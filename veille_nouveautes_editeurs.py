#!/usr/bin/env python3
"""
veille_nouveautes_editeurs.py — Veille des parutions jeunesse à venir, à
partir du flux RSS officiel de la BnF ("Nouveautés Éditeurs").

Contexte (2026-07-23) : ce flux est alimenté directement par les éditeurs
(déclarations de parution auprès de la BnF, dépôt légal), gratuit, sans
authentification, mis à jour en continu. On l'utilise pour repérer les
titres jeunesse annoncés qui ne sont probablement pas encore dans notre
fonds -- une piste d'acquisition en amont du catalogage Decalog.

Limite connue, à ne jamais perdre de vue : le flux RSS ne fournit PAS
l'ISBN (seulement titre, auteur, éditeur, date de parution, lien vers une
fiche détail elle-même sans ISBN accessible facilement). Le rapprochement
avec notre fonds se fait donc par TITRE normalisé (minuscules, sans
accents, sans ponctuation) -- une correspondance approximative, jamais une
preuve absolue. Un titre marqué "pas trouvé" peut simplement être mal
orthographié ou légèrement différent dans Decalog : ce script signale des
PISTES à vérifier humainement, il ne décide jamais rien tout seul.

Usage :
    python3 veille_nouveautes_editeurs.py            (flux jeunesse)
    python3 veille_nouveautes_editeurs.py --tout      (flux tous types)
"""

import os
import sys
import re
import html
import unicodedata
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

import db
from public_vise import normaliser as normaliser_public

FLUX_JEUNESSE = "https://nouveautes-editeurs.bnf.fr/neRss?jeunesse=true"
FLUX_TOUS = "https://nouveautes-editeurs.bnf.fr/neRss"
TIMEOUT_SECONDES = 15
EN_TETES = {"User-Agent": "Mozilla/5.0 (compatible; MediathequeArcachonVeille/1.0)"}


def _normaliser(texte):
    """Minuscules, sans accents, sans ponctuation -- pour comparer des
    titres qui peuvent différer par la casse ou la typographie sans être
    réellement différents."""
    if not texte:
        return ""
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower()
    texte = re.sub(r"[^a-z0-9 ]", " ", texte)
    texte = re.sub(r"\s+", " ", texte).strip()
    return texte


def _telecharger_flux(url):
    """Télécharge un flux RSS. Gère la décompression gzip : certains flux
    (Ricochet notamment) répondent en gzip même sans qu'on le demande --
    sans ça, ET.fromstring reçoit des octets binaires illisibles."""
    import gzip
    requete = urllib.request.Request(url, headers=EN_TETES)
    with urllib.request.urlopen(requete, timeout=TIMEOUT_SECONDES) as reponse:
        brut = reponse.read()
        if reponse.headers.get("Content-Encoding") == "gzip" or brut[:2] == b"\x1f\x8b":
            try:
                brut = gzip.decompress(brut)
            except OSError:
                pass  # pas réellement gzip malgré l'en-tête -- on garde tel quel
        return brut


def _parser_description(description_html):
    """La description de chaque <item> contient l'auteur, l'éditeur et la
    date de parution sous forme de HTML échappé -- on les extrait par
    motif plutôt que par un vrai parseur HTML (structure simple et stable,
    toujours les mêmes 2-3 paragraphes)."""
    texte = html.unescape(description_html or "")
    auteur = editeur = date_parution = None
    m = re.search(r"Auteurs?\s*:\s*([^<]+)", texte)
    if m:
        auteur = m.group(1).strip().rstrip(";").strip()
    m = re.search(r"[EÉ]diteur\s*:\s*([^<]+)", texte)
    if m:
        editeur = m.group(1).strip()
    m = re.search(r"Date de parution\s*:\s*([0-9/]+)", texte)
    if m:
        date_parution = m.group(1).strip()
    return auteur, editeur, date_parution


def charger_nouveautes(url):
    try:
        data = _telecharger_flux(url)
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"Impossible de récupérer le flux BnF : {type(e).__name__}: {e}")
        return []

    try:
        racine = ET.fromstring(data)
    except ET.ParseError as e:
        print(f"Flux BnF reçu mais illisible (format inattendu) : {e}")
        return []

    nouveautes = []
    for item in racine.iter("item"):
        titre = (item.findtext("title") or "").strip()
        if not titre:
            continue
        lien = (item.findtext("link") or "").strip()
        description = item.findtext("description") or ""
        auteur, editeur, date_parution = _parser_description(description)
        nouveautes.append({
            "titre": titre,
            "auteur": auteur,
            "editeur": editeur,
            "date_parution": date_parution,
            "lien": lien,
        })
    return nouveautes


def charger_titres_du_fonds():
    """Un seul aller-retour base : on récupère tous les titres existants et
    on les normalise côté Python, plus fiable qu'un LIKE SQL insensible
    aux accents (Turso/SQLite ne gère pas correctement les accents dans
    LIKE, piège déjà rencontré ailleurs dans ce projet)."""
    conn = db.connect()
    try:
        lignes = conn.execute("SELECT titre FROM notice WHERE titre IS NOT NULL").fetchall()
    finally:
        conn.close()
    return {_normaliser(l[0]) for l in lignes if l[0]}


DEMANDEUR_VEILLE = "Veille automatique"


def _connexion_ecriture():
    """Connexion avec le jeton d'écriture dédié (TURSO_AUTH_TOKEN_ECRITURE
    dans .env) -- jamais le jeton lecture-seule utilisé pour le reste du
    script. Renvoie None si le jeton n'est pas configuré (best-effort :
    l'absence d'écriture ne doit jamais faire échouer la génération du
    rapport, seulement l'enregistrement en base)."""
    jeton = os.environ.get("TURSO_AUTH_TOKEN_ECRITURE")
    if not jeton or not db.MODE_EN_LIGNE:
        return None
    return db.connect_avec_jeton(db.TURSO_URL, jeton)


def enregistrer_suggestions(absents, source_label):
    """Ajoute les titres absents dans suggestion_acquisition, SANS jamais
    créer de doublon d'un run à l'autre (le flux BnF est réinterrogé chaque
    semaine -- un même titre non encore acquis y réapparaît systématiquement
    tant qu'on ne l'a pas ajouté ou explicitement écarté). Statut de départ
    'à étudier' comme toute suggestion : rien n'est jamais acquis tout seul,
    seulement mis en file d'attente pour relecture humaine."""
    conn = _connexion_ecriture()
    if conn is None:
        print("(TURSO_AUTH_TOKEN_ECRITURE absent ou base locale -- suggestions non enregistrées, "
              "affichées ci-dessus uniquement.)")
        return 0, 0

    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_acquisition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL,
                demandeur TEXT,
                auteur TEXT,
                editeur TEXT,
                isbn TEXT,
                prix REAL,
                motif TEXT,
                source TEXT,
                statut TEXT NOT NULL DEFAULT 'à étudier',
                date_ajout TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        # Migration silencieuse : colonnes de classement, ajoutées le
        # 2026-07-25 pour permettre de trier les suggestions par segment
        # (BD jeunesse, manga adulte, romans ado...) dans l'interface.
        for colonne in ("categorie", "public_vise", "genre"):
            try:
                conn.execute(f"ALTER TABLE suggestion_acquisition ADD COLUMN {colonne} TEXT")
                conn.commit()
            except Exception:
                pass  # colonne déjà présente

        deja_suggeres = {
            _normaliser(l[0]) for l in
            conn.execute("SELECT titre FROM suggestion_acquisition").fetchall() if l[0]
        }

        ajoutes = 0
        ignores_doublon = 0
        for n in absents:
            norm = _normaliser(n["titre"])
            if norm in deja_suggeres:
                ignores_doublon += 1
                continue
            # Motif fourni par l'appelant (ex. veille des prix littéraires :
            # "Prix Sorcières 2026 — catégorie ...") sinon motif par défaut
            # pour une nouveauté éditeur.
            motif = n.get("motif")
            if not motif:
                motif = "Parution annoncée par l'éditeur"
                if n.get("date_parution"):
                    motif += f" (date de parution : {n['date_parution']})"
            conn.execute(
                "INSERT INTO suggestion_acquisition "
                "(titre, demandeur, auteur, editeur, isbn, motif, source, "
                " categorie, public_vise, genre) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (n["titre"], DEMANDEUR_VEILLE, n.get("auteur"), n.get("editeur"),
                 n.get("isbn"), motif, source_label,
                 n.get("categorie"),
                 # même règle que le catalogue : 4 valeurs canoniques
                 # (public_vise.py), et JAMAIS de public vide (demande de
                 # Thomas, 2026-07-27) : à défaut, la source décide
                 # (veille jeunesse -> Jeunesse), sinon « Tout public »
                 normaliser_public(n.get("public_vise"))
                 or ("Jeunesse" if any(mot in source_label.lower()
                                       for mot in ("jeunesse", "ricochet"))
                     else "Tout public"),
                 n.get("genre")),
            )
            deja_suggeres.add(norm)
            ajoutes += 1
        conn.commit()
        return ajoutes, ignores_doublon
    finally:
        conn.close()


def main():
    url = FLUX_TOUS if "--tout" in sys.argv else FLUX_JEUNESSE
    label = "tous types" if "--tout" in sys.argv else "jeunesse"

    print(f"═══ Veille nouveautés éditeurs BnF — flux {label} ═══\n")

    nouveautes = charger_nouveautes(url)
    if not nouveautes:
        print("Aucune nouveauté récupérée (flux vide ou inaccessible).")
        return

    print(f"{len(nouveautes)} parutions annoncées dans le flux.\n")

    titres_fonds = charger_titres_du_fonds()
    print(f"({len(titres_fonds)} titres distincts actuellement dans notre fonds pour comparaison.)\n")

    absents = []
    presents = []
    for n in nouveautes:
        titre_norm = _normaliser(n["titre"])
        if titre_norm in titres_fonds:
            presents.append(n)
        else:
            absents.append(n)

    print(f"── À envisager, pas trouvées dans le fonds ({len(absents)}) ──")
    print("(rapprochement par titre normalisé -- à vérifier humainement avant toute décision)\n")
    for n in absents:
        print(f"  • {n['titre']}")
        details = []
        if n["auteur"]:
            details.append(n["auteur"])
        if n["editeur"]:
            details.append(n["editeur"])
        if n["date_parution"]:
            details.append(f"parution {n['date_parution']}")
        if details:
            print(f"    {' — '.join(details)}")
        if n["lien"]:
            print(f"    {n['lien']}")
        print()

    if presents:
        print(f"── Probablement déjà au fonds ({len(presents)}) ──")
        for n in presents:
            print(f"  • {n['titre']}")

    print()
    ajoutes, doublons = enregistrer_suggestions(absents, source_label=f"Veille BnF Nouveautés Éditeurs ({label})")
    print(f"── Suggestions d'acquisition : {ajoutes} ajoutée(s), {doublons} déjà présente(s) (pas de doublon créé) ──")


if __name__ == "__main__":
    main()
