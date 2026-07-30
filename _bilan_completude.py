#!/usr/bin/env python3
"""Bilan de complétude de NOTRE base, après la fin de l'enrichissement
(30/07/2026). Lecture seule. Mesure ce qui reste vide là où ça compte."""
import sys
sys.path.insert(0, ".")
import db

conn = db.connect()
q = lambda sql: conn.execute(sql).fetchone()[0]

total = q("SELECT COUNT(*) FROM notice")
livres = q("SELECT COUNT(*) FROM notice WHERE type_document='LIVRE'")
print(f"Notices : {total}  (dont {livres} livres)\n")

print("CE QUI RESTE À COMBLER (notre base) :")
for libelle, sql in [
    ("BD/Manga sans série",
     "SELECT COUNT(*) FROM notice WHERE categorie IN ('BD','Manga') "
     "AND (serie IS NULL OR serie='')"),
    ("BD/Manga avec série mais sans tome",
     "SELECT COUNT(*) FROM notice WHERE categorie IN ('BD','Manga') "
     "AND serie IS NOT NULL AND serie != '' AND (tome IS NULL OR tome='')"),
    ("Livres sans catégorie",
     "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' "
     "AND (categorie IS NULL OR categorie='')"),
    ("Livres sans genre",
     "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' "
     "AND (genre IS NULL OR genre='')"),
    ("Livres sans résumé",
     "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' "
     "AND (resume IS NULL OR resume='')"),
    ("Livres sans image de couverture",
     "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' "
     "AND (image_url IS NULL OR image_url='')"),
    ("Sans EAN (identifiant CB:), livres depuis 2000",
     "SELECT COUNT(*) FROM notice WHERE identifiant LIKE 'CB:%' "
     "AND type_document='LIVRE' "
     "AND CAST(SUBSTR(date_publication,1,4) AS INTEGER) >= 2000"),
    ("Jamais passées par l'enrichissement",
     "SELECT COUNT(*) FROM notice WHERE date_enrichissement IS NULL "
     "AND identifiant NOT LIKE 'CB:%'"),
]:
    n = q(sql)
    print(f"  {n:>7}  {libelle}")

print("\nCE QUE NOTRE MOTEUR A DÉDUIT ET QUE DECALOG N'A PAS "
      "(à recopier dans Decalog) :")
n = q("SELECT COUNT(*) FROM notice WHERE champs_a_verifier_decalog "
      "IS NOT NULL AND champs_a_verifier_decalog != ''")
print(f"  {n:>7}  notices concernées (cf. Corrections_Decalog_*.xlsx)")
conn.close()
