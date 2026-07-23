#!/usr/bin/env python3
"""
corriger_serie_tome_manquants.py — Déduit série + tome depuis le titre,
UNIQUEMENT pour les notices où Decalog n'a rien fourni.

Contexte : actualiser_catalogue.py extrait serie/tome depuis les champs MARC
structurés de Decalog (lien 461, ou sous-champs $h/$i). Quand le catalogueur
a tapé "One Piece tome 98" en texte libre dans le titre sans utiliser ces
champs, l'extraction échoue et serie/tome restent NULL -- alors que
lancer_enrichissement.py ne les corrige jamais (Decalog = source de vérité
sur ces champs, par design). Ce script comble ce trou, sans jamais toucher
une notice où Decalog a déjà fourni une valeur.

RÈGLE DE SÉCURITÉ ABSOLUE : n'écrit QUE si serie IS NULL ET tome IS NULL.
Ne modifie jamais une notice où Decalog a renseigné l'un des deux champs.

Usage :
    python3 corriger_serie_tome_manquants.py              # dry-run : rapport seul
    python3 corriger_serie_tome_manquants.py --appliquer   # écrit en base

Nécessite TURSO_AUTH_TOKEN_ECRITURE dans .env pour --appliquer
(absent du .env local au 2026-07-22 -- à copier depuis les secrets Streamlit).
"""

import sys
import os
import re
import argparse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


# Motifs testés dans l'ordre, du plus au moins strict. Toujours ancrés sur un
# marqueur explicite ("tome", "t.", "vol.") -- on ne devine JAMAIS à partir
# d'un simple nombre en fin de titre (trop ambigu : "Seuls 8" existe, mais
# "1,2,3... Nagasaki" aussi).
MOTIFS = [
    re.compile(r'^(?P<serie>.+?)\s*[,\-–—:]\s*(?:tome|t°|t\.?|vol\.?|volume)\s*n?°?\s*(?P<tome>\d{1,3})\s*[a-zA-Z]?\b', re.IGNORECASE),
    re.compile(r'^(?P<serie>.+?)\s+(?:tome|t°|vol\.?|volume)\s*n?°?\s*(?P<tome>\d{1,3})\s*[a-zA-Z]?\b', re.IGNORECASE),
]


def extraire_serie_tome(titre):
    """Retourne (serie, tome) ou (None, None) si aucun motif ne correspond."""
    if not titre:
        return None, None
    for motif in MOTIFS:
        m = motif.match(titre.strip())
        if m:
            serie = m.group('serie').strip(' .,-–—:')
            tome = m.group('tome').strip()
            if len(serie) >= 2:
                return serie, tome
    return None, None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--appliquer', action='store_true',
                         help="Écrit réellement en base (par défaut : dry-run, rapport seul)")
    parser.add_argument('--limite', type=int, default=None,
                         help="Limiter le nombre de notices traitées (utile pour un premier test)")
    args = parser.parse_args()

    if args.appliquer:
        jeton = os.environ.get('TURSO_AUTH_TOKEN_ECRITURE')
        if not jeton:
            print("✗ TURSO_AUTH_TOKEN_ECRITURE absent de .env -- impossible d'écrire.")
            print("  Copie-le depuis les secrets Streamlit dans le .env local, puis relance.")
            sys.exit(1)
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton)
    else:
        conn = db.connect()

    cur = conn.cursor()
    cur.execute("""
        SELECT identifiant, titre, categorie, type_document
        FROM notice
        WHERE type_document = 'LIVRE' AND serie IS NULL AND tome IS NULL
        ORDER BY identifiant
    """)
    lignes = cur.fetchall()
    if args.limite:
        lignes = lignes[:args.limite]

    print(f"Notices LIVRE sans serie/tome renseigné par Decalog : {len(lignes)}\n")

    par_categorie = Counter()
    trouvailles = []
    for identifiant, titre, categorie, type_doc in lignes:
        serie, tome = extraire_serie_tome(titre)
        par_categorie[categorie or '(sans catégorie)'] += 1
        if serie:
            trouvailles.append((identifiant, titre, serie, tome))

    print("Répartition par catégorie (parmi les notices concernées) :")
    for cat, n in par_categorie.most_common():
        print(f"  {cat:30} {n:6}")

    print(f"\nMotif détecté dans le titre (série + tome déductibles) : {len(trouvailles)} / {len(lignes)}")
    print(f"Restent ambigus (pas de marqueur 'tome'/'T.'/'vol.' dans le titre) : {len(lignes) - len(trouvailles)}")

    print("\nExemples de corrections détectées (20 premières) :")
    for identifiant, titre, serie, tome in trouvailles[:20]:
        print(f"  [{identifiant}] \"{titre}\"")
        print(f"      -> serie=\"{serie}\"  tome=\"{tome}\"")

    if not args.appliquer:
        print(f"\n(dry-run -- rien n'a été écrit. Relance avec --appliquer pour corriger les {len(trouvailles)} notices détectées.)")
        conn.close()
        return

    n_ok = 0
    for identifiant, titre, serie, tome in trouvailles:
        # Ces valeurs viennent de notre détection, pas de Decalog -- marquées
        # pour signalement (champs_a_verifier_decalog) afin de pouvoir les
        # corriger dans Decalog lui-même le jour venu.
        cur.execute(
            "UPDATE notice SET serie = ?, tome = ?, "
            "champs_a_verifier_decalog = COALESCE(champs_a_verifier_decalog, 'serie,tome') "
            "WHERE identifiant = ? AND serie IS NULL AND tome IS NULL",
            (serie, tome, identifiant),
        )
        n_ok += 1
    conn.commit()
    conn.close()
    print(f"\n✓ {n_ok} notices corrigées en base.")
    print(f"  {len(lignes) - len(trouvailles)} notices restent sans série/tome détectable automatiquement")
    print("  (titre sans marqueur 'tome'/'T.'/'vol.' -- ex: numéro seul en fin de titre).")


if __name__ == '__main__':
    main()
