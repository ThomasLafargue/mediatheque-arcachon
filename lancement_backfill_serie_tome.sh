#!/bin/bash
# Backfill ciblé : repasse dans le moteur à 11 sites les notices déjà
# enrichies AVANT le fix du 2026-07-22 (serie/tome calculés par le moteur
# mais jamais écrits en base). Ne retraite QUE les notices encore sans
# serie/tome -- pas tout le fonds.
#
# ATTENTION : ce lancement en nohup+caffeinate ne survit PAS à un
# redémarrage macOS (mise à jour automatique, coupure de courant...). Pour
# un run de plusieurs jours qui doit résister à ça, utiliser à la place le
# service supervisé par launchd : voir service_backfill_serie_tome.py et
# com.maat.backfillserietome.plist (relance automatique en cas d'arrêt
# anormal, y compris après un redémarrage si la session est rouverte).
# Ce script .sh reste utile pour un test ponctuel rapide ou un petit lot.
#
# Usage : bash lancement_backfill_serie_tome.sh

DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOSSIER"

echo "Génération de la liste des ISBN sans serie/tome depuis la base..."
python3 << 'PYEOF2'
import db
conn = db.connect()
r = conn.execute("""
    SELECT identifiant FROM notice
    WHERE type_document = 'LIVRE' AND serie IS NULL AND tome IS NULL
      AND identifiant NOT LIKE 'CB:%'
""").fetchall()
with open('_liste_backfill_serie_tome.txt', 'w') as f:
    for row in r:
        f.write(row[0] + '\n')
print(len(r), 'ISBN à retraiter (déjà enrichis, mais sans serie/tome)')
PYEOF2

TOTAL=$(wc -l < _liste_backfill_serie_tome.txt | tr -d ' ')
echo "Lancement du backfill sur $TOTAL ISBN (--forcer, ré-enrichissement complet via le moteur à 11 sites)..."
echo "Tu peux fermer Terminal, ça continue de tourner."
echo ""

nohup caffeinate -i python3 -u lancer_enrichissement.py _liste_backfill_serie_tome.txt --forcer > journal_backfill_serie_tome.log 2>&1 &

echo "Lancé (PID $!). Suivi : tail -f $DOSSIER/journal_backfill_serie_tome.log"
echo "Vérifier : ps -p $!"
echo ""
echo "Si interrompu, relance simplement ce même script : il régénère la liste"
echo "depuis la base, donc les notices déjà corrigées ne seront plus retraitées."
