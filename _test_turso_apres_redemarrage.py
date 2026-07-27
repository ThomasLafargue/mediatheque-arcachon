#!/usr/bin/env python3
"""
_test_turso_apres_redemarrage.py — Répond aux 3 questions du support Turso
après le redémarrage du serveur, et vérifie si la panne est terminée.

On monte en charge progressivement : SELECT 1 (le plus simple possible),
puis COUNT, puis les vraies requêtes de l'application. Cela permet de dire
au support non pas « ça marche / ça ne marche pas » mais À PARTIR DE QUEL
VOLUME ça casse — c'est l'information qu'il lui manque.

Usage :  python3 _test_turso_apres_redemarrage.py
"""
import sys
import time

sys.path.insert(0, ".")
import db  # noqa: E402

TESTS = [
    ("SELECT 1 (le plus simple)",
     "SELECT 1"),
    ("COUNT(*) sur notice",
     "SELECT COUNT(*) FROM notice"),
    ("10 lignes courtes",
     "SELECT identifiant FROM notice LIMIT 10"),
    ("300 lignes avec titre + auteur",
     "SELECT identifiant, titre, createurs FROM notice LIMIT 300"),
    ("1000 lignes avec titre + auteur",
     "SELECT identifiant, titre, createurs FROM notice LIMIT 1000"),
    ("4000 lignes avec titre + auteur (le cas qui cassait en premier)",
     "SELECT identifiant, titre, createurs FROM notice LIMIT 4000"),
]

print("=== Test Turso apres redemarrage serveur ===")
print(time.strftime("%Y-%m-%d %H:%M:%S %Z"))
print()

for libelle, sql in TESTS:
    t0 = time.time()
    conn = None
    try:
        conn = db.connect()
        lignes = conn.execute(sql).fetchall()
        print(f"  OK    {libelle:56} {len(lignes):>5} ligne(s)  ({time.time()-t0:.1f}s)")
    except Exception as e:
        print(f"  ECHEC {libelle:56} ({time.time()-t0:.1f}s)")
        print(f"        {type(e).__name__}: {str(e)[:150]}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    time.sleep(0.5)

print()
print("Copier-coller ce bloc entier dans la reponse au support.")
