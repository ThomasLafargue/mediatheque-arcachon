#!/bin/bash
# Lance le traitement de toutes les notices non encore enrichies depuis la base.
# Usage : bash lancement_recherche_initiale.sh

DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOSSIER"

echo "Generation de la liste des ISBN a enrichir depuis la base..."
python3 << 'PYEOF2'
import db
conn = db.connect()
r = conn.execute("SELECT identifiant FROM notice WHERE date_enrichissement IS NULL AND identifiant NOT LIKE 'CB:%'").fetchall()
with open('_stock_initial_complet.txt', 'w') as f:
    for row in r:
        f.write(row[0] + '\n')
print(len(r), 'ISBN a traiter')
PYEOF2

TOTAL=$(wc -l < _stock_initial_complet.txt | tr -d ' ')
echo "Lancement du traitement de $TOTAL ISBN..."
echo "Tu peux fermer Terminal, ca continue de tourner."
echo ""

nohup caffeinate -i python3 -u lancer_enrichissement.py _stock_initial_complet.txt > journal_recherche_initiale.log 2>&1 &

echo "Lance (PID $!). Suivi : tail -f $DOSSIER/journal_recherche_initiale.log"
echo "Verifier : ps -p $!"
