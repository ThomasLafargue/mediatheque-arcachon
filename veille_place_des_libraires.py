#!/usr/bin/env python3
"""
veille_place_des_libraires.py — Veille d'acquisition à partir des SÉLECTIONS
de libraires sur Place des Libraires (placedeslibraires.fr).

Pourquoi cette source (2026-07-25) :
  - ce sont des sélections de LIBRAIRES INDÉPENDANTS : curation professionnelle
    humaine, pas un classement commercial ;
  - la plateforme est celle de la Librairie Générale d'Arcachon, notre
    fournisseur : un titre repéré ici est directement commandable chez eux ;
  - les données viennent de Dilicom (fichier professionnel du livre) : ISBN,
    série et tome fiables, contrairement au reste du web ;
  - les pages sont rendues côté serveur, donc lisibles par un script.

TOUS LES RAYONS sont couverts (jeunesse, BD, romans, polar, sciences...) et
pas seulement la jeunesse : le chat est utilisé par plusieurs agents de la
médiathèque, chacun avec son domaine. Le nom de la sélection d'origine est
conservé dans le motif de chaque suggestion, pour que chacun retrouve la
sienne.

Avantage décisif sur les autres veilles : on récupère l'ISBN, donc le
rapprochement avec le fonds est EXACT (les veilles BnF et Ricochet doivent se
contenter d'un rapprochement approximatif par titre).

Usage :
    python3 veille_place_des_libraires.py
    python3 veille_place_des_libraires.py --max 30    (limiter les fiches consultées)
    python3 veille_place_des_libraires.py --lister    (voir les sélections, sans rien écrire)
"""

import datetime
import os
import re
import sys
import time

import db  # noqa: F401 — correctif SSL (certifi) sur macOS
import requests
from bs4 import BeautifulSoup

from veille_nouveautes_editeurs import enregistrer_suggestions

BASE = "https://www.placedeslibraires.fr"
PAGE_SELECTIONS = f"{BASE}/liste_selections.php"
PAGE_COUPS_DE_COEUR = f"{BASE}/coups-de-coeur/"

EN_TETES = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
MAX_FICHES_PAR_DEFAUT = 60   # fiches consultées par exécution (courtoisie + durée)
PAUSE = 0.4


def _get(url):
    try:
        r = requests.get(url, headers=EN_TETES, timeout=20, allow_redirects=True)
        return r if r.status_code == 200 else None
    except Exception:
        return None


# Pages d'où partir pour découvrir les sélections. Elles n'apparaissent PAS
# sur /liste_selections.php mais sur l'accueil et les pages de rayon (constaté
# le 2026-07-25 en cartographiant le site : voir carte_placedeslibraires.md).
PAGES_DECOUVERTE = [
    BASE + "/",
    PAGE_COUPS_DE_COEUR,
    BASE + "/jeunesse/ssh-1277",
]

# Sélections prioritaires quel que soit leur âge : ce sont des références
# professionnelles (prix littéraires, sélections du Salon du livre jeunesse).
MOTS_PRIORITAIRES = (
    "jeunesse", "pépite", "pepite", "slpj", "kibookin", "prix ", "goncourt",
    "femina", "renaudot", "académie", "academie", "nobel", "ado", "rentrée",
    "rentree", "coup de cœur", "coups de cœur", "coup de coeur", "coups de coeur",
)

NB_SELECTIONS_PAR_PASSAGE = 14   # on ne peut pas aspirer 549 listes/semaine


def _nettoyer_url_selection(url):
    """Ramène une sélection à son adresse canonique /list-{id}/{slug}/.

    Une même sélection est liée sous de multiples formes selon le contexte
    (?modele=grille, ?page=2, ?provenance=…, ?select_langue=…). Aucun de ces
    paramètres ne change le contenu : on supprime donc TOUTE la partie
    interrogative, sinon la même liste serait consultée plusieurs fois dans
    le même passage (constaté le 2026-07-25 : 5 doublons sur une sélection).
    """
    url = url.split("#")[0].split("?")[0]
    if not url.endswith("/"):
        url += "/"
    return url


def recuperer_selections():
    """Découvre les sélections de libraires : [(nom, url), ...].

    Les sélections ont une URL /list-{id}/{slug}/. Le site en compte plus de
    500 : on les priorise plutôt que de toutes les consulter chaque semaine.
    Priorité = les plus récentes (identifiant le plus élevé) + celles dont
    l'intitulé correspond à une référence professionnelle (prix, pépites,
    jeunesse...).
    """
    trouvees = {}
    for page in PAGES_DECOUVERTE:
        r = _get(page)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not re.search(r"/list-\d+/", href):
                continue
            url = _nettoyer_url_selection(href if href.startswith("http") else BASE + href)
            nom = re.sub(r"\s+", " ", a.get_text(strip=True))
            nom = re.sub(r"Voir tout$", "", nom).strip()[:80]
            # libellés inutiles : « Mosaïque », numéros de page
            if not nom or nom.isdigit() or nom.lower() in ("mosaïque", "mosaique"):
                m = re.search(r"/list-\d+/([^/?]+)", url)
                nom = m.group(1).replace("-", " ").capitalize() if m else ""
            if not nom:
                continue
            # on garde le libellé le plus explicite rencontré
            if url not in trouvees or len(nom) > len(trouvees[url]):
                trouvees[url] = nom

    # Complément : la carte du site (carte_placedeslibraires.md) recense
    # ~550 sélections, dont beaucoup ne sont liées depuis aucune des pages
    # de découverte (ex. « Les Prix littéraires de la rentrée 2025 »). On la
    # lit si elle est présente -- elle se régénère avec
    # _carte_placedeslibraires.py.
    chemin_carte = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "carte_placedeslibraires.md")
    if os.path.exists(chemin_carte):
        with open(chemin_carte, encoding="utf-8") as f:
            for ligne in f:
                m = re.match(r"^\- \*\*(.+?)\*\* — `(/list-\d+/[^`]*)`", ligne)
                if not m:
                    continue
                nom = re.sub(r"Voir tout$", "", m.group(1)).strip()[:80]
                url = _nettoyer_url_selection(BASE + m.group(2))
                # La carte note « (sans libellé) » quand le lien n'avait pas de
                # texte : on reconstruit alors le nom depuis le slug de l'URL,
                # sinon la sélection passerait pour intemporelle (pas d'année
                # détectable) et échapperait au filtre d'obsolescence.
                if nom.lower().startswith("(sans libell"):
                    nom = ""
                if not nom or nom.isdigit() or nom.lower() in ("mosaïque", "mosaique"):
                    ms = re.search(r"/list-\d+/([^/?]+)", url)
                    nom = ms.group(1).replace("-", " ").capitalize() if ms else ""
                if not nom:
                    continue
                if url not in trouvees or len(nom) > len(trouvees[url]):
                    trouvees[url] = nom

    def identifiant(url):
        m = re.search(r"/list-(\d+)/", url)
        return int(m.group(1)) if m else 0

    def prioritaire(nom):
        bas = nom.lower()
        return any(mot in bas for mot in MOTS_PRIORITAIRES)

    annee_courante = datetime.date.today().year

    def annee_du_nom(nom, url=""):
        """Année mentionnée dans l'intitulé OU dans l'adresse (le slug la
        contient souvent), sinon None. Sert à écarter les sélections périmées :
        en 2026, « Rentrée littéraire 2025 » n'a plus d'intérêt."""
        annees = [int(a) for a in re.findall(r"\b(20\d{2})\b", nom + " " + url)]
        return max(annees) if annees else None

    def perimee(nom, url=""):
        a = annee_du_nom(nom, url)
        if a is None:
            return False                     # sélection intemporelle : on garde
        texte = (nom + " " + url).lower()
        if "rentree" in texte or "rentrée" in texte:
            return a < annee_courante        # une rentrée passée est périmée
        return a < annee_courante - 2        # sinon on tolère 2 ans (prix, pépites)

    def cle_tri(nom, url):
        # d'abord les plus récentes par millésime, puis par identifiant
        a = annee_du_nom(nom, url) or annee_courante   # sans année = actuelle
        return (-a, -identifiant(url))

    retenues = [(n, u) for u, n in trouvees.items() if not perimee(n, u)]
    prioritaires = sorted([(n, u) for n, u in retenues if prioritaire(n)],
                          key=lambda x: cle_tri(*x))
    autres = sorted([(n, u) for n, u in retenues if not prioritaire(n)],
                    key=lambda x: cle_tri(*x))

    # ROTATION hebdomadaire : sans elle, les mêmes sélections seraient
    # consultées à chaque passage et les autres jamais atteintes. On décale
    # le point de départ selon la semaine de l'année.
    semaine = datetime.date.today().isocalendar()[1]
    n_prio = int(NB_SELECTIONS_PAR_PASSAGE * 0.6)      # ~60 % de prioritaires
    n_autres = NB_SELECTIONS_PAR_PASSAGE - n_prio

    def fenetre(liste, taille):
        if not liste:
            return []
        depart = (semaine * taille) % len(liste)
        double = liste + liste
        return double[depart:depart + taille]

    selections = fenetre(prioritaires, n_prio) + fenetre(autres, n_autres)
    # la page « coups de cœur » est une sélection à part entière, vue à chaque fois
    selections.append(("Coups de cœur des libraires", PAGE_COUPS_DE_COEUR))
    return selections


def isbns_de_page(url):
    r = _get(url)
    if not r:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    isbns, vus = [], set()
    for a in soup.select("a[href*='/livre/']"):
        m = re.search(r"/livre/(\d{9,13})", a.get("href", ""))
        if not m:
            continue
        isbn = m.group(1)
        if isbn in vus:
            continue
        vus.add(isbn)
        isbns.append(isbn)
    return isbns


def isbns_du_fonds():
    conn = db.connect()
    try:
        lignes = conn.execute(
            "SELECT identifiant FROM notice WHERE identifiant NOT LIKE 'CB:%'"
        ).fetchall()
    finally:
        conn.close()
    return {str(l[0]).replace("-", "").strip() for l in lignes if l[0]}


def isbns_deja_suggeres():
    """Évite de reconsulter des fiches déjà proposées lors d'un passage
    précédent (économise des requêtes inutiles)."""
    conn = db.connect()
    try:
        lignes = conn.execute(
            "SELECT isbn FROM suggestion_acquisition WHERE isbn IS NOT NULL AND isbn != ''"
        ).fetchall()
    except Exception:
        return set()
    finally:
        conn.close()
    return {str(l[0]).replace("-", "").strip() for l in lignes if l[0]}


def main():
    maxi = MAX_FICHES_PAR_DEFAUT
    if "--max" in sys.argv:
        try:
            maxi = int(sys.argv[sys.argv.index("--max") + 1])
        except (IndexError, ValueError):
            pass
    lister_seulement = "--lister" in sys.argv

    print("═══ Veille Place des Libraires — sélections de libraires ═══\n")

    selections = recuperer_selections()
    if not selections:
        print("Aucune sélection récupérée (page inaccessible ?).")
        return
    print(f"{len(selections)} sélection(s) trouvée(s) :\n")
    for nom, url in selections:
        print(f"  • {nom[:60]:60} {url[len(BASE):][:45]}")

    if lister_seulement:
        print("\n(--lister : rien n'a été écrit en base.)")
        return

    print("\nLecture des sélections...")
    # ISBN -> nom de la sélection d'origine (première rencontrée)
    origine = {}
    for nom, url in selections:
        isbns = isbns_de_page(url)
        nouveaux = [i for i in isbns if i not in origine]
        for i in nouveaux:
            origine[i] = nom
        print(f"  {nom[:52]:52} {len(isbns):3} fiches ({len(nouveaux)} nouvelles)")
        time.sleep(PAUSE)

    fonds = isbns_du_fonds()
    deja = isbns_deja_suggeres()
    print(f"\n({len(fonds)} ISBN au fonds, {len(deja)} déjà suggérés — "
          "rapprochement exact par ISBN.)")

    candidats = [i for i in origine if i not in fonds and i not in deja]
    print(f"{len(origine)} titres au total, {len(candidats)} à examiner "
          f"(limite {maxi} par exécution).\n")

    import moteur_recherche as m

    absents = []
    for isbn in candidats[:maxi]:
        try:
            res = m.placedeslibraires_lookup(isbn)
        except Exception:
            res = None
        if not res or not res.get("titre"):
            continue
        motif = f"Sélection de libraires : {origine[isbn]}"
        if res.get("serie"):
            motif += f" — série {res['serie']}"
            if res.get("tome"):
                motif += f" t.{res['tome']}"
        absents.append({
            "titre": res["titre"],
            "auteur": res.get("auteur"),
            "editeur": res.get("editeur"),
            "date_parution": None,
            "isbn": isbn,
            "motif": motif,
            # Classement déduit par le moteur : permet de filtrer les
            # suggestions par segment dans l'interface (BD jeunesse, manga
            # adulte, romans ado...).
            "categorie": res.get("type"),
            "public_vise": res.get("public"),
            "genre": res.get("genre"),
        })
        print(f"  • {res['titre'][:52]}"
              + (f" — {res['auteur'][:28]}" if res.get("auteur") else ""))
        print(f"      ISBN {isbn} | {origine[isbn][:45]}")
        time.sleep(PAUSE)

    print(f"\n── {len(absents)} titre(s) absents du fonds retenus ──")
    ajoutes, doublons = enregistrer_suggestions(
        absents, source_label="Veille Place des Libraires (sélections)")
    print(f"── Suggestions : {ajoutes} ajoutée(s), {doublons} déjà présente(s) ──")


if __name__ == "__main__":
    main()
