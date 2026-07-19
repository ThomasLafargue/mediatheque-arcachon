#!/usr/bin/env python3
"""
UNE COMMANDE, N'IMPORTE QUEL FICHIER.

    python3 traiter_fichier.py "n'importe quel fichier Decalog ou fréquentation"

Détecte automatiquement le type (.mrc catalogue / .xlsx-.xls statistiques /
.csv fréquentation), traite, QUALIFIE INTÉGRALEMENT par recherche internet
ce qui peut l'être, puis régénère le tableau xlsx du fonds complet.

Pas de plafond : tout ce qui manque est traité dans la même commande,
jusqu'au bout. Pour un import hebdomadaire de nouveautés (quelques dizaines
de titres), ça reste rapide. Pour un gros volume, prévoir que la commande
tourne longtemps -- voir lancement_recherche_initiale.sh pour le premier
rattrapage du stock existant, pensé pour tourner plusieurs jours sans
surveillance.
"""

import sys
import db
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import actualiser_catalogue
import actualiser_statistiques
import actualiser_frequentation
import lancer_enrichissement
import exporter_fonds


def deviner_type(chemin):
    ext = os.path.splitext(chemin)[1].lower()
    if ext == '.mrc':
        return 'catalogue'
    if ext in ('.xlsx', '.xls'):
        return 'statistiques'
    if ext == '.csv':
        return 'frequentation'
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fichier")
    args = parser.parse_args()

    t = deviner_type(args.fichier)
    if t is None:
        print(f"⚠ Type de fichier non reconnu pour : {args.fichier}")
        print("  Attendu : .mrc (catalogue), .xlsx/.xls (statistiques) ou .csv (fréquentation)")
        sys.exit(1)

    print(f"Fichier reconnu comme : {t}\n")

    if t == 'catalogue':
        sys.argv = ['actualiser_catalogue.py', args.fichier]
        actualiser_catalogue.main()
    elif t == 'statistiques':
        sys.argv = ['actualiser_statistiques.py', args.fichier]
        actualiser_statistiques.main()
    elif t == 'frequentation':
        sys.argv = ['actualiser_frequentation.py', args.fichier]
        actualiser_frequentation.main()

    dossier = os.path.dirname(os.path.abspath(__file__))

    import sqlite3
    conn = db.connect(actualiser_catalogue.FICHIER_DB)
    cur = conn.cursor()
    cur.execute("SELECT identifiant FROM notice WHERE type_document='LIVRE' AND categorie IS NULL ORDER BY identifiant")
    sans_rien = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT identifiant FROM notice WHERE type_document='LIVRE' AND categorie IS NOT NULL AND genre IS NULL ORDER BY identifiant")
    genre_seul = [r[0] for r in cur.fetchall()]
    conn.close()

    with open(os.path.join(dossier, "liste_isbn_a_enrichir.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sans_rien) + "\n")
    with open(os.path.join(dossier, "liste_isbn_genre_seul.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(genre_seul) + "\n")

    a_traiter = sans_rien + genre_seul
    if a_traiter:
        print(f"\nQualification automatique par recherche internet ({len(a_traiter)} ISBN)...")
        with open(os.path.join(dossier, "_lot_synchrone.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(a_traiter) + "\n")
        sys.argv = ['lancer_enrichissement.py', os.path.join(dossier, "_lot_synchrone.txt")]
        lancer_enrichissement.main()
        os.remove(os.path.join(dossier, "_lot_synchrone.txt"))
    else:
        print("\nRien à qualifier par recherche internet pour cet import.")

    print("\nGénération du tableau xlsx à jour...")
    exporter_fonds.exporter()

    print(f"\n✓ Base et tableau xlsx à jour et prêts à être fournis.")


if __name__ == "__main__":
    main()
