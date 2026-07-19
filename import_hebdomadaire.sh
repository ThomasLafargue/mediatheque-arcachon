#!/bin/bash
# import_hebdomadaire.sh — Enchaîne les 4 imports hebdomadaires en une commande.
# Usage : bash import_hebdomadaire.sh
# Les fichiers doivent être dans le dossier inventaire_isbn avant de lancer.

set -e
DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOSSIER"

echo "════════════════════════════════════════════════════"
echo "  Import hebdomadaire — Médiathèque d'Arcachon"
echo "  $(date '+%d/%m/%Y %H:%M')"
echo "════════════════════════════════════════════════════"

# Détecter les fichiers automatiquement
MRC=$(ls "Liste des notices"*.mrc 2>/dev/null | sort | tail -1)
EPPK=$(ls "export-eppk"*.xlsx 2>/dev/null | sort | tail -1)
CSV=$(ls "Donnees_Comptage"*.csv 2>/dev/null | sort | tail -1)

echo ""
echo "Fichiers détectés :"
echo "  .mrc  : ${MRC:-❌ non trouvé}"
echo "  .xlsx : ${EPPK:-❌ non trouvé}"
echo "  .csv  : ${CSV:-❌ non trouvé}"
echo ""

# Import catalogue .mrc
if [ -n "$MRC" ]; then
    echo "── 1/3 Import catalogue : $MRC"
    python3 traiter_fichier.py "$MRC"
else
    echo "⚠ Pas de fichier .mrc — import catalogue ignoré"
fi

# Import EPPK .xlsx
if [ -n "$EPPK" ]; then
    echo ""
    echo "── 2/3 Import prêts EPPK : $EPPK"
    python3 traiter_fichier.py "$EPPK"
else
    echo "⚠ Pas de fichier EPPK — import prêts ignoré"
fi

# Import fréquentation .csv
if [ -n "$CSV" ]; then
    echo ""
    echo "── 3/3 Import fréquentation : $CSV"
    python3 traiter_fichier.py "$CSV"
else
    echo "⚠ Pas de fichier CSV — import fréquentation ignoré"
fi

# Enrichissement des nouvelles notices
echo ""
echo "── Enrichissement des nouvelles notices..."
bash lancement_recherche_initiale.sh

echo ""
echo "── Git push..."
git add -A
git commit -m "Import hebdomadaire $(date '+%Y-%m-%d')" || echo "(rien à commiter)"
git push

echo ""
echo "════════════════════════════════════════════════════"
echo "  ✓ Import terminé — Rebooter l'app Streamlit"
echo "════════════════════════════════════════════════════"
