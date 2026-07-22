#!/usr/bin/env python3
"""
service_backfill_serie_tome.py — Version robuste de lancement_backfill_serie_tome.sh,
conçue pour tourner plusieurs jours sans jamais s'arrêter durablement.

Différence avec le script .sh d'origine : celui-ci génère la liste UNE fois
puis lance un process détaché (nohup) -- si ce process est tué pour
n'importe quelle raison (fermeture de session, redémarrage macOS, crash),
rien ne le relance. Ce script-ci est fait pour être supervisé par launchd
(voir com.maat.backfillserietome.plist) : à chaque démarrage il régénère
sa propre liste depuis la base, retraite tout ce qui manque encore par
lots, et boucle jusqu'à ce qu'il n'y ait plus rien à faire -- moment où il
se termine proprement (code 0). launchd est configuré pour le relancer
automatiquement en cas d'arrêt anormal (code non nul), mais pas quand il
se termine normalement (backfill fini).

Comme lancer_enrichissement.py est appelé en sous-processus à chaque tour
de boucle, une interruption brutale ne fait perdre au pire que le lot en
cours (quelques dizaines d'ISBN) -- la reprise se fait automatiquement au
prochain lancement puisque la liste est régénérée depuis la base à chaque
fois (seules les notices encore sans serie/tome y figurent).

Usage direct (sans launchd, pour un test) :
    python3 service_backfill_serie_tome.py
"""

import sys
import os
import subprocess
import time
import datetime

DOSSIER = os.path.dirname(os.path.abspath(__file__))
LISTE = os.path.join(DOSSIER, "_liste_backfill_serie_tome.txt")
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
            WHERE type_document = 'LIVRE' AND serie IS NULL AND tome IS NULL
              AND identifiant NOT LIKE 'CB:%'
            """
        ).fetchall()
    finally:
        conn.close()
    return [ligne[0] for ligne in lignes]


def main():
    _log("Service de backfill démarré (supervisé par launchd).")
    while True:
        try:
            isbns = isbns_restants()
        except Exception as e:
            _log(f"Erreur de lecture base ({e}) -- nouvelle tentative dans 60s.")
            time.sleep(60)
            continue

        if not isbns:
            _log("Backfill terminé -- plus aucune notice LIVRE sans serie/tome. Arrêt normal.")
            return 0

        with open(LISTE, "w", encoding="utf-8") as f:
            f.write("\n".join(isbns) + "\n")

        _log(f"{len(isbns)} ISBN restants -- lancement d'un lot via lancer_enrichissement.py.")
        resultat = subprocess.run(
            [sys.executable, "-u", LANCEUR, LISTE, "--forcer"],
            cwd=DOSSIER,
        )
        _log(f"Lot terminé (code retour {resultat.returncode}) -- nouvelle vérification de la base.")
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
