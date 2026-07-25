#!/usr/bin/env python3
"""
veille_place_des_libraires.py — Veille d'acquisition à partir des « coups de
cœur » de Place des Libraires (placedeslibraires.fr).

Pourquoi cette source (2026-07-25) :
  - ce sont des sélections de LIBRAIRES INDÉPENDANTS, donc une curation
    professionnelle humaine, pas un classement commercial ;
  - la plateforme est celle de la Librairie Générale d'Arcachon, notre
    fournisseur : un titre repéré ici est directement commandable chez eux ;
  - les données viennent de Dilicom (fichier professionnel du livre), donc
    l'ISBN, la série et le tome sont fiables -- contrairement au reste du web ;
  - la page est rendue côté serveur, donc lisible par un script (vérifié :
    118 fiches livres détectées, avec leur ISBN).

Contrairement aux autres veilles (BnF, Ricochet) qui n'ont pas l'ISBN et
doivent rapprocher par titre, ici on récupère l'ISBN : le rapprochement avec
le fonds est donc EXACT, sans risque de faux positif.

Réutilise l'écriture anti-doublon de veille_nouveautes_editeurs.py (même
table suggestion_acquisition, statut « à étudier », rien n'est acquis
automatiquement).

Usage :
    python3 veille_place_des_libraires.py
    python3 veille_place_des_libraires.py --max 40   (limiter les requêtes)
"""

import re
import sys
import time

import db  # noqa: F401 — correctif SSL (certifi) sur macOS
import requests
from bs4 import BeautifulSoup

from veille_nouveautes_editeurs import (
    charger_titres_du_fonds,
    enregistrer_suggestions,
    _normaliser,
)

PAGE_COUPS_DE_COEUR = "https://www.placedeslibraires.fr/coups-de-coeur/"
EN_TETES = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
MAX_PAR_DEFAUT = 60          # nb de fiches consultées par exécution
PAUSE_ENTRE_FICHES = 0.4     # courtoisie envers le site


def recuperer_isbns():
    """Extrait les ISBN des fiches mises en avant sur la page coups de cœur."""
    try:
        r = requests.get(PAGE_COUPS_DE_COEUR, headers=EN_TETES, timeout=20,
                         allow_redirects=True)
    except Exception as e:
        print(f"Page coups de cœur inaccessible : {type(e).__name__}: {e}")
        return []
    if r.status_code != 200:
        print(f"Page coups de cœur : HTTP {r.status_code}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    isbns = []
    vus = set()
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


def charger_isbns_du_fonds():
    """ISBN déjà présents dans le fonds -- rapprochement EXACT (pas par titre)."""
    conn = db.connect()
    try:
        lignes = conn.execute(
            "SELECT identifiant FROM notice WHERE identifiant NOT LIKE 'CB:%'"
        ).fetchall()
    finally:
        conn.close()
    return {str(l[0]).replace("-", "").strip() for l in lignes if l[0]}


def main():
    maxi = MAX_PAR_DEFAUT
    if "--max" in sys.argv:
        try:
            maxi = int(sys.argv[sys.argv.index("--max") + 1])
        except (IndexError, ValueError):
            pass

    print("═══ Veille Place des Libraires — coups de cœur des libraires ═══\n")

    isbns = recuperer_isbns()
    if not isbns:
        print("Aucune fiche récupérée.")
        return
    print(f"{len(isbns)} titres mis en avant par les libraires.\n")

    isbns_fonds = charger_isbns_du_fonds()
    print(f"({len(isbns_fonds)} ISBN dans notre fonds pour comparaison — "
          "rapprochement exact par ISBN.)\n")

    a_examiner = [i for i in isbns if i not in isbns_fonds][:maxi]
    deja = len(isbns) - len([i for i in isbns if i not in isbns_fonds])
    print(f"{deja} déjà au fonds, {len(a_examiner)} à examiner "
          f"(limite : {maxi} par exécution).\n")

    # On importe ici pour ne pas alourdir le démarrage si la page est vide
    import moteur_recherche as m

    absents = []
    for isbn in a_examiner:
        try:
            res = m.placedeslibraires_lookup(isbn)
        except Exception:
            res = None
        if not res or not res.get("titre"):
            continue
        absents.append({
            "titre": res["titre"],
            "auteur": res.get("auteur"),
            "editeur": res.get("editeur"),
            "date_parution": None,
            "isbn": isbn,
            "motif": "Coup de cœur des libraires indépendants (Place des Libraires)"
                     + (f" — série {res['serie']}" if res.get("serie") else ""),
        })
        ligne = f"  • {res['titre'][:55]}"
        if res.get("auteur"):
            ligne += f" — {res['auteur'][:30]}"
        print(ligne)
        print(f"      ISBN {isbn}"
              + (f" | série {res['serie']} t.{res.get('tome') or '?'}" if res.get("serie") else "")
              + (f" | {res['editeur']}" if res.get("editeur") else ""))
        time.sleep(PAUSE_ENTRE_FICHES)

    print(f"\n── {len(absents)} titre(s) absents du fonds retenus ──")
    ajoutes, doublons = enregistrer_suggestions(
        absents, source_label="Veille Place des Libraires (coups de cœur)")
    print(f"── Suggestions : {ajoutes} ajoutée(s), {doublons} déjà présente(s) ──")


if __name__ == "__main__":
    main()
