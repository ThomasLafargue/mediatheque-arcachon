#!/usr/bin/env python3
"""
Point d'entrée de la tâche de fond automatique. Conçu pour être lancé
périodiquement par launchd (voir installer_tache_de_fond.sh) -- jamais à la
main. Traite un petit lot à chaque passage : priorité à
liste_isbn_a_enrichir.txt, puis bascule automatiquement sur
liste_isbn_genre_seul.txt une fois la première épuisée.
"""

import os
import sys
import datetime
import sqlite3
import db

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
import lancer_enrichissement as moteur
import exporter_fonds

LOT_PAR_PASSAGE = 30  # volontairement modeste : ça tourne plusieurs fois par jour


def reste_a_faire(fichier_liste):
    chemin = os.path.join(DOSSIER, fichier_liste)
    if not os.path.exists(chemin):
        return []
    with open(chemin, encoding="utf-8") as f:
        isbns = [l.strip() for l in f if l.strip()]
    conn = db.connect(moteur.FICHIER_DB)
    cur = conn.cursor()
    cur.execute("SELECT identifiant FROM notice WHERE date_enrichissement IS NOT NULL")
    deja_fait = {r[0] for r in cur.fetchall()}
    conn.close()
    return [i for i in isbns if i not in deja_fait]


def main():
    horodatage = datetime.datetime.now().isoformat(timespec='seconds')
    print(f"\n[{horodatage}] Passage de la tâche de fond")

    a_traite = False
    for fichier in ("liste_isbn_a_enrichir.txt", "liste_isbn_genre_seul.txt"):
        restants = reste_a_faire(fichier)
        if restants:
            print(f"  {len(restants)} ISBN restants dans {fichier} -- traitement de {min(LOT_PAR_PASSAGE, len(restants))}")
            sys.argv = ['lancer_enrichissement.py', os.path.join(DOSSIER, fichier), '--limite', str(LOT_PAR_PASSAGE)]
            moteur.main()
            a_traite = True
            break

    if not a_traite:
        print("  Rien à faire -- les deux listes sont à jour.")

    # Le xlsx doit rester à jour à tout moment, même entre deux imports,
    # puisqu'un agent peut le demander à n'importe quel moment.
    exporter_fonds.exporter()


if __name__ == "__main__":
    main()
