#!/usr/bin/env python3
"""Inventaire COMPLET des valeurs de categorie et genre — lecture seule.
Même démarche que pour public_vise : d'abord voir toutes les valeurs et
leurs effectifs, ensuite décider ensemble d'une table de fusion, enfin
appliquer. Rien n'est modifié ici."""
import sys
sys.path.insert(0, ".")
import db

conn = db.connect()
for champ in ("categorie", "genre"):
    lignes = conn.execute(
        f"SELECT {champ}, COUNT(*) FROM notice "
        f"GROUP BY {champ} ORDER BY 2 DESC").fetchall()
    print(f"\n===== {champ} : {len(lignes)} valeur(s) distincte(s) =====")
    for v, n in lignes:
        print(f"  {n:>7}  {str(v)!r}")
conn.close()
