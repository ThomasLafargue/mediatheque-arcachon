#!/bin/bash
# À lancer UNE SEULE FOIS pour activer la tâche de fond automatique.
# Ensuite, plus rien à faire : ton Mac s'occupe seul de l'enrichissement,
# toutes les 30 minutes, même si tu ne lances jamais Terminal.
#
# Usage : bash installer_tache_de_fond.sh

set -e
DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_SRC="$DOSSIER/fr.arcachon.mediatheque.enrichissement.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/fr.arcachon.mediatheque.enrichissement.plist"

mkdir -p "$HOME/Library/LaunchAgents"

# Remplace __DOSSIER__ par le vrai chemin absolu, et copie au bon endroit
sed "s|__DOSSIER__|$DOSSIER|g" "$PLIST_SRC" > "$PLIST_DEST"

# Désactive une éventuelle version précédente avant de recharger
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "✓ Tâche de fond installée et activée."
echo "  Elle tournera désormais toutes les 30 minutes, automatiquement,"
echo "  même après un redémarrage du Mac. Rien d'autre à faire."
echo ""
echo "  Pour vérifier qu'elle tourne :"
echo "    cat '$DOSSIER/journal_tache_de_fond.log'"
echo ""
echo "  Pour l'arrêter un jour si besoin :"
echo "    launchctl unload '$PLIST_DEST'"
