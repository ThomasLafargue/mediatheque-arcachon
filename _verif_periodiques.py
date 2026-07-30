#!/usr/bin/env python3
"""Identifier les périodiques dans la base en ligne — lecture seule.
Objectif : trouver le critère fiable pour les EXCLURE des listes de
correction Decalog (EAN manquants, notices incomplètes), demande de
Thomas du 2026-07-30 : ils n'ont légitimement ni ISBN ni statut."""
import sys
sys.path.insert(0, ".")
import db

conn = db.connect()
print("1. Combien de notices typées REVUE ?")
for r in conn.execute("SELECT type_document, COUNT(*) FROM notice "
                      "GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print("  ", r)

print("\n2. Les notices CB: (sans EAN), par type :")
for r in conn.execute("SELECT type_document, COUNT(*) FROM notice "
                      "WHERE identifiant LIKE 'CB:%' "
                      "GROUP BY 1 ORDER BY 2 DESC").fetchall():
    print("  ", r)

print("\n3. Échantillon de 15 titres CB: typés LIVRE — des périodiques ?")
for r in conn.execute(
        "SELECT n.titre, e.cote, n.editeur FROM notice n "
        "LEFT JOIN exemplaire e ON e.identifiant = n.identifiant "
        "WHERE n.identifiant LIKE 'CB:%' AND n.type_document = 'LIVRE' "
        "LIMIT 15").fetchall():
    print("  ", r)

print("\n4. Cotes des sans-statut typés LIVRE (préfixes fréquents) :")
for r in conn.execute(
        "SELECT SUBSTR(e.cote, 1, 4), COUNT(*) FROM exemplaire e "
        "JOIN notice n ON n.identifiant = e.identifiant "
        "WHERE (e.statut IS NULL OR e.statut = '') "
        "AND n.type_document = 'LIVRE' "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 12").fetchall():
    print("  ", r)
conn.close()
