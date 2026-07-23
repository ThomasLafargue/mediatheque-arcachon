#!/usr/bin/env python3
"""
Migration directe inventaire.db (local) -> Turso, table par table.

À lancer une seule fois, après avoir constaté que `turso db create
--from-file` n'a pas réellement chargé les données.

Usage :
    python3 migrer_vers_turso.py
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as db_module

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_LOCAL = os.path.join(DOSSIER, "inventaire.db")
FICHIER_SCHEMA = os.path.join(DOSSIER, "schema_inventaire.sql")

TAILLE_LOT = 200

TABLES = ['type_document', 'notice', 'exemplaire', 'frequentation',
          'flux_historique', 'flux_mensuel', 'commande', 'livraison', 'schema_info']


def main():
    if not db_module.MODE_EN_LIGNE:
        print("⚠ Mode en ligne non détecté (.env absent ou incomplet) -- rien à migrer.")
        sys.exit(1)

    print("Connexion à Turso...")
    conn_turso = db_module.connect()

    print("Création du schéma (tables, vues, index)...")
    with open(FICHIER_SCHEMA, encoding='utf-8') as f:
        conn_turso.executescript(f.read())
    print("  Schéma créé.\n")

    conn_local = sqlite3.connect(FICHIER_LOCAL)
    conn_local.row_factory = sqlite3.Row
    cur_local = conn_local.cursor()

    for table in TABLES:
        try:
            cur_local.execute(f"SELECT * FROM {table}")
        except sqlite3.OperationalError:
            print(f"  {table} : absente en local, ignorée")
            continue

        lignes = cur_local.fetchall()
        if not lignes:
            print(f"  {table} : vide, ignorée")
            continue

        colonnes = lignes[0].keys()
        n_col = len(colonnes)
        sql_colonnes = ", ".join(colonnes)

        total = len(lignes)
        for i in range(0, total, TAILLE_LOT):
            lot = lignes[i:i + TAILLE_LOT]
            groupes = ", ".join(["(" + ", ".join(["?"] * n_col) + ")"] * len(lot))
            params = []
            for ligne in lot:
                params.extend(tuple(ligne))
            sql_insert = f"INSERT INTO {table} ({sql_colonnes}) VALUES {groupes}"
            conn_turso.execute(sql_insert, params)
            conn_turso.commit()
            print(f"  {table} : {min(i + TAILLE_LOT, total)}/{total}", end='\r')
        print(f"  {table} : {total} lignes copiées")

    conn_local.close()
    conn_turso.close()
    print("\n✓ Migration terminée.")


if __name__ == "__main__":
    main()
