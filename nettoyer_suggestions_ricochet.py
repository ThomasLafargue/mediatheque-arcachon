#!/usr/bin/env python3
"""
nettoyer_suggestions_ricochet.py — Retire de suggestion_acquisition les
lignes ajoutées par la veille Ricochet (source LIKE 'Veille Ricochet%').

Usage ponctuel (2026-07-23) : le premier run de veille_ricochet.py pointait
par erreur vers le flux d'ARTICLES éditoriaux de Ricochet (et non le
catalogue livres), ce qui a inséré des entrées qui ne sont pas des livres.
Ce script les efface proprement pour repartir sur une base saine, avant de
relancer la veille corrigée (qui pointe désormais vers /livres/rss.xml et
ne garde que les fiches livres).

Réutilisable tel quel si un jour il faut re-purger la source Ricochet.

Usage :
    python3 nettoyer_suggestions_ricochet.py
"""

import os
import db


def main():
    jeton = os.environ.get("TURSO_AUTH_TOKEN_ECRITURE")
    if not jeton or not db.MODE_EN_LIGNE:
        print("TURSO_AUTH_TOKEN_ECRITURE absent ou base locale -- rien à faire.")
        return

    conn = db.connect_avec_jeton(db.TURSO_URL, jeton)
    try:
        lignes = conn.execute(
            "SELECT id, titre FROM suggestion_acquisition WHERE source LIKE 'Veille Ricochet%'"
        ).fetchall()
        if not lignes:
            print("Aucune suggestion Ricochet à retirer.")
            return
        print(f"{len(lignes)} suggestion(s) Ricochet à retirer :")
        for lid, titre in lignes:
            print(f"  - id {lid} : {titre}")
        conn.execute("DELETE FROM suggestion_acquisition WHERE source LIKE 'Veille Ricochet%'")
        conn.commit()
        print("Supprimées. Tu peux relancer veille_ricochet.py (flux corrigé).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
