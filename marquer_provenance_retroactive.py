#!/usr/bin/env python3
"""
marquer_provenance_retroactive.py — Marque rétroactivement les 935 notices
déjà corrigées par corriger_serie_tome_manquants.py --appliquer le
2026-07-22, AVANT que le suivi champs_a_verifier_decalog n'existe.

Comment ça retrouve les bonnes notices : la fonction de détection est pure
et déterministe (même titre -> même résultat). On la rejoue sur les
notices qui ont serie+tome renseignés mais pas encore de marqueur ; si le
résultat correspond exactement à ce qui est en base, c'est que ça vient de
ce script (et pas de Decalog) -- on marque.

Usage :
    python3 marquer_provenance_retroactive.py           # dry-run, rapport seul
    python3 marquer_provenance_retroactive.py --appliquer
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
from corriger_serie_tome_manquants import extraire_serie_tome


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--appliquer', action='store_true')
    args = parser.parse_args()

    if args.appliquer:
        jeton = os.environ.get('TURSO_AUTH_TOKEN_ECRITURE')
        if not jeton:
            print("✗ TURSO_AUTH_TOKEN_ECRITURE absent de .env.")
            sys.exit(1)
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton)
    else:
        conn = db.connect()

    cur = conn.cursor()
    cur.execute("""
        SELECT identifiant, titre, serie, tome
        FROM notice
        WHERE type_document = 'LIVRE'
          AND serie IS NOT NULL AND tome IS NOT NULL
          AND champs_a_verifier_decalog IS NULL
    """)
    lignes = cur.fetchall()

    a_marquer = []
    for identifiant, titre, serie_actuel, tome_actuel in lignes:
        serie_deduite, tome_deduit = extraire_serie_tome(titre)
        if serie_deduite == serie_actuel and tome_deduit == tome_actuel:
            a_marquer.append(identifiant)

    print(f"Notices candidates (serie/tome déjà renseignés, pas encore marqués) : {len(lignes)}")
    print(f"Correspondent exactement à la détection par motif (donc issues de "
          f"corriger_serie_tome_manquants.py) : {len(a_marquer)}")

    if not args.appliquer:
        print("\n(dry-run -- rien n'a été écrit. Relance avec --appliquer.)")
        conn.close()
        return

    for identifiant in a_marquer:
        cur.execute(
            "UPDATE notice SET champs_a_verifier_decalog = 'serie,tome' WHERE identifiant = ?",
            (identifiant,),
        )
    conn.commit()
    conn.close()
    print(f"\n✓ {len(a_marquer)} notices marquées champs_a_verifier_decalog = 'serie,tome'.")


if __name__ == '__main__':
    main()
