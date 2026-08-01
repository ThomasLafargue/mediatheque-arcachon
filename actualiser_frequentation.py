#!/usr/bin/env python3
"""
Actualisation de la fréquentation depuis un export Nedap/LibNet.

Alimente deux tables :
  - frequentation         : total journalier (date, nb_entrees)
  - frequentation_horaire : détail par tranche horaire (date, heure, nb_entrees)
    → permet d'analyser les heures de pointe, les pics de fréquentation, etc.

RÈGLE (Thomas, 2026-08-01) : SEULES les heures d'ouverture au public
comptent. Juillet-août : lundi-samedi 10h-19h ; reste de l'année :
mardi-samedi 10h-18h. Tout passage hors fenêtre (équipe le matin,
ménage, jours fermés — dimanches compris, même événementiels) est
IGNORÉ au chargement. Le compteur Nedap enregistrait ~3 % de passages
hors ouverture qui faussaient les statistiques du chat.

Usage :
    python3 actualiser_frequentation.py "Donnees_Comptage.csv"
    python3 actualiser_frequentation.py "Donnees_Comptage.csv" --recharger-tout
        → vide d'abord les deux tables (à utiliser quand le CSV couvre tout
          l'historique, ex. après un changement de règle de filtrage).
"""

import sys
import os
import csv
import argparse
import datetime
import db
from collections import defaultdict

FICHIER_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventaire.db")


def est_ouvert(date_iso, heure_hm):
    """Le MAAT est-il ouvert au public à ce moment-là ?
    date_iso = 'AAAA-MM-JJ', heure_hm = 'HH:MM' (zéro-paddée)."""
    try:
        jour_semaine = datetime.date.fromisoformat(date_iso).weekday()  # 0 = lundi
    except ValueError:
        return False
    ete = date_iso[5:7] in ("07", "08")
    if ete:
        return jour_semaine <= 5 and "10:00" <= heure_hm < "19:00"
    return 1 <= jour_semaine <= 5 and "10:00" <= heure_hm < "18:00"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fichier_csv")
    parser.add_argument("--recharger-tout", action="store_true",
                        help="Vide les deux tables avant chargement "
                             "(CSV historique complet uniquement)")
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

    hors_ouverture = 0
    for r in rows:
        if not r.get(col_entree) or not r.get(col_date):
            continue
        try:
            entrees = int(r[col_entree])
            if entrees <= 0:
                continue
            date = r[col_date]

            heure_brute = r.get(col_heure, '')
            if not heure_brute or ':' not in heure_brute:
                continue  # sans heure, impossible de filtrer : on écarte
            h, m = heure_brute.split(':')[0].zfill(2), heure_brute.split(':')[1][:2].zfill(2)

            # RÈGLE : seules les heures d'ouverture au public comptent.
            if not est_ouvert(date, f"{h}:{m}"):
                hors_ouverture += entrees
                continue

            par_jour[date] += entrees
            par_heure[(date, f"{h}:00")] += entrees  # arrondi à l'heure
        except (ValueError, KeyError):
            pass
    print(f"Passages hors ouverture ignorés : {hors_ouverture}")

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

    if args.recharger_tout:
        print("Rechargement complet : vidage des deux tables...")
        cur.execute("DELETE FROM frequentation")
        cur.execute("DELETE FROM frequentation_horaire")

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
