#!/usr/bin/env python3
"""
service_backfill_images.py — Comble les couvertures manquantes (image_url)
sur les notices qui alimentent les écrans MAAT (mosaïque + diaporama), pour
que generer_ecrans_maat.py ait suffisamment de titres à afficher chaque
semaine (diagnostic du 2026-07-22 : seuls 369 des 2301 titres récents sur
3 mois avaient une couverture enregistrée -- beaucoup sont des exemplaires
récemment acquis de notices plus anciennes, jamais enrichies côté image).

Même principe que service_backfill_serie_tome.py, supervisé par launchd
(voir com.maat.backfillimages.plist) : régénère sa liste depuis la base à
chaque tour de boucle, retraite par lots via lancer_enrichissement.py
--forcer (n'écrase jamais un champ déjà rempli grâce aux COALESCE), et
s'arrête proprement (code 0) une fois qu'il n'y a plus de notice concernée
sans couverture -- reprise automatique en cas d'interruption, backfill
possiblement long traité sur plusieurs jours sans surveillance.

Portée : uniquement les types qui alimentent les écrans (tout sauf
DVD/JEU/CD -- pas la peine d'aller chercher des couvertures pour des types
qu'on n'affiche de toute façon jamais sur les écrans).

Pas de priorité par catégorie (décision du 2026-07-22) : la rotation à
l'écran de la mosaïque garantit déjà un passage aléatoire et équitable de
tous les titres du pool avant toute répétition (voir nextBookForFlip() /
flipQueue dans mediatheque-cobas-mosaique.html) -- inutile de biaiser
l'ordre de traitement du backfill, ce n'est qu'une question de temps avant
que chaque catégorie ait sa juste part d'images.

Usage direct (sans launchd, pour un test) :
    python3 service_backfill_images.py
"""

import sys
import os
import subprocess
import time
import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LISTE = os.path.join(DOSSIER, "_liste_backfill_images.txt")
LANCEUR = os.path.join(DOSSIER, "lancer_enrichissement.py")

sys.path.insert(0, DOSSIER)
import db  # noqa: E402


def _log(message):
    horodatage = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"[{horodatage}] {message}", flush=True)


def isbns_restants():
    conn = db.connect()
    try:
        lignes = conn.execute(
            """
            SELECT identifiant FROM notice
            WHERE type_document NOT IN ('DVD', 'JEU', 'CD')
              AND (image_url IS NULL OR image_url = '')
              AND identifiant NOT LIKE 'CB:%'
            """
        ).fetchall()
    finally:
        conn.close()
    return [ligne[0] for ligne in lignes]


def main():
    _log("Service de backfill des couvertures démarré (supervisé par launchd).")
    while True:
        try:
            isbns = isbns_restants()
        except Exception as e:
            _log(f"Erreur de lecture base ({e}) -- nouvelle tentative dans 60s.")
            time.sleep(60)
            continue

        if not isbns:
            _log("Backfill terminé -- plus aucune notice éligible sans couverture. Arrêt normal.")
            return 0

        with open(LISTE, "w", encoding="utf-8") as f:
            f.write("\n".join(isbns) + "\n")

        _log(f"{len(isbns)} ISBN restants sans couverture -- lancement d'un lot via lancer_enrichissement.py.")
        resultat = subprocess.run(
            [sys.executable, "-u", LANCEUR, LISTE, "--forcer"],
            cwd=DOSSIER,
        )
        _log(f"Lot terminé (code retour {resultat.returncode}) -- nouvelle vérification de la base.")
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
