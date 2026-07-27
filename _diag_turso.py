#!/usr/bin/env python3
"""
_diag_turso.py — Isole la cause de l'erreur Hrana « unexpected EOF during
chunk size line » : volume, jointure, colonnes longues, ou base indisponible ?
On part du plus simple et on complexifie jusqu'à ce que ça casse.
"""
import sys, time
sys.path.insert(0, ".")
import db

TESTS = [
    ("1. COUNT simple",
     "SELECT COUNT(*) FROM notice"),
    ("2. COUNT sur le filtre visé",
     "SELECT COUNT(*) FROM notice WHERE champs_a_verifier_decalog IS NOT NULL "
     "AND champs_a_verifier_decalog != ''"),
    ("3. 10 lignes, colonnes courtes",
     "SELECT identifiant, serie, tome FROM notice "
     "WHERE champs_a_verifier_decalog IS NOT NULL LIMIT 10"),
    ("4. 10 lignes AVEC titre et auteur",
     "SELECT identifiant, titre, createurs, serie, tome FROM notice "
     "WHERE champs_a_verifier_decalog IS NOT NULL LIMIT 10"),
    ("5. 300 lignes, colonnes courtes",
     "SELECT identifiant, serie, tome FROM notice "
     "WHERE champs_a_verifier_decalog IS NOT NULL LIMIT 300"),
    ("6. 300 lignes AVEC titre et auteur",
     "SELECT identifiant, titre, createurs, serie, tome FROM notice "
     "WHERE champs_a_verifier_decalog IS NOT NULL LIMIT 300"),
    ("7. 300 lignes + ORDER BY",
     "SELECT identifiant, titre, createurs, serie, tome FROM notice "
     "WHERE champs_a_verifier_decalog IS NOT NULL "
     "ORDER BY identifiant LIMIT 300"),
    ("8. 300 lignes + JOIN exemplaire",
     "SELECT n.identifiant, n.titre, n.createurs, e.cote FROM notice n "
     "LEFT JOIN exemplaire e ON e.identifiant = n.identifiant "
     "WHERE n.champs_a_verifier_decalog IS NOT NULL LIMIT 300"),
]

for libelle, sql in TESTS:
    t0 = time.time()
    conn = None
    try:
        conn = db.connect()
        lignes = conn.execute(sql).fetchall()
        print(f"  ✓ {libelle:38} {len(lignes):>5} ligne(s)  ({time.time()-t0:.1f}s)")
    except Exception as e:
        print(f"  ✗ {libelle:38} ÉCHEC ({time.time()-t0:.1f}s)")
        print(f"      {type(e).__name__}: {str(e)[:100]}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    time.sleep(0.5)

print("\n✓ Diagnostic terminé.")
