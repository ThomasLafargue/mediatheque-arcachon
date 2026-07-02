#!/usr/bin/env python3
"""
Actualisation de la fréquentation depuis un export Nedap/LibNet.

Alimente deux tables :
  - frequentation         : total journalier (date, nb_entrees)
  - frequentation_horaire : détail par tranche horaire (date, heure, nb_entrees)
    → permet d'analyser les heures de pointe, les pics de fréquentation, etc.

Usage :
    python3 actualiser_frequentation.py "Donnees_Comptage.csv"
"""

import sys
import os
import csv
import argparse
import db
from collections import defaultdict

FICHIER_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventaire.db")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fichier_csv")
    args = parser.parse_args()

    with open(args.fichier_csv, encoding="utf-8", errors="replace") as f:
        premiere_ligne = f.readline()
        if not premiere_ligne.startswith("sep="):
            f.seek(0)
        reader = csv.DictReader(f, delimiter=';')
        rows = list(reader)

    if not rows or 'DATE' not in rows[0] or 'IN' not in rows[0]:
        print("⚠ Colonnes attendues introuvables (DATE, IN) -- vérifie le format du fichier.")
        sys.exit(1)

    par_jour = defaultdict(int)
    par_heure = defaultdict(int)  # clé : (date, heure_arrondie)

    for r in rows:
        if not r.get('IN') or not r.get('DATE'):
            continue
        try:
            entrees = int(r['IN'])
            if entrees <= 0:
                continue
            date = r['DATE']
            par_jour[date] += entrees

            # Heure arrondie à l'heure (ex: "14:25" → "14:00")
            heure_brute = r.get('HOUR', '')
            if heure_brute and ':' in heure_brute:
                h = heure_brute.split(':')[0].zfill(2)
                heure = f"{h}:00"
                par_heure[(date, heure)] += entrees
        except (ValueError, KeyError):
            pass

    conn = db.connect(FICHIER_DB)
    cur = conn.cursor()

    # Créer la table horaire si elle n'existe pas encore
    cur.execute("""
        CREATE TABLE IF NOT EXISTS frequentation_horaire (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            date    TEXT NOT NULL,
            heure   TEXT NOT NULL,
            nb_entrees INTEGER NOT NULL,
            UNIQUE(date, heure)
        )
    """)

    # Table journalière
    for date, total in par_jour.items():
        cur.execute("""
            INSERT INTO frequentation (date, nb_entrees) VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET nb_entrees = excluded.nb_entrees
        """, (date, total))

    # Table horaire
    for (date, heure), total in par_heure.items():
        cur.execute("""
            INSERT INTO frequentation_horaire (date, heure, nb_entrees) VALUES (?, ?, ?)
            ON CONFLICT(date, heure) DO UPDATE SET nb_entrees = excluded.nb_entrees
        """, (date, heure, total))

    conn.commit()

    cur.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM frequentation")
    total_j, mini, maxi = cur.fetchone()
    cur.execute("SELECT COUNT(DISTINCT date) FROM frequentation_horaire")
    total_h = cur.fetchone()[0]
    conn.close()

    print(f"Jours mis à jour cette exécution : {len(par_jour)}")
    print(f"Total en base : {total_j} jours, du {mini} au {maxi}")
    print(f"Données horaires : {total_h} jours avec détail par heure")


if __name__ == "__main__":
    main()
