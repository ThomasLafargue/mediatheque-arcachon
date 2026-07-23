#!/usr/bin/env python3
"""
veille_ricochet.py — Veille des nouveautés / dernières critiques jeunesse
publiées par Ricochet (ricochet-jeunes.org), via son flux RSS officiel.

Pourquoi Ricochet en particulier (2026-07-23) : c'est la seule des sources
"historiques" du moteur d'enrichissement (moteur_recherche.py) qui soit une
plateforme critique spécialisée jeunesse, et non un simple site marchand.
Elle couvre en plus les DEUX segments que les prix littéraires (Sorcières,
Incorruptibles) laissent de côté : la BD jeunesse et le manga jeunesse.
Contrairement aux sites marchands (Fnac, Amazon, Cultura, Decitre...), dont
la page "nouveautés" est massive, non filtrée et protégée contre les robots,
Ricochet expose un vrai flux RSS propre et exploitable, alimenté par une
équipe de critiques -- c'est donc un signal de qualité, pas juste du bruit
commercial.

Réutilise l'écriture en base de veille_nouveautes_editeurs.py (même table
suggestion_acquisition, même garde-fou anti-doublon, même statut de départ
'à étudier' : rien n'est acquis automatiquement, tout reste soumis à
relecture humaine).

Limite connue : comme le flux BnF, le RSS ne fournit pas d'ISBN -- le
rapprochement avec le fonds se fait par titre normalisé, donc approximatif.
Pistes à vérifier, jamais décision automatique.

⚠ À valider sur ton Mac : le contenu exact du flux Ricochet (structure des
items, présence de l'auteur dans la description) n'a pas pu être testé
depuis l'environnement de développement (pas d'accès réseau à Ricochet).
Le parsing ci-dessous suit le standard RSS universel (title/link/
description) et devrait fonctionner, mais un premier run réel permettra de
confirmer que titres et auteurs remontent correctement.

Usage :
    python3 veille_ricochet.py
"""

import re
import html
import xml.etree.ElementTree as ET

# On réutilise tout l'outillage déjà écrit et testé pour la veille BnF :
# téléchargement (avec gestion gzip), normalisation des titres, chargement
# du fonds, et surtout l'écriture anti-doublon dans suggestion_acquisition.
from veille_nouveautes_editeurs import (
    _telecharger_flux,
    _normaliser,
    charger_titres_du_fonds,
    enregistrer_suggestions,
)

# Flux du CATALOGUE LIVRES (et non /rss.xml, qui est le fil d'articles
# éditoriaux du site -- testé le 2026-07-23, ne renvoyait que des billets de
# blog, pas des livres). Garde-fou supplémentaire dans charger_nouveautes() :
# on ne retient que les items pointant vers une fiche livre (/livres/), jamais
# vers un article (/articles/).
FLUX_RICOCHET = "https://www.ricochet-jeunes.org/livres/rss.xml"


def _extraire_auteur(description_html):
    """Tente de repérer un auteur dans la description de l'item (formats
    variables selon les flux -- on reste tolérant, l'auteur est un bonus,
    jamais un bloquant)."""
    texte = html.unescape(description_html or "")
    texte = re.sub(r"<[^>]+>", " ", texte)  # retire les balises HTML
    m = re.search(r"(?:Auteur|Autrice|De|Par)\s*:?\s*([A-ZÀ-Ü][^.;\n]{2,60})", texte)
    if m:
        return m.group(1).strip()
    return None


def charger_nouveautes():
    try:
        data = _telecharger_flux(FLUX_RICOCHET)
    except Exception as e:
        print(f"Impossible de récupérer le flux Ricochet : {type(e).__name__}: {e}")
        return []

    try:
        racine = ET.fromstring(data)
    except ET.ParseError as e:
        print(f"Flux Ricochet reçu mais illisible (format inattendu) : {e}")
        return []

    nouveautes = []
    for item in racine.iter("item"):
        titre = (item.findtext("title") or "").strip()
        if not titre:
            continue
        lien = (item.findtext("link") or "").strip()
        # Garde-fou : on ne garde que les fiches livres. Si un jour ce flux
        # se met à mélanger des articles éditoriaux (/articles/...), ils ne
        # doivent JAMAIS finir en suggestion d'acquisition -- ce ne sont pas
        # des livres.
        if lien and "/livres/" not in lien and "/livre/" not in lien:
            continue
        description = item.findtext("description") or ""
        nouveautes.append({
            "titre": titre,
            "auteur": _extraire_auteur(description),
            "editeur": None,
            "date_parution": None,
            "lien": lien,
        })
    return nouveautes


def main():
    print("═══ Veille Ricochet (critiques jeunesse, dont BD & manga) ═══\n")

    nouveautes = charger_nouveautes()
    if not nouveautes:
        print("Aucune nouveauté récupérée (flux vide ou inaccessible).")
        return

    print(f"{len(nouveautes)} titres/critiques dans le flux Ricochet.\n")

    titres_fonds = charger_titres_du_fonds()
    print(f"({len(titres_fonds)} titres distincts dans le fonds pour comparaison.)\n")

    absents, presents = [], []
    for n in nouveautes:
        (presents if _normaliser(n["titre"]) in titres_fonds else absents).append(n)

    print(f"── Critiqués par Ricochet, absents du fonds ({len(absents)}) ──")
    print("(rapprochement par titre normalisé -- à vérifier humainement)\n")
    for n in absents:
        ligne = f"  • {n['titre']}"
        if n["auteur"]:
            ligne += f" — {n['auteur']}"
        print(ligne)
        if n["lien"]:
            print(f"    {n['lien']}")

    print()
    ajoutes, doublons = enregistrer_suggestions(absents, source_label="Veille Ricochet (critiques jeunesse)")
    print(f"── Suggestions d'acquisition : {ajoutes} ajoutée(s), {doublons} déjà présente(s) (pas de doublon créé) ──")


if __name__ == "__main__":
    main()
