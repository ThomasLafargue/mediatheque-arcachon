#!/usr/bin/env python3
"""Contrôle AVANT normalisation : quelles valeurs contient pegi pour les
mangas ? La simulation a trouvé 0 manga en PEGI >= 14, ce qui est suspect
(aucun seinen dans le fonds ?). Si pegi contient du texte, CAST le lit 0
et la règle basculerait des mangas adultes en Jeunesse. Lecture seule."""
import sys
sys.path.insert(0, ".")
import db

conn = db.connect()
print("pegi des mangas (base en ligne) :")
for r in conn.execute(
        "SELECT pegi, CAST(pegi AS INTEGER), COUNT(*) FROM notice "
        "WHERE categorie = 'Manga' GROUP BY pegi ORDER BY 3 DESC").fetchall():
    print(f"  pegi={str(r[0])!r:20} CAST={str(r[1]):>4}  {r[2]:>5} notices")
print("\npegi toutes catégories (les 12 plus fréquents) :")
for r in conn.execute(
        "SELECT pegi, COUNT(*) FROM notice WHERE pegi IS NOT NULL "
        "AND pegi != '' GROUP BY pegi ORDER BY 2 DESC LIMIT 12").fetchall():
    print(f"  {str(r[0])!r:20} {r[1]:>6}")
conn.close()
