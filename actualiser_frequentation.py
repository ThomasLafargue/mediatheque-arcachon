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

    if not rows or ('DATE' not in rows[0] and 'Date' not in rows[0]):
        print("⚠ Colonnes attendues introuvables (DATE/Date) -- vérifie le format du fichier.")
        sys.exit(1)

    # Support deux formats : ancien (DATE, IN, HOUR) et nouveau (Date, Entrées, Heure)
    col_date   = 'DATE'   if 'DATE'   in rows[0] else 'Date'
    col_entree = 'IN'     if 'IN'     in rows[0] else 'Entrées'
    col_heure  = 'HOUR'   if 'HOUR'   in rows[0] else 'Heure'

    par_jour = defaultdict(int)
    par_heure = defaultdict(int)  # clé : (date, heure_arrondie)

    for r in rows:
        if not r.get(col_entree) or not r.get(col_date):
            continue
        try:
            entrees = int(r[col_entree])
            if entrees <= 0:
                continue
            date = r[col_date]
            par_jour[date] += entrees

            # Heure arrondie à l'heure (ex: "14:25" → "14:00")
            heure_brute = r.get(col_heure, '')
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

    # Écriture PAR PAQUETS (2026-07-28) : ligne à ligne, chaque INSERT
    # faisait un aller-retour réseau vers Turso -- ~27 000 allers-retours,
    # 30 à 60 minutes. En groupant 400 lignes par requête, on tombe à
    # quelques dizaines de requêtes : moins d'une minute.
    TAILLE_PAQUET = 400

    lignes_jour = list(par_jour.items())
    for i in range(0, len(lignes_jour), TAILLE_PAQUET):
        paquet = lignes_jour[i:i + TAILLE_PAQUET]
        valeurs = ", ".join(["(?, ?)"] * len(paquet))
        params = [x for ligne in paquet for x in ligne]
        cur.execute(
            f"INSERT INTO frequentation (date, nb_entrees) VALUES {valeurs} "
            "ON CONFLICT(date) DO UPDATE SET nb_entrees = excluded.nb_entrees",
            params)
        print(f"  ... jours : {min(i + TAILLE_PAQUET, len(lignes_jour))}"
              f"/{len(lignes_jour)}", end="\r", flush=True)
    print()

    lignes_heure = [(d, h, t) for (d, h), t in par_heure.items()]
    for i in range(0, len(lignes_heure), TAILLE_PAQUET):
        paquet = lignes_heure[i:i + TAILLE_PAQUET]
        valeurs = ", ".join(["(?, ?, ?)"] * len(paquet))
        params = [x for ligne in paquet for x in ligne]
        cur.execute(
            f"INSERT INTO frequentation_horaire (date, heure, nb_entrees) "
            f"VALUES {valeurs} "
            "ON CONFLICT(date, heure) DO UPDATE SET "
            "nb_entrees = excluded.nb_entrees",
            params)
        print(f"  ... tranches horaires : "
              f"{min(i + TAILLE_PAQUET, len(lignes_heure))}"
              f"/{len(lignes_heure)}", end="\r", flush=True)
    print()

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
