#!/bin/bash
# veille_hebdomadaire.sh — Lance toutes les veilles d'acquisition en une fois.
# Conçu pour être exécuté automatiquement chaque semaine par launchd
# (voir com.maat.veillehebdo.plist), mais lançable à la main pour tester :
#     bash veille_hebdomadaire.sh
#
# Chaque veille alimente la même table suggestion_acquisition (demandeur
# "Veille automatique"), sans jamais créer de doublon d'une semaine à
# l'autre. Le résultat est ensuite consultable directement depuis le chat
# ("montre-moi les suggestions de la veille automatique") ou exportable.
#
# Tolérant aux pannes : si une source est momentanément inaccessible, les
# autres tournent quand même (|| true), et rien n'est jamais supprimé.

DOSSIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DOSSIER"

HORODATAGE="$(date '+%Y-%m-%d %H:%M')"
echo "════════════════════════════════════════════════════"
echo "  Veille acquisitions jeunesse — $HORODATAGE"
echo "════════════════════════════════════════════════════"

echo ""
echo "── 1/3 Nouveautés éditeurs (flux BnF)..."
python3 veille_nouveautes_editeurs.py || echo "⚠ Veille BnF échouée (sans effet sur les autres)."

echo ""
echo "── 2/3 Critiques jeunesse Ricochet (dont BD & manga)..."
python3 veille_ricochet.py || echo "⚠ Veille Ricochet échouée (sans effet sur les autres)."

echo ""
echo "── 3/4 Coups de cœur des libraires (Place des Libraires)..."
# Curation professionnelle de libraires indépendants, données Dilicom.
# Seule veille dont le rapprochement avec le fonds est EXACT (par ISBN).
python3 veille_place_des_libraires.py || echo "⚠ Veille Place des Libraires échouée (sans effet sur les autres)."

echo ""
echo "── 4/4 Prix littéraires jeunesse (Sorcières, Incorruptibles)..."
# Idempotent : ne ré-ajoute jamais un titre déjà suggéré. Utile chaque
# semaine pour que toute mise à jour de la liste de référence soit
# immédiatement répercutée, même si la liste elle-même ne change que 1 à
# 2 fois par an.
python3 veille_prix_litteraires.py || echo "⚠ Veille prix littéraires échouée (sans effet sur les autres)."

echo ""
echo "════════════════════════════════════════════════════"
echo "  ✓ Veille terminée — suggestions consultables dans le chat"
echo "════════════════════════════════════════════════════"
