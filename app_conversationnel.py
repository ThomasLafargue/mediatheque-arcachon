"""
Outil conversationnel -- Médiathèque d'Arcachon.

Interface de chat qui interroge inventaire.db (vue_inventaire) en langage
naturel, via l'API Claude (function calling / tool use). Pensé pour être
déployé sur Streamlit Community Cloud et accessible depuis n'importe où
(bibliothèque, domicile, téléphone) via une simple URL.

Lancement local :
    pip install -r requirements_app.txt
    export ANTHROPIC_API_KEY="sk-ant-..."
    streamlit run app_conversationnel.py
"""

import os
import re
import json
import io
import sys
import tempfile
import datetime
import sqlite3
import streamlit as st

# Pont secrets Streamlit Cloud -> variables d'environnement, AVANT d'importer
# db (qui lit ces variables au chargement). En local, ce pont ne fait rien
# de plus que ce que le fichier .env fait déjà ; sur Streamlit Cloud, c'est
# ce qui permet à db.py de détecter Turso sans aucun fichier .env présent.
for _cle in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
    try:
        if _cle in st.secrets:
            os.environ[_cle] = st.secrets[_cle]
    except Exception:
        pass  # pas de secrets.toml en local -- db.py se rabat sur .env / sqlite local

import db
from anthropic import Anthropic

FICHIER_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventaire.db")

st.set_page_config(page_title="Médiathèque d'Arcachon — Assistant fonds", page_icon="📚", layout="wide")


# ----------------------------------------------------------------------------
# Accès en lecture seule à la base -- aucune écriture possible depuis l'outil
# ----------------------------------------------------------------------------
MOTS_INTERDITS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)


def executer_requete_sql(sql: str) -> str:
    sql_nettoyee = sql.strip().rstrip(';')
    if not re.match(r'^\s*SELECT\b', sql_nettoyee, re.IGNORECASE):
        return json.dumps({"erreur": "Seules les requêtes SELECT sont autorisées."})
    if MOTS_INTERDITS.search(sql_nettoyee):
        return json.dumps({"erreur": "Mot-clé non autorisé dans cette requête."})
    try:
        conn = db.connect(FICHIER_DB)
        conn.row_factory = sqlite3.Row if not db.MODE_EN_LIGNE else db.Row
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM ({sql_nettoyee}) LIMIT 500")
        lignes = [dict(r) for r in cur.fetchall()]
        conn.close()
        return json.dumps(lignes, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"erreur": str(e)})


OUTIL_SQL = {
    "name": "executer_requete_sql",
    "description": (
        "Exécute une requête SQL SELECT en lecture seule sur la base de la médiathèque. "
        "Table principale à utiliser : vue_inventaire (une ligne par exemplaire réel "
        "d'Arcachon). Colonnes disponibles : isbn, titre, serie, tome, collection, type "
        "(LIVRE/CD/DVD/JEU), categorie (Roman jeunesse/BD/Manga/Album/Documentaire...), "
        "genre, public, age_recommande, pegi, auteur, illustrateur, traducteur, editeur, "
        "annee, dewey, dewey_libelle, mots_cles, description_physique, code_barres, cote, "
        "statut_exemplaire, prix, nb_prets_titre_reseau (prêts du titre sur tout le réseau "
        "COBAS), nb_prets_cet_exemplaire (prêts de cette copie précise à Arcachon), "
        "dernier_pret_titre_reseau, dernier_pret_cet_exemplaire, resume. "
        "Autres tables disponibles si besoin : frequentation (date, nb_entrees) ; "
        "suggestion_acquisition -- ATTENTION, nom exact SANS 's' à 'suggestion' -- "
        "(id, titre, demandeur, auteur, editeur, isbn, prix, motif, source, statut, "
        "date_ajout) pour consulter les suggestions déjà ajoutées, y compris "
        "filtrées par demandeur (WHERE demandeur = '...'). "
        "Toujours préférer nb_prets_cet_exemplaire pour des questions sur le fonds "
        "d'Arcachon spécifiquement. Limite automatique à 500 lignes par requête."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "La requête SELECT à exécuter"}},
        "required": ["sql"],
    },
}

COLONNES_EXPORT_PAR_DEFAUT = [
    ("isbn", "ISBN / EAN"), ("titre", "Titre"), ("serie", "Série"), ("tome", "Tome"),
    ("auteur", "Auteur"), ("illustrateur", "Illustrateur"), ("editeur", "Éditeur"),
    ("annee", "Année"), ("type", "Type"), ("categorie", "Catégorie"), ("genre", "Genre"),
    ("public", "Public"), ("age_recommande", "Âge conseillé"), ("cote", "Cote"),
    ("code_barres", "Code-barres"), ("statut_exemplaire", "Statut"), ("prix", "Prix (€)"),
    ("nb_prets_cet_exemplaire", "Prêts (Arcachon)"), ("dernier_pret_cet_exemplaire", "Dernier prêt"),
]


def generer_excel_bytes(sql=None, lignes_fournies=None):
    """Construit un export xlsx en mémoire.
    - lignes_fournies : liste de dicts construite par Claude lui-même (ex.
      suggestions d'acquisition trouvées par recherche web) -- utilisée en
      priorité si fournie.
    - sql : sinon, requête sur notre base (mêmes garde-fous SELECT-only
      qu'executer_requete_sql). Sans aucun des deux : fonds complet."""
    if lignes_fournies:
        lignes = lignes_fournies
        colonnes_presentes = list(lignes[0].keys())
        colonnes = [(c, c.replace('_', ' ').capitalize()) for c in colonnes_presentes]
        return _ecrire_xlsx(lignes, colonnes, acces_par_cle=True)

    sql_finale = (sql or "SELECT * FROM vue_inventaire").strip().rstrip(';')
    if not re.match(r'^\s*SELECT\b', sql_finale, re.IGNORECASE):
        return None, 0, "Seules les requêtes SELECT sont autorisées pour un export."
    if MOTS_INTERDITS.search(sql_finale):
        return None, 0, "Mot-clé non autorisé dans cette requête d'export."

    conn = db.connect(FICHIER_DB)
    conn.row_factory = sqlite3.Row if not db.MODE_EN_LIGNE else db.Row
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM ({sql_finale}) LIMIT 100000")
    lignes = cur.fetchall()
    conn.close()

    if not lignes:
        return None, 0, "Aucune ligne ne correspond à cet export."

    colonnes_presentes = list(lignes[0].keys())
    noms_par_defaut = {c for c, _ in COLONNES_EXPORT_PAR_DEFAUT}
    if noms_par_defaut.issubset(set(colonnes_presentes)):
        colonnes = [(c, l) for c, l in COLONNES_EXPORT_PAR_DEFAUT if c in colonnes_presentes]
    else:
        colonnes = [(c, c) for c in colonnes_presentes]

    return _ecrire_xlsx(lignes, colonnes, acces_par_cle=True)


def _ecrire_xlsx(lignes, colonnes, acces_par_cle=True):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Export"
    thin = Side(style="thin", color="D9E2F0")
    bordure = Border(left=thin, right=thin, top=thin, bottom=thin)

    for c, (cle, libelle) in enumerate(colonnes, 1):
        cellule = ws.cell(row=1, column=c, value=libelle)
        cellule.font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        cellule.fill = PatternFill("solid", fgColor="2E4A7A")
        cellule.border = bordure
        ws.column_dimensions[get_column_letter(c)].width = 18

    for i, ligne in enumerate(lignes, start=2):
        for c, (cle, libelle) in enumerate(colonnes, 1):
            valeur = ligne.get(cle) if isinstance(ligne, dict) else ligne[cle]
            cellule = ws.cell(row=i, column=c, value=valeur)
            cellule.font = Font(name="Arial", size=9.5)
            cellule.border = bordure

    ws.freeze_panes = "A2"
    tampon = io.BytesIO()
    wb.save(tampon)
    tampon.seek(0)
    return tampon.getvalue(), len(lignes), None


OUTIL_EXPORT = {
    "name": "generer_export_excel",
    "description": (
        "Génère un fichier Excel téléchargeable, de deux façons possibles :\n"
        "1) lignes : pour exporter une liste que TU as construite toi-même "
        "(typiquement des suggestions d'acquisition trouvées par web_search). "
        "Fournis une liste d'objets, chacun avec les mêmes champs (ex. titre, "
        "auteur, editeur, prix_estime, source). L'ISBN n'est PAS nécessaire "
        "pour une liste de suggestions -- ne le cherche pas, ne bloque jamais "
        "l'export en son absence. N'utilise CETTE option QUE pour des données "
        "venant réellement d'un résultat de web_search -- jamais de titres "
        "inventés.\n"
        "2) sql : pour exporter ce qui EST dans notre fonds (résultat d'une "
        "requête SELECT). Sans aucun argument : exporte le fonds complet.\n"
        "N'utilise jamais sql pour répondre à une demande de titres absents "
        "du fonds -- utilise lignes avec des résultats de web_search à la "
        "place, ou dis clairement que tu ne peux pas produire cet export."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Requête SELECT sur notre base (ce qu'on possède déjà)"},
            "lignes": {
                "type": "array",
                "description": "Liste d'objets à exporter directement (ex. suggestions trouvées par web_search)",
                "items": {"type": "object"},
            },
        },
    },
}


def ajouter_suggestion_acquisition(titre, demandeur, auteur=None, editeur=None, isbn=None,
                                    prix=None, motif=None, source=None):
    """Ajoute une ligne dans une liste de suggestions persistante (table
    suggestion_acquisition), consultable et exportable à tout moment via
    executer_requete_sql / generer_export_excel, y compris filtrée par
    demandeur. Nécessite le jeton d'écriture (TURSO_AUTH_TOKEN_ECRITURE) --
    l'opération est strictement limitée à cet ajout précis, jamais une
    écriture arbitraire."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "Fonction non configurée (TURSO_AUTH_TOKEN_ECRITURE manquant)."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_acquisition (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL,
                demandeur TEXT,
                auteur TEXT,
                editeur TEXT,
                isbn TEXT,
                prix REAL,
                motif TEXT,
                source TEXT,
                statut TEXT NOT NULL DEFAULT 'à étudier',
                date_ajout TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        try:  # migration silencieuse si la table existait déjà sans cette colonne
            conn.execute("ALTER TABLE suggestion_acquisition ADD COLUMN demandeur TEXT")
            conn.commit()
        except Exception:
            pass
        try:  # vue de compatibilité -- le nom "naturel" en français est au
            # pluriel ("liste de suggestions"), donc le modèle le devine
            # parfois ainsi malgré la table réelle au singulier. Plutôt que
            # de compter sur un texte d'instruction pour éviter l'erreur à
            # chaque fois, les deux noms fonctionnent désormais tous les deux.
            conn.execute("CREATE VIEW IF NOT EXISTS suggestions_acquisition AS SELECT * FROM suggestion_acquisition")
            conn.commit()
        except Exception:
            pass
        conn.execute(
            "INSERT INTO suggestion_acquisition (titre, demandeur, auteur, editeur, isbn, prix, motif, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (titre, demandeur, auteur, editeur, isbn, prix, motif, source),
        )
        conn.commit()
        conn.close()
        return json.dumps({"statut": "ok", "info": f"« {titre} » ajouté à la liste de {demandeur}."})
    except Exception as e:
        import traceback
        st.session_state["derniere_erreur_technique"] = traceback.format_exc()
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


OUTIL_SUGGESTION = {
    "name": "ajouter_suggestion_acquisition",
    "description": (
        "Ajoute un titre à une liste de suggestions d'acquisition PERSISTANTE, "
        "rattachée à une personne (demandeur). Utilise cet outil quand on te "
        "demande d'ajouter/noter/mettre un titre dans une liste de suggestions "
        "-- ne dis jamais que tu ne peux pas le faire, tu en es capable. Si la "
        "demande ne précise pas pour qui (quel demandeur), demande-le avant "
        "d'ajouter. Vérifie d'abord que le titre n'est pas déjà dans le fonds "
        "(executer_requete_sql) avant de l'ajouter. Pour consulter ou exporter "
        "la liste d'une personne en particulier, utilise executer_requete_sql "
        "ou generer_export_excel avec un filtre WHERE demandeur = '...'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "demandeur": {"type": "string", "description": "Qui fait cette suggestion (prénom de l'agent)"},
            "auteur": {"type": "string"},
            "editeur": {"type": "string"},
            "isbn": {"type": "string"},
            "prix": {"type": "number"},
            "motif": {"type": "string", "description": "Raison de la suggestion (ex. demande usager)"},
            "source": {"type": "string", "description": "D'où vient l'info (ex. URL trouvée par web_search)"},
        },
        "required": ["titre", "demandeur"],
    },
}


def supprimer_suggestion_acquisition(id):
    """Supprime UNE ligne précise de la liste de suggestions, par son id.
    Trouve d'abord l'id via executer_requete_sql avant d'appeler ceci --
    l'opération est strictement limitée à cette suppression précise par id,
    jamais une suppression arbitraire (pas de WHERE libre)."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "Fonction non configurée (TURSO_AUTH_TOKEN_ECRITURE manquant)."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        cur = conn.cursor()
        cur.execute("SELECT titre FROM suggestion_acquisition WHERE id = ?", (id,))
        ligne = cur.fetchone()
        if not ligne:
            conn.close()
            return json.dumps({"erreur": f"Aucune suggestion avec l'id {id}."})
        titre = ligne[0]
        conn.execute("DELETE FROM suggestion_acquisition WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        return json.dumps({"statut": "ok", "info": f"« {titre} » (id {id}) supprimé de la liste."})
    except Exception as e:
        import traceback
        st.session_state["derniere_erreur_technique"] = traceback.format_exc()
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


OUTIL_SUPPRESSION_SUGGESTION = {
    "name": "supprimer_suggestion_acquisition",
    "description": (
        "Supprime UNE suggestion précise de la liste, par son id. Utilise "
        "executer_requete_sql d'abord pour trouver l'id exact (ex. SELECT id, "
        "titre FROM suggestion_acquisition WHERE titre LIKE '%...%') avant "
        "d'appeler cet outil -- ne devine jamais un id. Si plusieurs lignes "
        "correspondent (doublon), demande confirmation avant de supprimer, "
        "ou précise laquelle (la plus récente sauf indication contraire)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"id": {"type": "integer", "description": "L'id exact de la ligne à supprimer"}},
        "required": ["id"],
    },
}

PROMPT_SYSTEME = """Tu es l'assistant de la section jeunesse de la Médiathèque d'Arcachon.

RÈGLE ABSOLUE, NON NÉGOCIABLE : chaque titre, prix, ISBN ou chiffre de prêt que
tu donnes doit venir d'un résultat RÉEL d'outil (executer_requete_sql ou
web_search) -- jamais de tes connaissances générales, même plausibles. Si une
information n'a pas été retournée par un outil, ne l'invente pas : dis
explicitement que tu ne l'as pas trouvée plutôt que de deviner. La base ne
contient QUE le fonds réel d'Arcachon -- elle ne contient aucune information
sur d'autres médiathèques, ni sur des titres que la médiathèque ne possède
pas.

Si un outil renvoie un champ "erreur" : ne le reformule JAMAIS vaguement
("une erreur technique est survenue"). Cite le texte exact de cette erreur
à l'utilisateur -- c'est souvent un problème de configuration (jeton ou
secret manquant) que seul un humain peut corriger, et une reformulation
vague l'empêche de comprendre quoi corriger.

Pour les questions sur le fonds (titre, auteur, prêts, désherbage, séries
incomplètes...) : utilise executer_requete_sql.

Pour les SUGGESTIONS D'ACQUISITION (proposer des titres à acheter) : la base
ne peut te dire que ce que la médiathèque possède déjà -- elle ne connaît
aucun titre extérieur. Pour proposer de vrais titres à acquérir :
  1. Interroge d'abord la base pour savoir ce qui existe déjà dans la
     catégorie/tranche d'âge demandée (pour ne jamais suggérer un doublon).
  2. Utilise web_search avec plusieurs requêtes ciblées si besoin (ex.
     "meilleurs albums 3-6 ans 2026", "sélection Ricochet albums",
     "coup de cœur album jeunesse nouveauté", nom d'une collection connue +
     "nouveautés") pour trouver de VRAIS titres actuels qui apparaissent
     réellement dans les résultats de recherche -- jamais des titres que tu
     "connais" de mémoire, même s'ils existent vraiment : l'origine doit
     être un résultat de recherche de CETTE conversation.
  3. AUCUN ISBN n'est nécessaire pour une liste de suggestions -- ne le
     cherche jamais, ne le mentionne jamais comme un manque ou un obstacle.
  4. Pour le prix : un budget prévisionnel n'exige pas un prix exact par
     titre. Si tu n'as pas trouvé de prix précis pour un titre donné, donne
     un prix moyen réaliste pour ce type d'ouvrage (cherché ou déduit des
     résultats web obtenus) et indique-le comme estimation -- ne refuse pas
     de répondre simplement parce que le prix exact ou l'ISBN manquent.
  5. Croise avec la base : ne propose que des titres absents du résultat
     SQL. Cite tes sources (sites consultés).
La seule chose à ne jamais inventer, c'est le TITRE lui-même -- il doit
venir d'un vrai résultat de recherche de cette conversation, jamais de ta
mémoire générale, même validée après coup. Si une recherche web ne donne
rien d'utile, reformule la requête et cherche encore (plusieurs requêtes
différentes valent mieux qu'une seule) avant de conclure que tu ne peux pas
répondre. Un prix estimé/moyen, clairement présenté comme tel, est
acceptable et même attendu pour ce genre de demande -- l'ISBN n'est jamais
un prérequis ni un motif de refus.

Pour les SUGGESTIONS DE LECTURE ("si on a aimé X, que lui conseiller dans
notre fonds ?") :
  1. Cherche d'abord X dans notre fonds (executer_requete_sql, par titre) :
     s'il y est, son genre/categorie/mots_cles/resume réels sont la
     meilleure base de comparaison -- utilise-les directement.
  2. Si X n'est pas dans notre fonds, ou pour mieux cerner ses thèmes,
     utilise web_search pour savoir de quoi parle X (genre, thèmes,
     tranche d'âge, ambiance, auteurs comparables).
  3. Interroge ensuite notre fonds pour trouver de vrais titres que NOUS
     POSSÉDONS PHYSIQUEMENT, partageant un genre/categorie/mots_cles/public
     réellement proche -- ce sont les seules suggestions valables.
N'affirme jamais qu'un livre de notre fonds "ressemble" à X sans t'appuyer
sur une vraie correspondance (genre, mots_cles, thème) trouvée par un outil.
Précise toujours sa cote et sa disponibilité actuelle (statut_exemplaire).

INTERDICTION ABSOLUE DE SUBSTITUTION : si l'utilisateur demande des titres
qu'on N'A PAS, ne réponds JAMAIS à la place avec des titres qu'on A DÉJÀ
(même si c'est une suggestion pertinente comme "racheter un exemplaire d'un
titre sous-emprunté ici mais populaire ailleurs") sans le dire EXPLICITEMENT
en toutes lettres au début de ta réponse ("Je n'ai pas pu chercher de
nouveaux titres, voici une autre piste : ..."). Changer de question sans le
signaler est pire que de refuser.

Si on te demande d'AJOUTER/NOTER un titre dans une liste de suggestions
(par exemple une demande d'un usager pour un livre absent du fonds) :
utilise ajouter_suggestion_acquisition -- tu en es capable, ne dis jamais
le contraire. Cette liste est rattachée à une personne (demandeur) : si la
demande ne précise pas qui (ex. "ajoute à la liste de Marjorie"), demande
qui avant d'ajouter. Vérifie d'abord via executer_requete_sql que le titre
n'est pas déjà dans le fonds. Cette liste est persistante : pour la
consulter ou l'exporter pour une personne en particulier ("montre-moi/
exporte la liste de Marjorie"), filtre avec WHERE demandeur = '...' dans
executer_requete_sql ou generer_export_excel.

Si on te demande de SUPPRIMER/RETIRER une suggestion de la liste : trouve
d'abord son id exact via executer_requete_sql (jamais en devinant), puis
utilise supprimer_suggestion_acquisition avec cet id. En cas de doublon,
précise lequel tu supprimes (le plus ancien sauf indication contraire) ou
demande confirmation si l'utilisateur n'a pas précisé.

Pour exporter en Excel des suggestions venant de web_search : utilise
generer_export_excel avec le paramètre lignes (jamais sql, qui ne peut
interroger que notre propre fonds et ne peut donc jamais contenir de titres
absents de la base).

Si l'utilisateur demande un export, un tableau, ou un fichier Excel à
télécharger sur ce qui EST dans le fonds : utilise generer_export_excel avec
sql -- ne décris jamais son contenu en table dans le texte, le bouton de
téléchargement apparaît automatiquement après ta réponse.

Réponds de façon concise, en français, avec les chiffres exacts retournés
par les outils. Si un outil ne retourne rien, dis-le clairement plutôt que
de deviner."""


def repondre(historique_existant, question, cle_api):
    """Travaille sur une COPIE de l'historique, jamais sur la liste
    st.session_state.messages_api directement. Si une nouvelle question
    arrive pendant qu'une réponse précédente est encore en cours (plusieurs
    recherches web qui prennent du temps), Streamlit peut abandonner
    l'exécution en cours en plein milieu -- sans cette précaution, l'objet
    partagé resterait alors à moitié écrit (un tool_use sans son
    tool_result), et toute la conversation deviendrait invalide. En
    travaillant sur une copie et en ne renvoyant le résultat qu'à la toute
    fin, un abandon en cours de route ne laisse plus aucune trace."""
    historique = list(historique_existant)
    historique.append({"role": "user", "content": question})
    client = Anthropic(api_key=cle_api)
    outils = [OUTIL_SQL, OUTIL_EXPORT, OUTIL_SUGGESTION, OUTIL_SUPPRESSION_SUGGESTION,
              {"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
    while True:
        reponse = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=PROMPT_SYSTEME,
            tools=outils,
            messages=historique,
        )
        historique.append({"role": "assistant", "content": reponse.content})
        if reponse.stop_reason != "tool_use":
            texte = "".join(b.text for b in reponse.content if b.type == "text")
            return texte, historique

        resultats_outils = []
        for bloc in reponse.content:
            if bloc.type != "tool_use":
                continue
            if bloc.name == "executer_requete_sql":
                resultat = executer_requete_sql(bloc.input.get("sql", ""))
            elif bloc.name == "generer_export_excel":
                contenu, n_lignes, erreur = generer_excel_bytes(bloc.input.get("sql"), bloc.input.get("lignes"))
                if erreur:
                    resultat = json.dumps({"erreur": erreur})
                else:
                    st.session_state["export_xlsx_pret"] = contenu
                    st.session_state["export_xlsx_lignes"] = n_lignes
                    resultat = json.dumps({
                        "statut": "ok", "lignes": n_lignes,
                        "info": "Fichier généré -- un bouton de téléchargement va apparaître juste sous ta réponse.",
                    })
            elif bloc.name == "ajouter_suggestion_acquisition":
                resultat = ajouter_suggestion_acquisition(**bloc.input)
            elif bloc.name == "supprimer_suggestion_acquisition":
                resultat = supprimer_suggestion_acquisition(**bloc.input)
            else:
                resultat = json.dumps({"erreur": "outil inconnu"})
            resultats_outils.append({"type": "tool_result", "tool_use_id": bloc.id, "content": resultat})
        historique.append({"role": "user", "content": resultats_outils})


# ----------------------------------------------------------------------------
# Dépôt de fichier -- enrichissement direct depuis l'interface, RÉSERVÉ à
# l'équipe (derrière le mot de passe si configuré). Utilise un jeton
# d'écriture séparé du jeton lecture-seule employé pour le chat : le chat
# reste strictement en lecture quoi qu'il arrive, même si cette fonction a
# un problème.
# ----------------------------------------------------------------------------
def deviner_type_fichier(nom):
    ext = os.path.splitext(nom)[1].lower()
    if ext == '.mrc':
        return 'catalogue'
    if ext in ('.xlsx', '.xls'):
        return 'statistiques'
    if ext == '.csv':
        return 'frequentation'
    return None


# Chaque ISBN qualifié est enregistré immédiatement (pas en un seul bloc à
# la fin) : même si la session Streamlit venait à être interrompue en cours
# de route, rien n'est perdu -- il suffit de redéposer le fichier, ou la
# tâche de fond sur le Mac prend le relais automatiquement pour le reste.


def traiter_fichier_depose(fichier_televerse, url_turso, jeton_ecriture):
    suffixe = os.path.splitext(fichier_televerse.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffixe) as tmp:
        tmp.write(fichier_televerse.getvalue())
        chemin_tmp = tmp.name

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import actualiser_catalogue
    import actualiser_statistiques
    import actualiser_frequentation
    import lancer_enrichissement

    connexion_ecriture = db.connect_avec_jeton(url_turso, jeton_ecriture)
    ancien_connect = db.connect
    db.connect = lambda *a, **k: connexion_ecriture  # bascule temporaire sur le jeton d'écriture

    tampon_sortie = io.StringIO()
    ancien_stdout = sys.stdout
    sys.stdout = tampon_sortie
    try:
        t = deviner_type_fichier(fichier_televerse.name)
        sys.argv = ['x', chemin_tmp]
        if t == 'catalogue':
            actualiser_catalogue.main()
        elif t == 'statistiques':
            actualiser_statistiques.main()
        elif t == 'frequentation':
            actualiser_frequentation.main()
        else:
            return False, "Type de fichier non reconnu (.mrc, .xlsx/.xls ou .csv attendu)."

        # Qualification automatique par recherche internet, sans plafond
        cur = connexion_ecriture.cursor()
        cur.execute("SELECT identifiant FROM notice WHERE type_document='LIVRE' AND categorie IS NULL ORDER BY identifiant")
        a_traiter = [r[0] for r in cur.fetchall()]
        if a_traiter:
            print(f"\nQualification automatique par recherche internet ({len(a_traiter)} ISBN)...")
            chemin_liste = chemin_tmp + "_isbn.txt"
            with open(chemin_liste, "w", encoding="utf-8") as f:
                f.write("\n".join(a_traiter) + "\n")
            sys.argv = ['lancer_enrichissement.py', chemin_liste]
            lancer_enrichissement.main()
            os.remove(chemin_liste)
        else:
            print("\nRien à qualifier par recherche internet pour cet import.")

        return True, tampon_sortie.getvalue()
    except Exception as e:
        return False, f"{tampon_sortie.getvalue()}\n\nErreur : {e}"
    finally:
        sys.stdout = ancien_stdout
        db.connect = ancien_connect
        connexion_ecriture.close()
        os.remove(chemin_tmp)


# ----------------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------------
st.title("📚 Médiathèque d'Arcachon — Assistant du fonds")
st.caption("Pose une question sur le fonds, en langage naturel. Les réponses viennent toujours de la base, jamais d'une supposition.")

cle_api = st.secrets.get("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", ""))
if not cle_api:
    st.error("Clé API Anthropic manquante -- à configurer dans les secrets de l'application.")
    st.stop()

mot_de_passe_requis = st.secrets.get("MOT_DE_PASSE", "")  # accès au chat, pour les agents
if mot_de_passe_requis:
    if "authentifie" not in st.session_state:
        st.session_state.authentifie = False
    if not st.session_state.authentifie:
        saisie = st.text_input("Mot de passe", type="password")
        if saisie:
            if saisie == mot_de_passe_requis:
                st.session_state.authentifie = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
        st.stop()

if "messages_affiches" not in st.session_state:
    st.session_state.messages_affiches = []
if "messages_api" not in st.session_state:
    st.session_state.messages_api = []

for msg in st.session_state.messages_affiches:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

question = st.chat_input("Quels mangas n'avons-nous jamais prêtés ?")
if question:
    st.session_state.messages_affiches.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        with st.spinner("Interrogation de la base..."):
            try:
                texte, nouvel_historique = repondre(st.session_state.messages_api, question, cle_api)
                st.session_state.messages_api = nouvel_historique  # commit uniquement sur succès complet
            except Exception as e:
                texte = f"Erreur : {e}. L'historique n'a pas été modifié, tu peux reposer ta question normalement."
        st.markdown(texte)
        if st.session_state.get("export_xlsx_pret"):
            n_lignes = st.session_state.get("export_xlsx_lignes", 0)
            st.download_button(
                f"📥 Télécharger le fichier Excel ({n_lignes} lignes)",
                data=st.session_state["export_xlsx_pret"],
                file_name=f"export_mediatheque_arcachon_{datetime.date.today().isoformat()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            del st.session_state["export_xlsx_pret"]
            del st.session_state["export_xlsx_lignes"]

    st.session_state.messages_affiches.append({"role": "assistant", "content": texte})

with st.sidebar:
    st.header("Fonds Arcachon")
    try:
        conn = db.connect(FICHIER_DB)
        total = conn.execute("SELECT COUNT(*) FROM notice").fetchall()[0][0]
        exemplaires = conn.execute("SELECT COUNT(*) FROM exemplaire").fetchall()[0][0]
        conn.close()
        st.metric("Notices", f"{total:,}".replace(",", " "))
        st.metric("Exemplaires", f"{exemplaires:,}".replace(",", " "))
    except Exception:
        st.write("Base indisponible.")

    st.divider()
    if st.button("Nouvelle conversation"):
        st.session_state.messages_affiches = []
        st.session_state.messages_api = []
        st.rerun()

    st.divider()
    with st.expander("📤 Mettre à jour le fonds"):
        mot_de_passe_import = st.secrets.get("MOT_DE_PASSE_IMPORT", "")
        if not mot_de_passe_import:
            st.caption("Non configuré -- ajoute MOT_DE_PASSE_IMPORT dans les secrets pour activer cette fonction.")
        else:
            if "import_authentifie" not in st.session_state:
                st.session_state.import_authentifie = False
            if not st.session_state.import_authentifie:
                saisie_import = st.text_input("Mot de passe import", type="password", key="mdp_import")
                if saisie_import:
                    if saisie_import == mot_de_passe_import:
                        st.session_state.import_authentifie = True
                        st.rerun()
                    else:
                        st.error("Mot de passe incorrect.")
            else:
                jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
                if not jeton_ecriture:
                    st.caption("TURSO_AUTH_TOKEN_ECRITURE manquant dans les secrets.")
                else:
                    st.caption("Catalogue (.mrc), statistiques (.xlsx/.xls) ou fréquentation (.csv).")
                    fichier_depose = st.file_uploader("Déposer un fichier", type=['mrc', 'xlsx', 'xls', 'csv'], key="depot")
                    if fichier_depose and st.button("Traiter ce fichier"):
                        with st.spinner("Traitement en cours (peut prendre plusieurs minutes)..."):
                            succes, sortie = traiter_fichier_depose(fichier_depose, db.TURSO_URL, jeton_ecriture)
                        if succes:
                            st.success("Fichier traité.")
                        else:
                            st.error("Une erreur s'est produite.")
                        st.code(sortie, language=None)

    if st.session_state.get("derniere_erreur_technique"):
        st.divider()
        with st.expander("🔧 Dernière erreur technique", expanded=True):
            st.code(st.session_state["derniere_erreur_technique"], language=None)
            if st.button("Effacer"):
                del st.session_state["derniere_erreur_technique"]
                st.rerun()
