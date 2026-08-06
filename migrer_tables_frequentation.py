#!/usr/bin/env python3
"""
migrer_tables_frequentation.py — Renomme les tables de fréquentation pour
supprimer toute ambiguïté (2026-08-06).

POURQUOI : le chat a produit un tableau étiqueté « brut » rempli avec les
chiffres « ouverture » — il interrogeait la table `frequentation`, dont le
nom ne dit pas ce qu'elle contient. Après cette migration :
  frequentation          → frequentation_ouverture
  frequentation_horaire  → frequentation_horaire_ouverture
  (frequentation_brute et frequentation_horaire_brute ne changent pas)
Toute requête sur l'ancien nom échouera franchement au lieu de renvoyer des
chiffres mal étiquetés.

Usage :  python3 migrer_tables_frequentation.py
"""
import os
import sys

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
import db  # noqa: E402


def main():
    conn = db.connect()
    existantes = {l[0] for l in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for ancien, nouveau in (
            ("frequentation", "frequentation_ouverture"),
            ("frequentation_horaire", "frequentation_horaire_ouverture")):
        if nouveau in existantes:
            print(f"  {nouveau} existe déjà — rien à faire.")
        elif ancien in existantes:
            conn.execute(f"ALTER TABLE {ancien} RENAME TO {nouveau}")
            print(f"  ✓ {ancien} → {nouveau}")
        else:
            print(f"  ⚠ table {ancien} introuvable !")
    conn.commit()
    for t in ("frequentation_ouverture", "frequentation_horaire_ouverture",
              "frequentation_brute", "frequentation_horaire_brute"):
        try:
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t} : {n} lignes")
        except Exception as e:
            print(f"  {t} : ERREUR {e}")
    conn.close()


if __name__ == "__main__":
    main()
