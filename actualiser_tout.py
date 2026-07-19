#!/usr/bin/env python3
"""
UNE SEULE COMMANDE pour tout actualiser : catalogue + statistiques +
fréquentation, fusion, nettoyage et qualification automatique incluse.

Usage :
    python3 actualiser_tout.py "Liste des notices.mrc" "export-eppk.xlsx" "Donnees_Comptage.csv"

Les trois fichiers sont optionnels et peuvent être donnés dans n'importe quel
ordre (détectés automatiquement par leur extension) -- utile si tu n'as
qu'un ou deux fichiers à actualiser ce jour-là.

Ce que fait cette commande, dans l'ordre, sans aucune autre intervention :
  1. Catalogue (.mrc)  -> fusion notices/exemplaires, normalisation des
     séries, qualification automatique categorie/genre/public depuis les
     classifications déjà présentes dans Decalog (champ 686).
  2. Statistiques (.xlsx) -> prêts (total, N, N-1, N-2, N-3, dernier prêt).
  3. Fréquentation (.csv) -> entrées/jour.

Ce qui N'EST PAS inclus ici, volontairement : l'enrichissement par le
moteur de recherche multi-sources (lancer_enrichissement.py). C'est la
seule étape qui dépend d'internet et prend du temps réel (plusieurs
secondes par ISBN, pour des milliers d'ISBN) -- l'inclure ici forcerait à
attendre des heures à chaque actualisation, même pour un simple
rafraîchissement mensuel des prêts. Cette commande te dira à la fin combien
de livres ont encore besoin de cette étape.
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import actualiser_catalogue
import actualiser_statistiques
import actualiser_frequentation


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
    parser.add_argument("fichiers", nargs='+', help="Les fichiers à traiter, dans n'importe quel ordre")
    args = parser.parse_args()

    plan = {'catalogue': None, 'statistiques': None, 'frequentation': None}
    for chemin in args.fichiers:
        t = deviner_type(chemin)
        if t is None:
            print(f"⚠ Type de fichier non reconnu, ignoré : {chemin}")
            continue
        plan[t] = chemin

    if plan['catalogue']:
        print("=" * 70)
        print("ÉTAPE 1/3 — CATALOGUE")
        print("=" * 70)
        sys.argv = ['actualiser_catalogue.py', plan['catalogue']]
        actualiser_catalogue.main()
        print()

    if plan['statistiques']:
        print("=" * 70)
        print("ÉTAPE 2/3 — STATISTIQUES DE PRÊT")
        print("=" * 70)
        sys.argv = ['actualiser_statistiques.py', plan['statistiques']]
        actualiser_statistiques.main()
        print()

    if plan['frequentation']:
        print("=" * 70)
        print("ÉTAPE 3/3 — FRÉQUENTATION")
        print("=" * 70)
        sys.argv = ['actualiser_frequentation.py', plan['frequentation']]
        actualiser_frequentation.main()
        print()

    # --- Bilan final : qu'est-ce qu'il reste pour le moteur de recherche ? ---
    import sqlite3
    conn = sqlite3.connect(actualiser_catalogue.FICHIER_DB)
    cur = conn.cursor()
    cur.execute("SELECT identifiant FROM notice WHERE type_document='LIVRE' AND categorie IS NULL ORDER BY identifiant")
    sans_rien = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT identifiant FROM notice WHERE type_document='LIVRE' AND categorie IS NOT NULL AND genre IS NULL ORDER BY identifiant")
    genre_seul = [r[0] for r in cur.fetchall()]
    conn.close()

    dossier = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(dossier, "liste_isbn_a_enrichir.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sans_rien) + "\n")
    with open(os.path.join(dossier, "liste_isbn_genre_seul.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(genre_seul) + "\n")

    print("=" * 70)
    print("  BASE ACTUALISÉE -- prête pour l'outil conversationnel")
    print("=" * 70)
    print(f"  Livres encore sans aucune qualification : {len(sans_rien)} "
          f"(-> liste_isbn_a_enrichir.txt, priorité)")
    print(f"  Livres avec catégorie mais sans genre    : {len(genre_seul)} "
          f"(-> liste_isbn_genre_seul.txt, secondaire)")
    if sans_rien or genre_seul:
        print("\n  Pour les qualifier : python3 lancer_enrichissement.py liste_isbn_a_enrichir.txt --limite 200")


if __name__ == "__main__":
    main()
