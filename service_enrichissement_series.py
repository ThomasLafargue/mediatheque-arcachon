#!/usr/bin/env python3
"""
service_enrichissement_series.py — Enrichit les notices LIVRE encore sans
série, en tâche de fond supervisée par launchd
(voir com.maat.enrichissementseries.plist).

Pourquoi ce service (2026-07-25) :
  - le lancement manuel précédent s'est arrêté au bout de ~48 notices
    (terminal fermé / veille du Mac) : sur ~18 000 notices, il faut une
    exécution qui survive à tout ;
  - il tournait avec l'ANCIEN ordre de sources, où les 4 premières (Amazon,
    Fnac, BDfugue, Manga News) sont bloquées et coûtaient jusqu'à 20 s de
    timeout chacune avant d'atteindre une source vivante. Le nouvel ordre
    (Place des Libraires, Cultura, Open Library, BnF en tête) est bien plus
    rapide ET plus complet.

TERMINAISON GARANTIE — leçon du backfill série/tome précédent :
on ne peut pas boucler sur « notices sans série », car un livre qui n'a
légitimement aucune série (roman indépendant, album unique) n'en sortira
JAMAIS : le service tournerait indéfiniment en retraitant les mêmes. On tient
donc un fichier des ISBN DÉJÀ TENTÉS dans cette campagne, et on s'arrête quand
tout a été tenté une fois.

Reprise : l'avancement est sur disque, donc une interruption (crash, veille,
redémarrage) ne fait perdre au pire que le lot en cours.

Usage direct (test) :
    python3 service_enrichissement_series.py
"""

import datetime
import os
import subprocess
import sys
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
import db  # noqa: E402

LISTE_LOT = os.path.join(DOSSIER, "_lot_series_en_cours.txt")
DEJA_TENTES = os.path.join(DOSSIER, "_series_deja_tentees.txt")
LANCEUR = os.path.join(DOSSIER, "lancer_enrichissement.py")

TAILLE_LOT = 200  # ~200 notices par lot : point de reprise fréquent


def _log(message):
    horodatage = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"[{horodatage}] {message}", flush=True)


def charger_deja_tentes():
    if not os.path.exists(DEJA_TENTES):
        return set()
    with open(DEJA_TENTES, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def ajouter_deja_tentes(isbns):
    with open(DEJA_TENTES, "a", encoding="utf-8") as f:
        for i in isbns:
            f.write(i + "\n")


def isbns_a_enrichir():
    """Notices à traiter, deux cas réunis (corrigé le 2026-07-26) :

      1. JAMAIS ENRICHIES (date_enrichissement NULL), tous types confondus --
         typiquement les notices nouvelles arrivées par l'import hebdomadaire ;
      2. LIVRES SANS SÉRIE, pour la campagne de rattrapage en cours.

    Cette fusion est volontaire : auparavant, l'import hebdomadaire lançait
    SON PROPRE enrichissement (via lancement_recherche_initiale.sh) pendant
    que ce service tournait -- deux processus écrivaient donc en même temps
    dans la base. Désormais ce service est le SEUL enrichisseur, et l'import
    se contente de le relancer.
    """
    conn = db.connect()
    try:
        lignes = conn.execute(
            "SELECT identifiant FROM notice "
            "WHERE identifiant NOT LIKE 'CB:%' AND ("
            "      date_enrichissement IS NULL"
            "   OR (type_document='LIVRE' AND (serie IS NULL OR serie=''))"
            ")"
        ).fetchall()
    finally:
        conn.close()
    return [l[0] for l in lignes]


def main():
    _log("Service d'enrichissement des séries démarré (supervisé par launchd).")
    _log(f"Ordre des sources : Place des Libraires, Cultura, Open Library, BnF en tête.")

    while True:
        try:
            restants = isbns_a_enrichir()
        except Exception as e:
            _log(f"Erreur de lecture base ({e}) -- nouvelle tentative dans 60 s.")
            time.sleep(60)
            continue

        deja = charger_deja_tentes()
        a_faire = [i for i in restants if i not in deja]

        if not a_faire:
            _log(f"Campagne terminée : les {len(deja)} notices visées ont toutes été "
                 f"tentées une fois. Il reste {len(restants)} notices sans série "
                 f"(livres sans série réelle, ou séries introuvables sur les sources). "
                 f"Arrêt normal.")
            return 0

        lot = a_faire[:TAILLE_LOT]
        with open(LISTE_LOT, "w", encoding="utf-8") as f:
            f.write("\n".join(lot) + "\n")

        _log(f"{len(a_faire)} notices restant à tenter -- lot de {len(lot)} en cours "
             f"(déjà tentées : {len(deja)}).")
        resultat = subprocess.run(
            [sys.executable, "-u", LANCEUR, LISTE_LOT, "--forcer"],
            cwd=DOSSIER,
        )
        # On marque le lot comme tenté même en cas d'échec partiel : sinon on
        # rejouerait indéfiniment les ISBN que les sources ne connaissent pas.
        ajouter_deja_tentes(lot)
        _log(f"Lot terminé (code retour {resultat.returncode}).")
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
