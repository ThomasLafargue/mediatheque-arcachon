#!/usr/bin/env python3
"""
collections_editeur.py — Distingue une VRAIE SÉRIE narrative d'une COLLECTION
d'éditeur.

POURQUOI (2026-07-26) : nos sources (web marchand, zone MARC 410) renvoient
indifféremment la série d'une œuvre (« Corto Maltese », « Max et Lili ») et la
collection de l'éditeur (« Folio », « Aire Libre », « 10-18 »). Les deux
finissent dans le champ `serie`. Demander à un agent de saisir « Collection
Folio » comme série dans Decalog dégraderait le catalogue au lieu de
l'améliorer -- c'est le chat lui-même qui a repéré le problème.

Ce module ne supprime rien : il QUALIFIE, pour permettre de trier les
corrections sûres de celles qui demandent un œil humain.

Utilisé par exporter_corrections_decalog.py. Testable seul :
    python3 collections_editeur.py
"""

import re
import unicodedata

# Collections d'éditeur françaises courantes (littérature, poche, BD, jeunesse).
# Liste volontairement non exhaustive : elle couvre les cas les plus fréquents
# du fonds, pas la totalité de l'édition française.
COLLECTIONS_CONNUES = {
    # Poche / littérature générale
    "folio", "collection folio", "points", "pocket", "j ai lu", "le livre de poche",
    "livre de poche", "10 18", "babel", "babel noir", "points seuil", "points roman",
    "presses pocket", "librio", "flammarion", "gf flammarion", "garnier flammarion",
    "quarto", "la pleiade", "bibliotheque de la pleiade", "imaginaire",
    "belfond noir", "cadre noir", "cadre rouge", "serie noire", "grands detectives",
    "rivages noir", "rivages thriller", "actes noirs", "seuil policiers",
    "le masque", "policiers", "thriller", "suspense", "terreur",
    # BD / comics
    "aire libre", "grand angle", "1000 feuilles", "ex libris", "marabulles",
    "contre bande", "mirages", "best of marvel", "marvel deluxe", "dc deluxe",
    "collection dc deluxe", "urban comics", "vertigo", "shonen", "shonen manga",
    "seinen", "shojo", "kana", "glenat manga", "ecritures", "signe",
    "repérages", "reperages", "bd cult", "patrimoine",
    # Jeunesse
    "albums", "album", "albums circonflexe", "jeunesse", "romans", "roman",
    "premiere lecture", "premieres lectures", "mes premiers", "petite enfance",
    "castor poche", "folio junior", "folio cadet", "folio benjamin",
    "milan poche", "mouche", "neuf", "medium", "lutin poche", "les lutins",
    "kididoc",  # NB : Kididoc est une collection, même si numérotée
    # DÉCISION DU 2026-07-27 (Thomas, bibliothécaire) : « Mes p'tits docs »,
    # « Mes p'tites questions », « Mes p'tits albums » (Milan) restent traitées
    # comme des SÉRIES, donc NE PAS les ajouter ici. Ce sont formellement des
    # collections, mais le public les cherche par ce nom : les regrouper rend
    # plus service qu'une orthodoxie catalographique. Choix délibéré.
    # Documentaires / essais
    "que sais je", "decouvertes", "decouvertes gallimard", "essais",
    "sciences humaines", "documents", "temoignages", "biographie", "biographies",
    # Guides de voyage : le « titre » varie par destination, la collection non
    "guide de tourisme", "guides de tourisme", "lonely planet guide de voyage",
    "guide du routard", "en quelques jours", "un grand week end a",
    "cartoville", "encyclopedie du voyage",
    # Marques éditoriales relevées dans le fonds le 2026-07-27
    "fiction cie", "g f", "les grandes traductions", "harpercollins noir",
    "exprim", "en lettres d ancre", "grands detectives", "domaine etranger",
    # Grands caractères : « 16-17 » = corps de caractère (À vue d'œil), pas
    # une série. Vérifié le 2026-07-27 sur les 41 notices du fonds : que des
    # romans adultes réédités en gros texte (Dicker, Foenkinos, Lévy...).
    # Les collections sœurs « 16 », « 18 », « 20 » sont déjà écartées par la
    # règle de la parenthèse ; celle-ci n'en porte pas.
    "16 17", "gros caracteres", "grands caracteres", "corps 16", "corps 17",
}

# Motifs qui trahissent une collection plutôt qu'une série narrative
MOTIFS_COLLECTION = (
    r"^collection\b",
    r"\bcollection dirig",       # « Collection dirigée par ... »
    r"^(les )?(albums?|romans?|essais?|documents?)$",
    r"^(litt[ée]rature|jeunesse|policier|polar|thriller|fantasy|science.fiction)$",
    r"^\W*\d+\W*$",              # une série qui ne serait qu'un nombre
    r"^(éd|ed)\.?\s",            # « Éd. courtes et longues »
)


def _normaliser(t):
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def a_qualificatif_autorite(valeur):
    """True si la valeur porte un qualificatif d'autorité MARC entre
    parenthèses : « Médium (Paris. 1 », « Roman (Éd. de la Loupe »,
    « Domaine français (Arles ».

    POURQUOI C'EST FIABLE (vérifié le 2026-07-27) : ce qualificatif — lieu
    d'édition, millésime ou éditeur — sert à DÉSAMBIGUÏSER une collection
    d'éditeur homonyme d'une autre. Le catalogage ne l'accole jamais à une
    série narrative : Thorgal, Achille Talon ou A.N.G.E n'en portent pas.
    Sur les 290 valeurs à parenthèse du fonds, 290 étaient des collections
    (ou des titres tronqués) — aucune vraie série. C'est donc une règle de
    structure, pas une heuristique de vocabulaire : elle attrape les
    collections que la liste COLLECTIONS_CONNUES ne peut pas prévoir.
    """
    return bool(valeur) and "(" in valeur


def est_collection(valeur):
    """True si la valeur ressemble à une collection d'éditeur plutôt qu'à une
    série narrative. En cas de doute -> False (on préfère laisser passer une
    vraie série qu'écarter à tort)."""
    if not valeur:
        return False
    if a_qualificatif_autorite(valeur):
        return True
    n = _normaliser(valeur)
    if not n:
        return False
    if n in COLLECTIONS_CONNUES:
        return True
    for motif in MOTIFS_COLLECTION:
        if re.search(motif, n):
            return True
    # « Folio junior », « Points roman »... : commence par une collection connue
    premiers = n.split()
    if premiers and premiers[0] in {"folio", "points", "babel", "rivages",
                                    "castor", "milan", "librio"}:
        return True
    return False


def qualifier(serie, tome):
    """Renvoie (fiable, raison).

    Un tome numéroté est un fort indice de série narrative : une collection
    d'éditeur ne numérote pas ses titres de façon suivie (à l'exception de
    quelques collections documentaires, d'où le maintien du doute)."""
    if not serie:
        return False, "série vide"
    if a_qualificatif_autorite(serie):
        # Motif distinct : ces lignes sont écartables en bloc, sans examen
        # au cas par cas, contrairement aux collections repérées par leur nom.
        return False, "qualificatif d'autorité entre parenthèses = collection"
    if est_collection(serie):
        if tome:
            return False, "collection d'éditeur (mais tome renseigné : à vérifier)"
        return False, "collection d'éditeur, pas une série"
    return True, "série narrative"


if __name__ == "__main__":
    cas = [
        ("Corto Maltese", "3"), ("Les Aventures de Tintin", "7"),
        ("Ainsi va la vie.", "125"), ("Max et Lili", None),
        ("Collection Folio", None), ("Folio junior", None),
        ("Aire Libre", None), ("Grand angle", None), ("10-18", None),
        ("Albums", None), ("Jeunesse", None), ("7", None),
        ("Collection dirigée par Emmanuelle Beulque", None),
        ("Kididoc", "43"), ("Best of Marvel", None),
        ("Yoko Tsuno", "12"), ("Lucky Luke", "37"),
        # qualificatif d'autorité MARC -> collection, quoi qu'il arrive
        ("Médium (Paris. 1", None), ("Roman (Éd. de la Loupe", None),
        ("Domaine français (Arles", None), ("Presses pocket (Paris", None),
        ("Mouche (Paris", "3"),
        # ... mais une série narrative sans parenthèse reste une série
        ("Achille Talon", "5"), ("A.N.G.E", None), ("Thorgal", "22"),
    ]
    print(f"{'valeur':46} {'tome':>6}  verdict")
    print("-" * 78)
    for s, t in cas:
        ok, raison = qualifier(s, t)
        print(f"{s[:44]:46} {str(t or '—'):>6}  "
              f"{'✓ SÉRIE' if ok else '✗ écartée'} — {raison}")
