#!/usr/bin/env python3
"""
Enrichissement prêts Decalog -> inventaire.db
================================================
Met à jour les notices déjà présentes dans inventaire.db avec les
statistiques de prêts d'un export Decalog ("Liste des notices...xls").

Ce script NE CRÉE JAMAIS de nouvelle notice. Il met à jour, par EAN/ISBN,
les notices déjà migrées (fonds livres jeunesse pour l'instant). Les
notices de l'export Decalog qui ne sont pas encore dans la base (CD, DVD,
jeux, ou simplement livres pas encore enrichis) sont ignorées sans erreur
— ce n'est pas un manque du script, juste hors périmètre pour l'instant.

Les chiffres de prêts sont une PHOTO qui écrase l'ancienne valeur à chaque
import (Decalog ne fournit jamais un delta, seulement un cumul). Pour
pouvoir un jour calculer "combien de prêts depuis le dernier import", ce
script alimente en parallèle la table flux_historique, une ligne par
notice x date d'export.

Usage :
    python3 enrichissement_prets_decalog.py <export_decalog.xls|.xlsx>

Le nom du fichier doit contenir une date au format AAAA-MM-JJ (c'est le
comportement par défaut de Decalog) — cette date est utilisée comme date
de validité des chiffres de prêts, pas la date d'exécution du script.
"""

import os
import re
import sys
import sqlite3
import db

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FICHIER_DB = os.path.join(SCRIPT_DIR, "inventaire.db")

# Colonnes attendues dans l'export Decalog (vérifiées sur un export réel) :
COL_EAN = "EAN / ISBN"
COL_TOTAL = "Nombre de prêts total"
COL_ANNEE_COURANTE = "Nombre de prêts année en cours"
COL_N1 = "Nombre de prêts année N-1"
COL_N2 = "Nombre de prêts année N-2"
COL_N3 = "Nombre de prêts année N-3"
COL_FONCTIONNELS = "Nombre de prêts fonctionnels"
COL_DERNIER_PRET = "Date de dernier prêt"


def extraire_date_export(nom_fichier):
    """Cherche une date AAAA-MM-JJ dans le nom de fichier. Lève une erreur
    explicite si absente plutôt que de deviner silencieusement."""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", nom_fichier)
    if not m:
        raise ValueError(
            f"Impossible de trouver une date (AAAA-MM-JJ) dans le nom de fichier "
            f"'{nom_fichier}'. Decalog nomme ses exports avec une date par défaut "
            f"— vérifie que le fichier n'a pas été renommé."
        )
    return m.group(1)


def normaliser_ean(valeur):
    """Renvoie l'EAN si et seulement s'il est strictement composé de 13
    chiffres. Tout le reste (codes fournisseur jouets, codes internes 'V',
    EAN corrompus) est volontairement écarté plutôt que deviné."""
    if pd.isna(valeur):
        return None
    s = str(valeur).strip()
    if re.fullmatch(r"\d{13}", s):
        return s
    return None


def normaliser_entier(valeur):
    if pd.isna(valeur):
        return None
    s = str(valeur).strip()
    if s in ("", "Aucune donnée disponible"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def normaliser_date_pret(valeur):
    """'25/06/2026 17:44' -> '2026-06-25 17:44'. NULL si absent/illisible."""
    if pd.isna(valeur):
        return None
    s = str(valeur).strip()
    if s in ("", "Aucune donnée disponible"):
        return None
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})(?:\s+(\d{2}:\d{2}))?", s)
    if not m:
        return None
    jour, mois, annee, heure = m.groups()
    return f"{annee}-{mois}-{jour}" + (f" {heure}" if heure else "")


def main():
    if len(sys.argv) != 2:
        print("Usage : python3 enrichissement_prets_decalog.py <export_decalog.xls|.xlsx>")
        sys.exit(1)

    chemin_export = sys.argv[1]
    if not os.path.exists(chemin_export):
        print(f"⚠ Fichier introuvable : {chemin_export}")
        sys.exit(1)

    nom_fichier = os.path.basename(chemin_export)
    date_export = extraire_date_export(nom_fichier)

    print("=" * 70)
    print("  Enrichissement prêts Decalog — Médiathèque d'Arcachon")
    print("=" * 70)
    print(f"\nFichier        : {nom_fichier}")
    print(f"Date des chiffres de prêts : {date_export}")

    extension = os.path.splitext(chemin_export)[1].lower()
    moteur = "xlrd" if extension == ".xls" else "openpyxl"
    print(f"\nLecture du fichier (moteur {moteur})...")
    df = pd.read_excel(chemin_export, engine=moteur, header=None)

    # Détection du format : certains exports ont une ligne vide en tête
    # On cherche la ligne qui contient les vrais en-têtes
    header_row = 0
    for i in range(min(3, len(df))):
        valeurs = [str(v) for v in df.iloc[i].dropna().values]
        if any("barres" in v.lower() or "EAN" in v or "ISBN" in v for v in valeurs):
            header_row = i
            break
    df.columns = df.iloc[header_row]
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    print(f"Lignes lues : {len(df)}")
    print(f"Colonnes détectées : {list(df.columns)}")

    # Détection du format : EPPK par code-barres ou classique par EAN
    COL_CB = "Code-barres de l'exemplaire"
    FORMAT_EPPK = COL_CB in df.columns
    FORMAT_EAN = COL_EAN in df.columns

    if not FORMAT_EPPK and not FORMAT_EAN:
        print(f"\n⚠ Format non reconnu. Colonnes disponibles : {list(df.columns)}")
        sys.exit(1)

    if FORMAT_EPPK:
        print(f"\nFormat détecté : EPPK (prêts par exemplaire, mise à jour par code-barres)")
    else:
        print(f"\nFormat détecté : classique (prêts par titre, mise à jour par EAN)")

    conn = db.connect(FICHIER_DB)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS etat_imports (
            cle TEXT PRIMARY KEY,
            valeur TEXT,
            date_maj TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    cur.execute("SELECT valeur FROM etat_imports WHERE cle = 'date_dernieres_statistiques'")
    row = cur.fetchone()
    date_precedente = row[0] if row else None
    if date_precedente and date_export < date_precedente:
        print(f"\n⚠ ATTENTION : ce fichier est daté du {date_export}, plus ancien que "
              f"les dernières statistiques importées ({date_precedente}). "
              f"Tu importes peut-être le mauvais fichier par erreur.")
    cur.execute("""
        INSERT INTO etat_imports (cle, valeur, date_maj) VALUES ('date_dernieres_statistiques', ?, datetime('now'))
        ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, date_maj = excluded.date_maj
    """, (date_export,))
    conn.commit()

    identifiants_existants = {
        row[0] for row in cur.execute("SELECT identifiant FROM notice").fetchall()
    }
    print(f"Notices déjà en base : {len(identifiants_existants)}")

    rapport = {
        "sans_ean": 0,
        "ean_invalide": 0,
        "doublons_ean_ignores": 0,
        "hors_perimetre": 0,
        "mises_a_jour": 0,
    }

    eans_traites_dans_ce_fichier = set()

    # ── FORMAT EPPK : prêts par exemplaire (code-barres) ──────────────────
    if FORMAT_EPPK:
        COL_PRETS_EX = "Nombre de prêts total (ex)"
        COL_ANNEE_PRET = "Année du dernier prêt"
        codes_barres_existants = {
            row[0] for row in cur.execute("SELECT code_barre_exemplaire FROM exemplaire").fetchall()
        }
        maj_ex = 0
        lot = []
        for _, row in df.iterrows():
            cb = str(row[COL_CB]).strip() if not pd.isna(row[COL_CB]) else None
            if not cb or cb not in codes_barres_existants:
                continue
            nb_prets = int(float(row[COL_PRETS_EX])) if COL_PRETS_EX in df.columns and not pd.isna(row.get(COL_PRETS_EX)) else None
            try:
                annee = str(int(float(row[COL_ANNEE_PRET]))) if COL_ANNEE_PRET in df.columns and not pd.isna(row.get(COL_ANNEE_PRET)) and str(row.get(COL_ANNEE_PRET, '')).strip() not in ('', '-Non Précisé-', 'Non Précisé') else None
            except (ValueError, TypeError):
                annee = None
            lot.append((nb_prets, annee, cb))
            if len(lot) >= 500:
                cur.executemany("UPDATE exemplaire SET nb_prets_total = ?, annee_dernier_pret = ? WHERE code_barre_exemplaire = ?", lot)
                conn.commit()
                maj_ex += len(lot)
                print(f"  {maj_ex}/{len(df)} traités...", end='\r', flush=True)
                lot = []
        if lot:
            cur.executemany("UPDATE exemplaire SET nb_prets_total = ?, annee_dernier_pret = ? WHERE code_barre_exemplaire = ?", lot)
            conn.commit()
            maj_ex += len(lot)

        # Recalculer nb_prets_cet_exemplaire dans vue_inventaire
        # (déjà dans la vue, pas besoin de recalcul séparé)
        print(f"\n--- Rapport EPPK ---")
        print(f"Exemplaires mis à jour avec leurs prêts : {maj_ex}")
        conn.close()
        print("\n" + "=" * 70)
        print("  Import EPPK terminé.")
        print("=" * 70)
        return

    # ── FORMAT CLASSIQUE : prêts par titre (EAN) ──────────────────────────

    for _, row in df.iterrows():
        ean = normaliser_ean(row[COL_EAN])
        if ean is None:
            if pd.isna(row[COL_EAN]):
                rapport["sans_ean"] += 1
            else:
                rapport["ean_invalide"] += 1
            continue

        if ean in eans_traites_dans_ce_fichier:
            rapport["doublons_ean_ignores"] += 1
            continue
        eans_traites_dans_ce_fichier.add(ean)

        if ean not in identifiants_existants:
            rapport["hors_perimetre"] += 1
            continue

        nb_total = normaliser_entier(row[COL_TOTAL])
        nb_annee_courante = normaliser_entier(row[COL_ANNEE_COURANTE]) if COL_ANNEE_COURANTE in df.columns else None
        nb_n1 = normaliser_entier(row[COL_N1]) if COL_N1 in df.columns else None
        nb_n2 = normaliser_entier(row[COL_N2]) if COL_N2 in df.columns else None
        nb_n3 = normaliser_entier(row[COL_N3]) if COL_N3 in df.columns else None
        nb_fonctionnels = normaliser_entier(row[COL_FONCTIONNELS]) if COL_FONCTIONNELS in df.columns else None
        date_dernier_pret = normaliser_date_pret(row[COL_DERNIER_PRET]) if COL_DERNIER_PRET in df.columns else None

        cur.execute("""
            UPDATE notice SET
                nb_prets_total = ?,
                nb_prets_annee_courante = ?,
                nb_prets_n1 = ?,
                nb_prets_n2 = ?,
                nb_prets_n3 = ?,
                nb_prets_fonctionnels = ?,
                date_dernier_pret = ?,
                date_maj_prets = ?
            WHERE identifiant = ?
        """, (nb_total, nb_annee_courante, nb_n1, nb_n2, nb_n3, nb_fonctionnels,
              date_dernier_pret, date_export, ean))

        cur.execute("""
            INSERT INTO flux_historique (identifiant, date_export, nb_prets_total)
            VALUES (?, ?, ?)
            ON CONFLICT(identifiant, date_export) DO UPDATE SET nb_prets_total = excluded.nb_prets_total
        """, (ean, date_export, nb_total))

        rapport["mises_a_jour"] += 1

    conn.commit()

    print("\n--- Rapport ---")
    print(f"Notices mises à jour avec leurs prêts      : {rapport['mises_a_jour']}")
    print(f"Lignes sans EAN du tout                    : {rapport['sans_ean']}")
    print(f"Lignes avec un EAN invalide/non standard   : {rapport['ean_invalide']}")
    print(f"Doublons d'EAN dans ce fichier (ignorés)   : {rapport['doublons_ean_ignores']}")
    print(f"Hors périmètre actuel (pas encore en base) : {rapport['hors_perimetre']}")

    # Vérification rapide : combien de notices restent sans aucune donnée de prêt après cet import ?
    sans_prets = cur.execute(
        "SELECT COUNT(*) FROM notice WHERE nb_prets_total IS NULL"
    ).fetchone()[0]
    jamais_pretes = cur.execute(
        "SELECT COUNT(*) FROM notice WHERE nb_prets_total = 0"
    ).fetchone()[0]
    print(f"\nNotices encore sans donnée de prêt (non trouvées dans cet export) : {sans_prets}")
    print(f"Notices avec 0 prêt enregistré (jamais prêtées)                    : {jamais_pretes}")

    conn.close()
    print("\n" + "=" * 70)
    print(f"  Base mise à jour : {FICHIER_DB}")
    print("=" * 70)


if __name__ == "__main__":
    main()
