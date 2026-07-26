#!/usr/bin/env python3
"""
exporter_corrections_decalog.py — Tableau Excel des fiches Decalog mal
renseignées, avec le champ concerné et la valeur à saisir.

PRINCIPE : notre moteur d'enrichissement complète les champs que Decalog a
laissés vides (série, tome, catégorie, genre, public visé...). Ces déductions
vivent dans NOTRE base, mais Decalog, lui, reste incomplet. Ce script produit
la liste de travail pour corriger Decalog à la source — ce qui bénéficie
ensuite à tout le réseau COBAS, pas seulement à notre outil.

DEUX FAMILLES DE CORRECTIONS
  1. Champs déduits par notre moteur (colonne champs_a_verifier_decalog) :
     on connaît la valeur à saisir, il n'y a qu'à la recopier.
  2. Champs manquants sans déduction possible : on les signale quand même,
     car ce sont des trous à combler manuellement.

Une feuille Excel par type de correction, pour pouvoir répartir le travail
entre agents.

N'ÉCRIT RIEN EN BASE ni dans Decalog : c'est une liste de travail.

Usage :
    python3 exporter_corrections_decalog.py
    python3 exporter_corrections_decalog.py --jeunesse   (fonds jeunesse seul)
    python3 exporter_corrections_decalog.py --max 500
"""

import datetime
import os
import sys

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
import db  # noqa: E402

LIBELLES = {
    "serie": "Série",
    "tome": "Tome",
    "categorie": "Catégorie",
    "genre": "Genre",
    "public_vise": "Public visé",
    "pegi": "PEGI",
    "dewey": "Dewey",
}


def recuperer(jeunesse_seule=False, maxi=None):
    conn = db.connect()
    filtre_jeunesse = (
        " AND n.public_vise IN ('Jeune','Jeunesse','Ado (12+)','Adolescent') "
        if jeunesse_seule else ""
    )
    try:
        # 1. Champs DÉDUITS par notre moteur : la valeur à saisir est connue
        deduits = conn.execute(
            "SELECT n.identifiant, n.titre, n.createurs, n.date_publication, "
            "       n.champs_a_verifier_decalog, n.serie, n.tome, n.categorie, "
            "       n.genre, n.public_vise, e.cote "
            "FROM notice n LEFT JOIN exemplaire e ON n.identifiant = e.identifiant "
            "WHERE n.champs_a_verifier_decalog IS NOT NULL "
            "  AND n.champs_a_verifier_decalog != ''" + filtre_jeunesse +
            " ORDER BY e.cote"
        ).fetchall()

        # 2. Notices sans EAN (identifiant substitut CB:) : invisibles à toute
        #    recherche par ISBN tant que Decalog n'est pas corrigé
        sans_ean = conn.execute(
            "SELECT n.identifiant, n.titre, n.createurs, n.date_publication, e.cote "
            "FROM notice n LEFT JOIN exemplaire e ON n.identifiant = e.identifiant "
            "WHERE n.identifiant LIKE 'CB:%' AND n.type_document = 'LIVRE' "
            "  AND CAST(SUBSTR(n.date_publication,1,4) AS INTEGER) >= 2000"
            + filtre_jeunesse + " ORDER BY n.date_publication DESC"
        ).fetchall()
    finally:
        conn.close()

    lignes_deduits, vus = [], set()
    for (ident, titre, auteur, date_pub, champs, serie, tome,
         categorie, genre, public, cote) in deduits:
        if ident in vus:
            continue
        vus.add(ident)
        valeurs = {"serie": serie, "tome": tome, "categorie": categorie,
                   "genre": genre, "public_vise": public}
        for champ in [c.strip() for c in (champs or "").split(",") if c.strip()]:
            lignes_deduits.append({
                "Cote": cote or "",
                "ISBN / identifiant": ident,
                "Titre": titre or "",
                "Auteur": auteur or "",
                "Année": (date_pub or "")[:4],
                "Champ à corriger": LIBELLES.get(champ, champ),
                "Valeur à saisir dans Decalog": valeurs.get(champ) or "",
            })

    lignes_sans_ean, vus2 = [], set()
    for ident, titre, auteur, date_pub, cote in sans_ean:
        if ident in vus2:
            continue
        vus2.add(ident)
        lignes_sans_ean.append({
            "Cote": cote or "",
            "Identifiant actuel": ident,
            "Titre": titre or "",
            "Auteur": auteur or "",
            "Année": (date_pub or "")[:4],
            "Champ à corriger": "EAN / ISBN",
            "Valeur à saisir dans Decalog": "(à retrouver — voir "
                                            "retrouver_ean_manquants.py)",
        })

    if maxi:
        lignes_deduits = lignes_deduits[:maxi]
        lignes_sans_ean = lignes_sans_ean[:maxi]
    return lignes_deduits, lignes_sans_ean


def ecrire_feuille(ws, lignes, titre_feuille):
    from openpyxl.styles import Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter
    if not lignes:
        ws.cell(row=1, column=1, value="(aucune ligne)")
        return
    colonnes = list(lignes[0].keys())
    thin = Side(style="thin", color="D9E2F0")
    bordure = Border(left=thin, right=thin, top=thin, bottom=thin)
    for c, nom in enumerate(colonnes, 1):
        cell = ws.cell(row=1, column=c, value=nom)
        cell.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2E4A7A")
        cell.border = bordure
        largeur = 40 if "Titre" in nom or "Valeur" in nom else 20
        ws.column_dimensions[get_column_letter(c)].width = largeur
    for i, ligne in enumerate(lignes, start=2):
        for c, nom in enumerate(colonnes, 1):
            cell = ws.cell(row=i, column=c, value=ligne[nom])
            cell.font = Font(name="Arial", size=9.5)
            cell.border = bordure
    ws.freeze_panes = "A2"


def main():
    jeunesse = "--jeunesse" in sys.argv
    maxi = None
    if "--max" in sys.argv:
        try:
            maxi = int(sys.argv[sys.argv.index("--max") + 1])
        except (IndexError, ValueError):
            pass

    print("═══ Fiches Decalog à corriger ═══\n")
    deduits, sans_ean = recuperer(jeunesse, maxi)
    print(f"  {len(deduits)} correction(s) avec valeur connue "
          f"(série, tome, catégorie... déduites par notre moteur)")
    print(f"  {len(sans_ean)} notice(s) sans EAN à retrouver\n")

    if deduits:
        from collections import Counter
        c = Counter(d["Champ à corriger"] for d in deduits)
        print("  Répartition par champ :")
        for champ, n in c.most_common():
            print(f"    {n:6}  {champ}")

    from openpyxl import Workbook
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Valeur connue"
    ecrire_feuille(ws1, deduits, "Valeur connue")
    ws2 = wb.create_sheet("EAN manquant")
    ecrire_feuille(ws2, sans_ean, "EAN manquant")

    suffixe = "_jeunesse" if jeunesse else ""
    sortie = os.path.join(
        DOSSIER,
        f"Corrections_Decalog{suffixe}_{datetime.date.today().isoformat()}.xlsx")
    wb.save(sortie)
    print(f"\n✓ Export : {os.path.basename(sortie)}")
    print("  Feuille 1 « Valeur connue » : il n'y a qu'à recopier dans Decalog.")
    print("  Feuille 2 « EAN manquant »  : ISBN à retrouver.")


if __name__ == "__main__":
    main()
