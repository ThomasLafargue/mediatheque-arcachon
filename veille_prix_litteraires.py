#!/usr/bin/env python3
"""
veille_prix_litteraires.py — Croise les sélections des grands prix jeunesse
français (Prix Sorcières, Prix des Incorruptibles) avec le fonds Arcachon,
pour repérer les titres primés/nommés absents du catalogue.

Pourquoi une liste figée plutôt qu'un scraping automatique (2026-07-23) :
contrairement au flux RSS BnF (continu, stable, lu automatiquement dans
veille_nouveautes_editeurs.py), ces deux prix n'ont pas de source fiable à
interroger en direct -- le flux RSS de Citrouille Hebdo (Sorcières) existe
mais nos outils ne savent pas l'exploiter proprement, et la page du Prix
des Incorruptibles est une page web fragile (contenu tronqué lors de sa
récupération, nécessite un contournement technique). Comme ces sélections
ne changent qu'une à deux fois par an (pas chaque semaine), on préfère une
LISTE DE RÉFÉRENCE tenue à jour à la main -- plus rigoureux qu'un scraping
qui casserait silencieusement à la moindre refonte de site, en laissant
croire à tort que la liste est encore à jour.

Mise à jour (une à deux fois par an) : ajouter les nouvelles sélections
dans SELECTION ci-dessous.
  - Prix Sorcières : nommés en mars sur citrouille-hebdo.fr (catégorie
    "Prix Sorcières"), lauréats fin mars.
  - Prix des Incorruptibles : sélection officielle sur
    https://prix.lesincos.com/la-selection (rythme scolaire, votes en
    cours d'année).

Usage :
    python3 veille_prix_litteraires.py
"""

import db
# Fonctions partagées, définies une seule fois dans veille_nouveautes_editeurs
# (normalisation des titres, chargement du fonds, écriture anti-doublon en
# base). On les réutilise ici au lieu de les dupliquer.
from veille_nouveautes_editeurs import (
    _normaliser,
    charger_titres_du_fonds,
    enregistrer_suggestions,
)

SELECTION = [
    # ── Prix Sorcières 2026 (40e édition, nommés -- ABF + ALSJ / Librairies
    # Sorcières, source : citrouille-hebdo.fr) ──
    {"titre": "36 mois", "auteur": "Julia Spiers", "editeur": "Les Grandes Personnes",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau mini"},
    {"titre": "Allons voir la nuit. Un livre à animer ensemble", "auteur": "Aurélie Sarrazin",
     "editeur": "Sens Dessus Dessous", "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau mini"},
    {"titre": "L'imagier des objets et des matières", "auteur": "Pascale Estellon",
     "editeur": "Les Grandes Personnes", "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau mini"},
    {"titre": "Printemps", "auteur": "Léa Louis", "editeur": "Courtes et Longues",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau mini"},
    {"titre": "Raouf", "auteur": "Krocui", "editeur": "L'Articho",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau mini"},
    {"titre": "Chamalloux", "auteur": "Lee Gee-eun", "editeur": "Les fourmis rouges",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau maxi"},
    {"titre": "La chasse aux rainettes", "auteur": "Antonin Faure", "editeur": "Thierry Magnier",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau maxi"},
    {"titre": "L'été de Mamie", "auteur": "Bonsoir Lune", "editeur": "Cambourakis",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau maxi"},
    {"titre": "La Grande Cradolasse. Princesse du Pays de Boue", "auteur": "Beatrice Alemagna",
     "editeur": "l'école des loisirs", "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau maxi"},
    {"titre": "Lune", "auteur": "Eva Diop", "editeur": "hélium",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Beau maxi"},
    {"titre": "Droméo et Chuliette", "auteur": "Marcus Malte", "editeur": "du Rouergue",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant mini"},
    {"titre": "Esprits d'enfance", "auteur": "Stéphane Servant", "editeur": "du Rouergue",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant mini"},
    {"titre": "Une histoire de rien du tout", "auteur": "Marie Dorléans", "editeur": "Seuil Jeunesse",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant mini"},
    {"titre": "Oskar et moi. Et tous nos petits endroits", "auteur": "Maria Parr", "editeur": "Thierry Magnier",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant mini"},
    {"titre": "La petite fille au fusil. L'histoire d'une jeune résistante", "auteur": "Marius Marcinkevičius",
     "editeur": "du Ricochet", "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant mini"},
    {"titre": "Les Adelphides", "auteur": "Alice Dozier", "editeur": "Actes Sud Jeunesse",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant maxi"},
    {"titre": "L'archipel de béton", "auteur": "Olivier Dain-Belmont", "editeur": "Sarbacane",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant maxi"},
    {"titre": "Finding Phoebe", "auteur": "Gavin Extence", "editeur": "Seuil Jeunesse",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant maxi"},
    {"titre": "La part du vent", "auteur": "Nathalie Bernard", "editeur": "Thierry Magnier",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant maxi"},
    {"titre": "Quelque chose de beau", "auteur": "Julie Rey", "editeur": "l'école des loisirs",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Passionnant maxi"},
    {"titre": "Boucle d'Or. En chemin", "auteur": "Caroline Gamon", "editeur": "hélium",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières fiction"},
    {"titre": "La cité des lettres", "auteur": "Jonas Tjäder", "editeur": "Rue du monde",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières fiction"},
    {"titre": "Dia de Muertos", "auteur": "Anne-Florence Lemasson", "editeur": "Les Grandes Personnes",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières fiction"},
    {"titre": "Le jeu du plus qu'un jour", "auteur": "Audrey Poussier", "editeur": "l'école des loisirs",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières fiction"},
    {"titre": "Le tambour", "auteur": "Jeanne Saboureault", "editeur": "MeMo",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières fiction"},
    {"titre": "Histoire de l'information", "auteur": "Chris Haughton", "editeur": "Thierry Magnier",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières non-fiction"},
    {"titre": "Une île est née", "auteur": "Virginie Aladjidi et Caroline Pellissier", "editeur": "Saltimbanque",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières non-fiction"},
    {"titre": "Tout le monde se parle ! Petite encyclopédie des 1 000 manières de communiquer chez les humains et autres êtres vivants",
     "auteur": "Romana Romanyshyn", "editeur": "Rue du monde",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières non-fiction"},
    {"titre": "L'univers de Pi. Le nombre mystérieux qui rend tout le monde dingue", "auteur": "Anita Lehmann et Jean-Baptiste Aubin",
     "editeur": "Helvetiq", "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières non-fiction"},
    {"titre": "Voir et savoir. Dans l'intimité du monde végétal", "auteur": "Fanny Pageaud", "editeur": "Les Grandes Personnes",
     "prix": "Prix Sorcières 2026", "categorie": "Carrément Sorcières non-fiction"},

    # ── Prix des Incorruptibles 2026/2027 (38e édition, sélection officielle,
    # source : prix.lesincos.com/la-selection) ──
    {"titre": "Coricoco !", "auteur": "Christelle Saquet", "editeur": "Circonflexe",
     "prix": "Incorruptibles 2026/2027", "categorie": "Maternelle"},
    {"titre": "Parfois, on tombe", "auteur": "Randall De Sève", "editeur": "Didier Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "Maternelle"},
    {"titre": "GRRRIZZLY", "auteur": "Hervé Le Goff", "editeur": "Flammarion jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "Maternelle"},
    {"titre": "Rien du tout !", "auteur": "Marie-Hélène Jarry", "editeur": "Editions de l'Isatis",
     "prix": "Incorruptibles 2026/2027", "categorie": "Maternelle"},
    {"titre": "Opération Escargot", "auteur": "Corey R. Tabor", "editeur": "Le Genévrier",
     "prix": "Incorruptibles 2026/2027", "categorie": "Maternelle"},
    {"titre": "Les apPAPArences", "auteur": "Sonia Coudert", "editeur": "Mijade",
     "prix": "Incorruptibles 2026/2027", "categorie": "Maternelle"},
    {"titre": "Je choisis", "auteur": "Olivier Dupin", "editeur": "Alice Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CP"},
    {"titre": "Le Tablier de Tomio", "auteur": "Delphine Roux", "editeur": "HongFei",
     "prix": "Incorruptibles 2026/2027", "categorie": "CP"},
    {"titre": "Ici", "auteur": "Séverine Duchesne", "editeur": "Kilowatt",
     "prix": "Incorruptibles 2026/2027", "categorie": "CP"},
    {"titre": "Le carré sauvage", "auteur": "Anne-Hélène Dubray", "editeur": "L'Agrume",
     "prix": "Incorruptibles 2026/2027", "categorie": "CP"},
    {"titre": "Toto", "auteur": "Hyewon Yum", "editeur": "Les éditions des Éléphants",
     "prix": "Incorruptibles 2026/2027", "categorie": "CP"},
    {"titre": "Et si la baleine me croque ?", "auteur": "Susanna Isern", "editeur": "Père Fouettard",
     "prix": "Incorruptibles 2026/2027", "categorie": "CP"},
    {"titre": "Notre lac", "auteur": "Angie Kang", "editeur": "Didier Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CE1/CE2"},
    {"titre": "Un sari vert et bleu", "auteur": "Nicolas Deleau", "editeur": "Gallimard Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CE1/CE2"},
    {"titre": "Le prince et le grand chêne", "auteur": "Bernard Villiot", "editeur": "Gautier-Languereau",
     "prix": "Incorruptibles 2026/2027", "categorie": "CE1/CE2"},
    {"titre": "La Ballade magique de Baumerire", "auteur": "Loïc Clement", "editeur": "Glénat Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CE1/CE2"},
    {"titre": "Le Goût du Cresson", "auteur": "Andrea Wang", "editeur": "HongFei",
     "prix": "Incorruptibles 2026/2027", "categorie": "CE1/CE2"},
    {"titre": "Peur à peur", "auteur": "Chiara Mezzalama", "editeur": "Les éditions des Éléphants",
     "prix": "Incorruptibles 2026/2027", "categorie": "CE1/CE2"},
    {"titre": "Le cadeau sauvage", "auteur": "Jean-François Chabas", "editeur": "Albin Michel Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM1"},
    {"titre": "Je n'ai pas de frontière", "auteur": "Cécile Elma Roger", "editeur": "Athizes",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM1"},
    {"titre": "Les cils du loup", "auteur": "Chantal Nguyen", "editeur": "Cipango",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM1"},
    {"titre": "Omar tisserand d'art", "auteur": "Jane Singleton", "editeur": "Editions du Jasmin",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM1"},
    {"titre": "Ombreline", "auteur": "Manon Fargetton", "editeur": "Milan",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM1"},
    {"titre": "Quelque chose sur le cœur", "auteur": "Amélie Antoine", "editeur": "Syros",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM1"},
    {"titre": "Wesh la fée !", "auteur": "Rachel Corenblit", "editeur": "Bayard Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM2/6e"},
    {"titre": "Envers et contre ma sœur", "auteur": "Nadège Margaud", "editeur": "Didier Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM2/6e"},
    {"titre": "Les exploits de Connie Mara", "auteur": "Jean-Philippe Arrou-Vignod", "editeur": "Gallimard Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM2/6e"},
    {"titre": "Chercheurs d'os", "auteur": "Michel Piquemal", "editeur": "Milan",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM2/6e"},
    {"titre": "Satomi et le souffle de vie", "auteur": "Sissi Briche", "editeur": "Sarbacane",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM2/6e"},
    {"titre": "Le maillot des Hercules", "auteur": "Sarah Turoche Dromery", "editeur": "Thierry Magnier",
     "prix": "Incorruptibles 2026/2027", "categorie": "CM2/6e"},
    {"titre": "Les Adelphides", "auteur": "Alice Dozier", "editeur": "Actes Sud Junior",
     "prix": "Incorruptibles 2026/2027", "categorie": "5e/4e"},
    {"titre": "Bye bye Dubaï", "auteur": "Muriel Zürcher", "editeur": "Didier Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "5e/4e"},
    {"titre": "L'évadé de Belle-Ile", "auteur": "Philippe Nessmann", "editeur": "Les éditions des Éléphants",
     "prix": "Incorruptibles 2026/2027", "categorie": "5e/4e"},
    {"titre": "Tomber les murs", "auteur": "Delphine Pessin", "editeur": "PKJ",
     "prix": "Incorruptibles 2026/2027", "categorie": "5e/4e"},
    {"titre": "Comment rester invisible", "auteur": "Maggie C. Rudd", "editeur": "Seuil Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "5e/4e"},
    {"titre": "1096 jours", "auteur": "Amélie Antoine", "editeur": "Syros",
     "prix": "Incorruptibles 2026/2027", "categorie": "5e/4e"},
    {"titre": "Où que tu sois", "auteur": "Aurelia Demarlier", "editeur": "Alice Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "3e/Lycée"},
    {"titre": "La mélancolie des sauterelles", "auteur": "Lily-Belle De Chollet", "editeur": "Didier Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "3e/Lycée"},
    {"titre": "Vivre sans attendre", "auteur": "Laureline Maumelat", "editeur": "Rageot",
     "prix": "Incorruptibles 2026/2027", "categorie": "3e/Lycée"},
    {"titre": "Finding Phoebe", "auteur": "Gavin Extence", "editeur": "Seuil Jeunesse",
     "prix": "Incorruptibles 2026/2027", "categorie": "3e/Lycée"},
    {"titre": "Une trace dans la nuit", "auteur": "Catherine Cuenca", "editeur": "Talents Hauts",
     "prix": "Incorruptibles 2026/2027", "categorie": "3e/Lycée"},
]


def enregistrer_suggestions_prix(absents):
    """Enregistre les titres primés absents du fonds dans suggestion_acquisition.
    Réutilise l'écriture générique de veille_nouveautes_editeurs (même table,
    même garde-fou anti-doublon, même statut 'à étudier') : on se contente de
    formater chaque prix en un 'motif' lisible, puis on délègue. Évite de
    dupliquer la logique d'écriture, qui n'existe qu'à un seul endroit."""
    a_ecrire = [
        {
            "titre": item["titre"],
            "auteur": item.get("auteur"),
            "editeur": item.get("editeur"),
            "date_parution": None,
            "motif": f"{item['prix']} — catégorie/niveau : {item['categorie']}",
        }
        for item in absents
    ]
    return enregistrer_suggestions(a_ecrire, source_label="Veille prix littéraires jeunesse")


def main():
    print("═══ Veille prix littéraires jeunesse — croisement avec le fonds ═══\n")
    print(f"{len(SELECTION)} titres dans la liste de référence (Prix Sorcières 2026 + Incorruptibles 2026/2027).\n")

    # Signal bonus : un titre nommé/sélectionné pour PLUSIEURS prix à la fois
    # est un candidat particulièrement solide -- on le repère avant tout.
    par_titre_norm = {}
    for item in SELECTION:
        par_titre_norm.setdefault(_normaliser(item["titre"]), []).append(item)
    doublons = {k: v for k, v in par_titre_norm.items() if len(v) > 1}

    titres_fonds = charger_titres_du_fonds()
    print(f"({len(titres_fonds)} titres distincts dans le fonds pour comparaison.)\n")

    absents, presents = [], []
    for item in SELECTION:
        norm = _normaliser(item["titre"])
        (presents if norm in titres_fonds else absents).append(item)

    if doublons:
        print(f"── Reconnus par PLUSIEURS prix à la fois ({len(doublons)}) — signal fort ──\n")
        for norm, items in doublons.items():
            prix_liste = " + ".join(i["prix"] for i in items)
            deja_present = norm in titres_fonds
            statut = "déjà au fonds" if deja_present else "ABSENT du fonds"
            print(f"  • {items[0]['titre']} ({items[0]['auteur']}) — {prix_liste} — {statut}")
        print()

    print(f"── Primés/nommés absents du fonds ({len(absents)}) ──\n")
    par_prix = {}
    for item in absents:
        par_prix.setdefault(item["prix"], []).append(item)
    for prix, items in par_prix.items():
        print(f"  {prix} :")
        for i in items:
            print(f"    • {i['titre']} — {i['auteur']} ({i['editeur']}) — {i['categorie']}")
        print()

    print(f"── Déjà au fonds ({len(presents)}) ──")
    for i in presents:
        print(f"  • {i['titre']}")

    print()
    ajoutes, doublons = enregistrer_suggestions_prix(absents)
    print(f"── Suggestions d'acquisition : {ajoutes} ajoutée(s), {doublons} déjà présente(s) (pas de doublon créé) ──")


if __name__ == "__main__":
    main()
