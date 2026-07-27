#!/usr/bin/env python3
"""
public_vise.py — LA règle unique de normalisation du public visé.

DÉCISION DU 2026-07-27 (Thomas) : quatre valeurs canoniques, pas une de plus :

    Adulte   Jeunesse   Adolescent   Tout public

POURQUOI : l'audit du même jour a trouvé 13 valeurs différentes dans
notice.public_vise (« Jeune » ET « Jeunesse », « Ado (12+) » ET
« Adolescent », des âges comme « Dès 3 ans »...). Le chat devait deviner les
variantes à chaque requête ; le premier oubli produisait un chiffre faux.
Les données brutes Decalog (zone 995 $l) n'utilisent que « Jeune »,
« Adolescent », « Adulte », « Tout public » — les variantes venaient de notre
propre enrichissement. La règle vit donc ICI, et tout point d'écriture en
base DOIT passer par normaliser().

Utilisé par : actualiser_catalogue.py (import hebdo), lancer_enrichissement.py
(écritures d'enrichissement), normaliser_public_vise.py (rattrapage initial).

Testable seul :  python3 public_vise.py
"""
import re
import unicodedata

VALEURS_CANONIQUES = ("Adulte", "Jeunesse", "Adolescent", "Tout public")


def _cle(v):
    v = unicodedata.normalize("NFKD", v or "")
    v = "".join(c for c in v if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", v).strip()


_TABLE = {
    "adulte": "Adulte",
    "jeune": "Jeunesse",
    "jeunesse": "Jeunesse",
    "ado": "Adolescent",
    "ado (12+)": "Adolescent",
    "adolescent": "Adolescent",
    "ados": "Adolescent",
    "des 12 ans": "Adolescent",
    "12-16 ans": "Adolescent",
    "tout public": "Tout public",
    "ados / adultes": "Tout public",
}


def est_age(valeur):
    """« Dès 3 ans », « 8-12 ans », « à partir de 8 »... : un ÂGE égaré dans
    le champ public. Sa place est dans age_recommande ; le public devient
    Jeunesse (ces mentions ne concernent que des documents jeunesse)."""
    k = _cle(valeur)
    return bool(re.match(r"^(des\b|a partir\b|\d)", k)) and k not in _TABLE


def normaliser(valeur):
    """Ramène toute valeur à l'une des quatre canoniques.

    Valeur inconnue et non reconnue comme un âge -> renvoyée TELLE QUELLE :
    on ne détruit jamais une information qu'on ne comprend pas, on préfère
    la voir apparaître dans le prochain audit."""
    if not valeur or not str(valeur).strip():
        return valeur
    k = _cle(valeur)
    if k in _TABLE:
        return _TABLE[k]
    if est_age(valeur):
        return "Jeunesse"
    return valeur


SEUIL_PEGI_MANGA_ADULTE = 14


def public_manga(pegi, public_actuel=None):
    """RÈGLE MAAT (Thomas, 2026-07-27) : pour les MANGAS, le public découle
    du PEGI — PEGI >= 14 c'est Adulte, en dessous c'est Jeunesse. Pas de
    rayon « manga ado » à la médiathèque : la frontière est à 14.

    PEGI absent ou illisible -> on ne décide RIEN, on garde le public
    existant (normalisé). Un seinen sans PEGI qui deviendrait « Jeunesse »
    par défaut serait bien pire que l'incohérence qu'on corrige."""
    # le champ a longtemps été rempli sous la forme « PEGI 12 » (corrigé le
    # 2026-07-27 dans moteur_recherche) : on extrait le nombre où qu'il soit
    m = re.search(r"\d+", str(pegi or ""))
    if not m:
        return normaliser(public_actuel)
    return ("Adulte" if int(m.group()) >= SEUIL_PEGI_MANGA_ADULTE
            else "Jeunesse")


if __name__ == "__main__":
    cas = ["Jeune", "Jeunesse", "JEUNE ", "Adulte", "Ado (12+)", "Adolescent",
           "Ados / Adultes", "Tout public", "Dès 3 ans", "8-12 ans",
           "à partir de 8", "dès 9 ans", "Dès 12 ans", "", None,
           "Public inconnu bizarre"]
    for c in cas:
        print(f"  {str(c)!r:28} -> {normaliser(c)!r}"
              f"{'   (âge)' if c and est_age(c) else ''}")
