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
# (motif "Liste des notices - " avec le tiret : exclut volontairement les
# éventuels exports "Liste des notices mosaique - ...", qui sont un fichier
# distinct et ne doivent pas être pris pour une ancienne version à supprimer)
MRC=$(ls "Liste des notices - "*.mrc 2>/dev/null | sort | tail -1)
EPPK=$(ls "export-eppk"*.xlsx 2>/dev/null | sort | tail -1)
CSV=$(ls "Donnees_Comptage"*.csv 2>/dev/null | sort | tail -1)

echo ""
echo "Fichiers détectés :"
echo "  .mrc  : ${MRC:-❌ non trouvé}"
echo "  .xlsx : ${EPPK:-❌ non trouvé}"
echo "  .csv  : ${CSV:-❌ non trouvé}"
echo ""

# Supprime les anciens fichiers d'un motif donné, en gardant uniquement
# celui qu'on vient de traiter (les fichiers sont datés -- on ne garde
# que la semaine courante pour ne pas ré-accumuler des centaines de Mo).
nettoyer_anciens() {
    motif="$1"
    fichier_garde="$2"
    for f in $motif; do
        [ -f "$f" ] || continue
        [ "$f" = "$fichier_garde" ] && continue
        rm -f "$f"
        echo "  (ancien fichier supprimé : $f)"
    done
}

# Import catalogue .mrc
if [ -n "$MRC" ]; then
    echo "── 1/3 Import catalogue : $MRC"
    python3 traiter_fichier.py "$MRC"
    nettoyer_anciens "Liste des notices - "*.mrc "$MRC"
else
    echo "⚠ Pas de fichier .mrc — import catalogue ignoré"
fi

# Import EPPK .xlsx
if [ -n "$EPPK" ]; then
    echo ""
    echo "── 2/3 Import prêts EPPK : $EPPK"
    python3 traiter_fichier.py "$EPPK"
    nettoyer_anciens "export-eppk"*.xlsx "$EPPK"
else
    echo "⚠ Pas de fichier EPPK — import prêts ignoré"
fi

# Import fréquentation .csv
if [ -n "$CSV" ]; then
    echo ""
    echo "── 3/3 Import fréquentation : $CSV"
    python3 traiter_fichier.py "$CSV"
    nettoyer_anciens "Donnees_Comptage"*.csv "$CSV"
else
    echo "⚠ Pas de fichier CSV — import fréquentation ignoré"
fi

# Chaque import ci-dessus régénère "Fonds Arcachon - AAAA-MM-JJ.xlsx" (tableau
# complet du fonds, lisible par n'importe quel agent) -- on ne garde que le
# plus récent, une fois que les 3 imports sont passés.
DERNIER_FONDS=$(ls "Fonds Arcachon"*.xlsx 2>/dev/null | sort | tail -1)
if [ -n "$DERNIER_FONDS" ]; then
    nettoyer_anciens "Fonds Arcachon"*.xlsx "$DERNIER_FONDS"
fi

# Enrichissement des nouvelles notices
#
# Corrigé le 2026-07-26 : ce script lançait auparavant son PROPRE
# enrichissement (lancement_recherche_initiale.sh, en nohup), ce qui faisait
# tourner DEUX enrichisseurs en parallèle quand le service launchd
# com.maat.enrichissementseries était actif -- donc deux processus écrivant
# en même temps dans la base. Désormais le service est le seul enrichisseur :
# on se contente de le (re)démarrer, et il prend en charge aussi bien les
# notices nouvelles que la campagne série en cours.
echo ""
echo "── Enrichissement des nouvelles notices..."
PLIST_ENRICH="$HOME/Library/LaunchAgents/com.maat.enrichissementseries.plist"
if [ -f "$PLIST_ENRICH" ]; then
    # kickstart relance le service s'il dormait (il s'arrête tout seul quand
    # il n'a plus rien à traiter) ; -k le redémarre s'il tourne déjà.
    launchctl kickstart -k "gui/$(id -u)/com.maat.enrichissementseries" 2>/dev/null \
      || launchctl bootstrap "gui/$(id -u)" "$PLIST_ENRICH" 2>/dev/null
    echo "  Service d'enrichissement (re)lancé — il traitera les nouvelles notices"
    echo "  en tâche de fond. Suivi : tail -f /tmp/journal_enrichissement_series.log"
else
    echo "  Service launchd absent — repli sur le lancement direct."
    bash lancement_recherche_initiale.sh
fi

# Écrans MAAT (mosaïque hall + diaporama jeunesse) : régénérés depuis la
# base à jour, puis envoyés automatiquement sur OVH si les identifiants
# SFTP sont renseignés dans .env (sinon fichiers générés en local, à
# pousser via Cyberduck comme avant).
echo ""
echo "── Mise à jour des écrans MAAT (mosaïque + diaporama)..."
python3 generer_ecrans_maat.py || echo "⚠ Génération des écrans MAAT échouée -- import du catalogue non affecté"

echo ""
echo "── Git push..."
git add -A
git commit -m "Import hebdomadaire $(date '+%Y-%m-%d')" || echo "(rien à commiter)"
git push

echo ""
echo "════════════════════════════════════════════════════"
echo "  ✓ Import terminé — Rebooter l'app Streamlit"
echo "════════════════════════════════════════════════════"
