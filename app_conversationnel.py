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
        "IMPORTANT : pour chercher TOUS les tomes d'une série (ex. 'tous les Naruto', "
        "'tome 61 de Naruto'), filtre sur la colonne serie (WHERE serie = 'Naruto'), "
        "JAMAIS sur titre -- titre contient souvent le sous-titre propre à ce tome "
        "précis (ex. titre='Frères unis dans le combat !!' pour le tome 61 de Naruto), "
        "pas le nom de la série. Chercher sur titre fait rater des tomes qui existent "
        "pourtant bel et bien. "
        "Autres tables disponibles si besoin : frequentation (date, nb_entrees) ; "
        "suggestion_acquisition (id, titre, demandeur, auteur, editeur, isbn, prix, "
        "motif, source, statut, date_ajout) -- SANS 's' à 'suggestion' ; "
        "suggestion_desherbage (id, titre, demandeur, isbn, cote, motif, nb_prets, "
        "dernier_pret, statut, date_ajout) ; "
        "suggestion_mise_en_avant (id, titre, demandeur, isbn, cote, motif, nb_prets, "
        "statut, date_ajout) ; "
        "desherbage_effectue (id, titre, demandeur, isbn, cote, motif, "
        "nb_prets_au_retrait, dernier_pret_au_retrait, date_retrait) -- "
        "historique des retraits réellement effectués (distinct des suggestions) ; "
        "journal_requetes (id, date_requete, question, sql_executees, nb_recherches_web, "
        "a_genere_export, a_modifie_suggestions, erreur) -- historique de toutes les "
        "questions posées, utile pour analyser l'usage de l'outil lui-même. "
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


# ─────────────────────── DÉSHERBAGE ───────────────────────────────────────────

def ajouter_suggestion_desherbage(titre, demandeur, isbn=None, cote=None,
                                   motif=None, nb_prets=None, dernier_pret=None):
    """Ajoute une suggestion de désherbage dans une liste persistante, par agent.
    Symétrique à suggestion_acquisition. Nécessite le jeton d'écriture."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "Fonction non configurée (TURSO_AUTH_TOKEN_ECRITURE manquant)."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_desherbage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL, demandeur TEXT, isbn TEXT, cote TEXT,
                motif TEXT, nb_prets INTEGER, dernier_pret TEXT,
                statut TEXT NOT NULL DEFAULT 'à valider',
                date_ajout TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO suggestion_desherbage (titre, demandeur, isbn, cote, motif, nb_prets, dernier_pret) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (titre, demandeur, isbn, cote, motif, nb_prets, dernier_pret),
        )
        conn.commit()
        conn.close()
        return json.dumps({"statut": "ok", "info": f"« {titre} » ajouté aux suggestions de désherbage de {demandeur}."})
    except Exception as e:
        import traceback; st.session_state["derniere_erreur_technique"] = traceback.format_exc()
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


def supprimer_suggestion_desherbage(id):
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "TURSO_AUTH_TOKEN_ECRITURE manquant."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        cur = conn.cursor(); cur.execute("SELECT titre FROM suggestion_desherbage WHERE id = ?", (id,))
        ligne = cur.fetchone()
        if not ligne:
            conn.close(); return json.dumps({"erreur": f"Aucune suggestion de désherbage avec l'id {id}."})
        conn.execute("DELETE FROM suggestion_desherbage WHERE id = ?", (id,))
        conn.commit(); conn.close()
        return json.dumps({"statut": "ok", "info": f"Suggestion de désherbage id {id} (« {ligne[0]} ») supprimée."})
    except Exception as e:
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


OUTIL_DESHERBAGE = {
    "name": "ajouter_suggestion_desherbage",
    "description": (
        "Ajoute un titre à la liste de suggestions de DÉSHERBAGE (retrait du fonds) "
        "d'un agent précis. Utilise cet outil quand on demande de noter un titre "
        "à étudier pour le pilon ou le retrait. AVANT d'ajouter, interroge "
        "executer_requete_sql pour récupérer les vraies données de l'exemplaire "
        "(nb_prets_cet_exemplaire, dernier_pret_cet_exemplaire, cote, isbn) et "
        "inclus-les -- ce sont les données qui permettront la décision humaine. "
        "Si le motif n'est pas précisé, déduis-le des données (ex. '0 prêt depuis "
        "2015, documentaire périmé'). La validation finale reste humaine."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "demandeur": {"type": "string"},
            "isbn": {"type": "string"},
            "cote": {"type": "string"},
            "motif": {"type": "string", "description": "Raison du désherbage (ex. '0 prêt depuis 2015')"},
            "nb_prets": {"type": "integer"},
            "dernier_pret": {"type": "string"},
        },
        "required": ["titre", "demandeur"],
    },
}

OUTIL_SUPPRESSION_DESHERBAGE = {
    "name": "supprimer_suggestion_desherbage",
    "description": "Supprime UNE suggestion de désherbage par son id (après vérification via executer_requete_sql).",
    "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
}


# ─────────────────────── MISE EN AVANT (PÉPITES) ───────────────────────────────

def ajouter_suggestion_mise_en_avant(titre, demandeur, isbn=None, cote=None,
                                      motif=None, nb_prets=None):
    """Ajoute une suggestion de mise en avant (présentoir, coup de cœur...)
    dans une liste persistante. Pour les pépites méconnues : livres peu empruntés
    mais de qualité reconnue (prix littéraires, bonnes critiques)."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "TURSO_AUTH_TOKEN_ECRITURE manquant."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_mise_en_avant (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL, demandeur TEXT, isbn TEXT, cote TEXT,
                motif TEXT, nb_prets INTEGER,
                statut TEXT NOT NULL DEFAULT 'à programmer',
                date_ajout TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO suggestion_mise_en_avant (titre, demandeur, isbn, cote, motif, nb_prets) VALUES (?, ?, ?, ?, ?, ?)",
            (titre, demandeur, isbn, cote, motif, nb_prets),
        )
        conn.commit(); conn.close()
        return json.dumps({"statut": "ok", "info": f"« {titre} » ajouté aux suggestions de mise en avant de {demandeur}."})
    except Exception as e:
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


def supprimer_suggestion_mise_en_avant(id):
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "TURSO_AUTH_TOKEN_ECRITURE manquant."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        cur = conn.cursor(); cur.execute("SELECT titre FROM suggestion_mise_en_avant WHERE id = ?", (id,))
        ligne = cur.fetchone()
        if not ligne:
            conn.close(); return json.dumps({"erreur": f"Aucune suggestion de mise en avant avec l'id {id}."})
        conn.execute("DELETE FROM suggestion_mise_en_avant WHERE id = ?", (id,))
        conn.commit(); conn.close()
        return json.dumps({"statut": "ok", "info": f"Suggestion id {id} (« {ligne[0]} ») supprimée."})
    except Exception as e:
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


OUTIL_MISE_EN_AVANT = {
    "name": "ajouter_suggestion_mise_en_avant",
    "description": (
        "Ajoute un titre à la liste de suggestions de MISE EN AVANT (présentoir, "
        "table thématique, coup de cœur...) d'un agent. Utilise cet outil pour les "
        "pépites méconnues : livres peu empruntés mais de qualité reconnue (prix "
        "littéraires, bonnes critiques). AVANT d'ajouter, récupère le vrai nombre de "
        "prêts et la cote via executer_requete_sql, puis vérifie via web_search si ce "
        "titre a reçu des distinctions. Inclus toujours le motif précis (ex. 'Seulement "
        "2 prêts mais Prix Sorcières 2023 -- mérite d'être mis en avant')."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "demandeur": {"type": "string"},
            "isbn": {"type": "string"},
            "cote": {"type": "string"},
            "motif": {"type": "string", "description": "Raison de la mise en avant (prix, thème, qualité...)"},
            "nb_prets": {"type": "integer"},
        },
        "required": ["titre", "demandeur"],
    },
}

OUTIL_SUPPRESSION_MISE_EN_AVANT = {
    "name": "supprimer_suggestion_mise_en_avant",
    "description": "Supprime UNE suggestion de mise en avant par son id.",
    "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
}


# ─────────────────────── RAPPORT HEBDOMADAIRE ──────────────────────────────────

def generer_rapport_import():
    """Synthèse automatique du fonds au moment de l'appel, utile après chaque
    import hebdomadaire. Renvoie un texte structuré + produit optionnellement
    un Excel des nouveaux titres de la semaine."""
    conn = db.connect(FICHIER_DB)
    cur = conn.cursor()
    lignes = []
    try:
        # Totaux généraux
        totaux = cur.execute("""
            SELECT
                COUNT(DISTINCT isbn) as nb_notices,
                COUNT(DISTINCT code_barres) as nb_exemplaires,
                (SELECT COUNT(*) FROM notice WHERE date_enrichissement IS NOT NULL) as enrichis,
                (SELECT COUNT(*) FROM notice WHERE categorie IS NULL AND type_document='LIVRE') as sans_categorie,
                (SELECT COUNT(*) FROM notice) as total_notices
            FROM vue_inventaire
        """).fetchone()
        lignes.append(f"📚 Fonds total : {totaux[4]} notices, {totaux[1]} exemplaires")
        lignes.append(f"✅ Notices enrichies : {totaux[2]} ({round(totaux[2]/max(totaux[4],1)*100)}%)")
        lignes.append(f"⚠ Livres encore sans catégorie : {totaux[3]}")

        # Nouveaux depuis 8 jours
        nouveaux = cur.execute("""
            SELECT COUNT(*) FROM notice
            WHERE date_creation >= datetime('now', '-8 days')
        """).fetchone()[0]
        lignes.append(f"🆕 Notices créées depuis 8 jours : {nouveaux}")

        # Top 5 séries les plus empruntées (réseau)
        lignes.append("\n🏆 Top 5 séries – prêts réseau :")
        for r in cur.execute("""
            SELECT serie, SUM(nb_prets_titre_reseau) as total
            FROM vue_inventaire
            WHERE serie IS NOT NULL
            GROUP BY serie ORDER BY total DESC LIMIT 5
        """).fetchall():
            lignes.append(f"   • {r[0]} — {r[1]} prêts")

        # Séries incomplètes (tomes manquants)
        manquants = cur.execute("""
            SELECT serie, MAX(CAST(tome AS INTEGER)) as dernier_tome, COUNT(*) as nb_tomes
            FROM notice WHERE serie IS NOT NULL AND tome IS NOT NULL AND tome != ''
            GROUP BY serie HAVING MAX(CAST(tome AS INTEGER)) > COUNT(*)
            ORDER BY MAX(CAST(tome AS INTEGER)) - COUNT(*) DESC LIMIT 5
        """).fetchall()
        if manquants:
            lignes.append("\n🔍 Séries potentiellement incomplètes (top 5) :")
            for r in manquants:
                lignes.append(f"   • {r[0]} : {r[2]} tomes présents sur {r[1]}")

        # Incohérences Decalog rapides
        sans_cote = cur.execute(
            "SELECT COUNT(*) FROM vue_inventaire WHERE cote IS NULL OR cote = ''"
        ).fetchone()[0]
        sans_statut = cur.execute(
            "SELECT COUNT(*) FROM vue_inventaire WHERE statut_exemplaire IS NULL OR statut_exemplaire = ''"
        ).fetchone()[0]
        if sans_cote or sans_statut:
            lignes.append(f"\n🔧 Points d'attention Decalog :")
            if sans_cote: lignes.append(f"   • {sans_cote} exemplaires sans cote")
            if sans_statut: lignes.append(f"   • {sans_statut} exemplaires sans statut")

    except Exception as e:
        lignes.append(f"Erreur lors de la génération du rapport : {e}")
    finally:
        conn.close()

    return "\n".join(lignes)


OUTIL_RAPPORT = {
    "name": "generer_rapport_import",
    "description": (
        "Génère une synthèse statistique du fonds à l'instant présent : totaux, "
        "taux d'enrichissement, nouveautés récentes, top séries, séries incomplètes, "
        "points d'attention Decalog. Utilise cet outil quand on demande un bilan, "
        "un résumé, un état des lieux de la collection, ou le rapport de la semaine. "
        "Ne renvoie aucun paramètre."
    ),
    "input_schema": {"type": "object", "properties": {}},
}


# ─────────────────────── DÉSHERBAGE EFFECTUÉ ───────────────────────────────────

def enregistrer_desherbage_effectue(titre, demandeur, isbn=None, cote=None,
                                     motif=None, nb_prets_au_retrait=None,
                                     dernier_pret_au_retrait=None):
    """Enregistre un retrait DE FONDS réellement effectué (distinct d'une suggestion).
    Permet de suivre ce qui a vraiment été retiré, pour analyse future."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "TURSO_AUTH_TOKEN_ECRITURE manquant."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS desherbage_effectue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titre TEXT NOT NULL, demandeur TEXT, isbn TEXT, cote TEXT,
                motif TEXT, nb_prets_au_retrait INTEGER, dernier_pret_au_retrait TEXT,
                date_retrait TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO desherbage_effectue (titre, demandeur, isbn, cote, motif, nb_prets_au_retrait, dernier_pret_au_retrait) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (titre, demandeur, isbn, cote, motif, nb_prets_au_retrait, dernier_pret_au_retrait),
        )
        conn.commit(); conn.close()
        return json.dumps({"statut": "ok", "info": f"« {titre} » enregistré dans l'historique des retraits."})
    except Exception as e:
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


def supprimer_desherbage_effectue(id):
    """Correction d'une erreur de saisie dans l'historique de désherbage."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return json.dumps({"erreur": "TURSO_AUTH_TOKEN_ECRITURE manquant."})
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        cur = conn.cursor(); cur.execute("SELECT titre FROM desherbage_effectue WHERE id = ?", (id,))
        ligne = cur.fetchone()
        if not ligne: conn.close(); return json.dumps({"erreur": f"Id {id} introuvable."})
        conn.execute("DELETE FROM desherbage_effectue WHERE id = ?", (id,))
        conn.commit(); conn.close()
        return json.dumps({"statut": "ok", "info": f"Retrait id {id} (« {ligne[0]} ») supprimé de l'historique."})
    except Exception as e:
        return json.dumps({"erreur": f"{type(e).__name__}: {e}"})


OUTIL_DESHERBAGE_EFFECTUE = {
    "name": "enregistrer_desherbage_effectue",
    "description": (
        "Enregistre un retrait RÉELLEMENT EFFECTUÉ dans l'historique de désherbage "
        "(table desherbage_effectue, distincte de suggestion_desherbage). Utilise cet "
        "outil quand un agent confirme qu'un livre a physiquement quitté les rayons. "
        "AVANT d'enregistrer, récupère via executer_requete_sql les données réelles "
        "de l'exemplaire (nb_prets, dernier_pret, cote, isbn) pour les conserver dans "
        "l'historique -- elles seront perdues dès que Decalog supprime la notice."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "titre": {"type": "string"},
            "demandeur": {"type": "string", "description": "Agent qui a effectué le retrait"},
            "isbn": {"type": "string"}, "cote": {"type": "string"},
            "motif": {"type": "string"}, "nb_prets_au_retrait": {"type": "integer"},
            "dernier_pret_au_retrait": {"type": "string"},
        },
        "required": ["titre", "demandeur"],
    },
}

OUTIL_SUPPRESSION_DESHERBAGE_EFFECTUE = {
    "name": "supprimer_desherbage_effectue",
    "description": "Supprime UNE entrée de l'historique de désherbage par son id (correction d'erreur uniquement).",
    "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]},
}


def journaliser_requete(question, sql_executees, nb_recherches_web, a_exporte, a_modifie_suggestions, erreur):
    """Enregistre chaque question posée au chat dans un journal persistant
    (journal_requetes), pour permettre d'étudier l'usage réel de l'outil --
    directement interrogeable comme n'importe quelle autre table via
    executer_requete_sql, sans tableau de bord séparé à construire.
    Best-effort strict : un échec d'écriture du journal ne doit jamais faire
    échouer la réponse réellement attendue par la personne qui pose la
    question."""
    jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
    if not jeton_ecriture:
        return
    try:
        conn = db.connect_avec_jeton(db.TURSO_URL, jeton_ecriture) if db.MODE_EN_LIGNE else db.connect(FICHIER_DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS journal_requetes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_requete TEXT NOT NULL DEFAULT (datetime('now')),
                question TEXT NOT NULL,
                sql_executees TEXT,
                nb_recherches_web INTEGER NOT NULL DEFAULT 0,
                a_genere_export INTEGER NOT NULL DEFAULT 0,
                a_modifie_suggestions INTEGER NOT NULL DEFAULT 0,
                erreur TEXT
            )
        """)
        conn.execute(
            "INSERT INTO journal_requetes "
            "(question, sql_executees, nb_recherches_web, a_genere_export, a_modifie_suggestions, erreur) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (question, "\n---\n".join(sql_executees) if sql_executees else None,
             nb_recherches_web, 1 if a_exporte else 0, 1 if a_modifie_suggestions else 0, erreur),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # le journal est un outil d'observabilité, jamais un point de blocage


PROMPT_SYSTEME = """Tu es l'assistant de la section jeunesse de la Médiathèque d'Arcachon.

RÈGLE ABSOLUE, NON NÉGOCIABLE : chaque titre, prix, ISBN ou chiffre de prêt que
tu donnes doit venir d'un résultat RÉEL d'outil (executer_requete_sql ou
web_search) -- jamais de tes connaissances générales, même plausibles. Si une
information n'a pas été retournée par un outil, ne l'invente pas. La base ne
contient QUE le fonds réel d'Arcachon.

Si un outil renvoie un champ "erreur" : cite le texte exact, ne reformule jamais
vaguement. INTERDICTION ABSOLUE DE SUBSTITUTION : si la demande porte sur des
titres absents du fonds, ne réponds jamais avec des titres qu'on possède déjà
sans le dire explicitement.

═══════════════════════════════════════════════════════
SYNONYMES ET ÉQUIVALENCES — à gérer TOUJOURS en interne
═══════════════════════════════════════════════════════
Ces équivalences doivent être transparentes pour l'utilisateur. Quand
quelqu'un demande "romans ado" ou "livres pour ados", gère ça seul sans
jamais demander à l'utilisateur de préciser la valeur exacte.

Public :
• "ado", "adolescent", "ados", "pour les ados", "12 ans et plus"
  → chercher : public IN ('Ado (12+)', 'Adolescent') [deux valeurs existent]
• "jeunesse", "jeunes", "enfants", "section jeunesse"
  → chercher : public IN ('Jeune', 'Jeunesse') [deux valeurs existent]

Catégorie :
• "roman jeunesse", "roman enfant", "roman junior"
  → categorie = 'Roman jeunesse'
• "roman ado", "roman ado/YA", "young adult", "YA"
  → categorie IN ('Roman ado / YA', 'Roman jeunesse') AND public IN ('Ado (12+)', 'Adolescent')
• "bande dessinée", "BD", "bandes dessinées"
  → categorie = 'BD'
• "album", "album illustré", "album jeunesse"
  → categorie = 'Album'
• "documentaire", "doc", "non-fiction"
  → categorie = 'Documentaire'
• "manga", "mangas"
  → categorie = 'Manga'

Genre (les genres doubles existent — utiliser LIKE plutôt que =) :
• "policier", "polar", "mystère" → genre LIKE '%Policier%'
• "fantastique", "fantasy", "heroic fantasy" → genre LIKE '%Fantastique%'
• "science-fiction", "SF", "sci-fi" → genre LIKE '%Science-fiction%'
• "horreur", "frissons", "peur" → genre LIKE '%Frissons%'
• "amour", "romance", "sentimental" → genre LIKE '%Amour%'
• "humour", "comique", "drôle" → genre LIKE '%Humour%'

Type :
• "livre", "roman", "BD", "album", "documentaire" → type = 'LIVRE'
• "film", "vidéo" → type = 'DVD'
• "jeu", "jeux" → type = 'JEU'
• "CD", "disque", "musique" → type = 'CD'

Disponibilité :
• "disponible", "empruntable", "à emprunter"
  → statut_exemplaire = 'A - Prêtable'

Ne jamais mentionner ces valeurs internes à l'utilisateur, ni lui demander
de préciser laquelle utiliser. Gère les ambiguïtés seul.

═══════════════════════════════════════════════════════
FONCTIONS DISPONIBLES — ce que tu sais faire
═══════════════════════════════════════════════════════

── CONSULTATION DU FONDS ──────────────────────────────
Toute question sur le fonds (titre, série, prêts, cote, statut...) :
executer_requete_sql. Pour les séries, toujours filtrer par serie (pas titre) --
un tome peut avoir un sous-titre différent du nom de la série.
Disponibilité = date du dernier import (~1x/semaine), pas l'instant présent --
le préciser à l'utilisateur.

── RAPPORT HEBDOMADAIRE / PROFIL STATISTIQUE ─────────
Quand on demande un bilan, résumé, état des lieux, profil de la collection,
ou "rapport de la semaine" : utilise generer_rapport_import (renvoie tout
d'un coup : totaux, enrichissement, nouveautés, top séries, séries incomplètes,
alertes Decalog). Pour des détails complémentaires (répartition par catégorie,
genre, public, année, taux d'emprunt par type) : enchaîne avec executer_requete_sql
puis generer_export_excel si demandé.

── VEILLE NOUVEAUTÉS DE SÉRIES ───────────────────────
"Y a-t-il de nouveaux tomes parus pour la série X ?" :
1. executer_requete_sql : MAX(CAST(tome AS INTEGER)) WHERE serie LIKE '%X%'
2. web_search "{nom de la série} tome {N+1} parution" pour voir si des
   tomes plus récents existent sur le marché.
3. Titres absents → proposer de les ajouter à suggestion_acquisition.

── SÉRIES INTERROMPUES À FORT USAGE ─────────────────
Pour les séries que les lecteurs cherchent encore mais qui ne peuvent plus
être complétées : executer_requete_sql en croisant statut_publication
(valeurs comme "Épuisé", "Abandonné"...) et nb_prets_cet_exemplaire élevé.
Ces titres méritent une note dans suggestion_desherbage (avec contexte) OU
une suggestion d'acquisition d'une série de substitution.

── DOUBLONS POTENTIELS ────────────────────────────────
Pour détecter des doublons :
SELECT titre, auteur, COUNT(*) as n, GROUP_CONCAT(identifiant) as isbns
FROM notice GROUP BY LOWER(TRIM(titre)), auteur HAVING n > 1
Précise toujours les ISBN et dates (deux éditions légitimes existent).
Pour une liste à transmettre à Decalog : generer_export_excel avec sql.

── HISTORIQUE DE DÉSHERBAGE EFFECTUÉ ─────────────────
Quand un agent confirme qu'un livre A ÉTÉ retiré physiquement (pas juste
"à étudier") : enregistrer_desherbage_effectue. AVANT d'appeler l'outil,
récupère via executer_requete_sql les données réelles de l'exemplaire
(nb_prets, dernier_pret, cote, isbn) -- elles seront perdues une fois que
Decalog supprime la notice. Table : desherbage_effectue.
Pour analyser si les décisions étaient bonnes : croiser avec
suggestion_acquisition (titres retirés qui ont ensuite été redemandés).

── AUDIT QUALITÉ DECALOG ──────────────────────────────
Pour détecter des incohérences (EAN absent mais cote présente, exemplaires sans
statut, doublons potentiels...) : executer_requete_sql sur notice et exemplaire
en LEFT JOIN, puis generer_export_excel pour produire la liste à transmettre.
Exemples de requêtes utiles :
• Notices sans EAN : SELECT identifiant, titre FROM notice WHERE identifiant IS NULL
• Exemplaires sans statut : SELECT * FROM vue_inventaire WHERE statut_exemplaire IS NULL
• Cote sans exemplaire réel : notice LEFT JOIN exemplaire ON identifiant -- notice seule

── SUGGESTIONS D'ACQUISITION ─────────────────────────
1. Interroge la base pour ce qui existe déjà (éviter les doublons).
2. web_search avec plusieurs sources variées (Fnac, Decitre, LesLibraires.fr,
   Mollat, Ricochet-jeunes.org, Pépites/BnF, prix littéraires, festivals).
   Jamais de titres de mémoire. Prix estimé acceptable, ISBN non requis.
3. Vise 80-100% du budget indiqué -- plusieurs recherches si nécessaire.
Titres trouvés → generer_export_excel avec paramètre lignes (pas sql).
Pour ajouter à une liste : ajouter_suggestion_acquisition (avec demandeur).

── DÉSHERBAGE ────────────────────────────────────────
Pour identifier des candidats au pilon (peu/pas empruntés, anciens, périmés...) :
executer_requete_sql sur vue_inventaire (nb_prets_cet_exemplaire, dernier_pret,
annee, type, categorie). Pour ajouter à la liste de désherbage d'un agent :
ajouter_suggestion_desherbage -- inclure toujours nb_prets et dernier_pret réels.
La décision finale est TOUJOURS humaine : l'outil ne décide jamais du retrait.

── PÉPITES MÉCONNUES / MISE EN AVANT ─────────────────
Livres peu empruntés qui méritent mieux (prix littéraires, bonnes critiques) :
1. executer_requete_sql pour trouver les titres sous-empruntés (nb_prets faible).
2. web_search pour vérifier si le titre ou l'auteur a reçu des distinctions.
3. Si oui : ajouter_suggestion_mise_en_avant avec le motif précis (ex. "2 prêts
   seulement mais Prix Sorcières 2023 -- mérite d'être mis en avant en présentoir").

── BIBLIOGRAPHIES THÉMATIQUES ───────────────────────
Pour une animation, une visite de classe, un thème donné : executer_requete_sql
en filtrant sur genre, mots_cles, public, statut_exemplaire (pour ne sélectionner
que les disponibles si demandé), puis generer_export_excel pour la liste imprimable.
Ajoute toujours la cote pour faciliter le travail en rayon.

── SUGGESTIONS DE LECTURE ────────────────────────────
"Si un usager a aimé X, quoi lui proposer ?" :
1. Cherche X dans notre fonds (genre/mots_cles/resume réels = meilleure base).
2. Si X absent : web_search pour cerner ses thèmes.
3. executer_requete_sql pour vrais titres disponibles avec genre/mots_cles proches.
Précise toujours la cote et la disponibilité (à la date du dernier import).

── DEMANDES INSATISFAITES ────────────────────────────
Quand un usager demande un livre absent du fonds : vérifie d'abord que c'est
bien absent (executer_requete_sql), puis propose de l'ajouter à la liste
de suggestions avec ajouter_suggestion_acquisition, motif = "Demande usager",
demandeur = le nom de l'agent au comptoir (ou "Public" si pas précisé).

── LISTES PERSISTANTES (AJOUT/SUPPRESSION/EXPORT) ───
Trois types de listes, chacune avec add/delete/export :
• suggestion_acquisition -- achats envisagés
• suggestion_desherbage  -- retraits envisagés (avec nb_prets, dernier_pret, cote)
• suggestion_mise_en_avant -- pépites à mettre en valeur
Chaque liste filtrée par demandeur (WHERE demandeur = '...'). Pour supprimer,
trouver l'id via executer_requete_sql d'abord. Pour exporter, generer_export_excel
avec sql = SELECT ... FROM suggestion_XXX WHERE demandeur = '...'.
Pour ajouter PLUSIEURS titres d'un coup : plusieurs appels d'outil successifs,
un par titre.

── JOURNAL D'USAGE ───────────────────────────────────
La table journal_requetes (id, date_requete, question, sql_executees,
nb_recherches_web, a_genere_export, a_modifie_suggestions, erreur) enregistre
automatiquement chaque question. Pour analyser l'usage de l'outil lui-même,
utilise executer_requete_sql sur cette table.

── NOTICES SANS EAN DECALOG ───────────────────────────
Certains exemplaires physiques existent dans les rayons mais leur notice
Decalog n'a pas d'EAN renseigné. Ces notices entrent en base avec un
identifiant préfixé "CB:" (ex. CB:0123456789). Quand tu les rencontres :
• Ne dis JAMAIS qu'un titre est absent du fonds si son isbn commence par "CB:"
• Précise qu'il est bien présent physiquement, mais sans EAN dans Decalog
• Signale qu'une correction dans Decalog serait nécessaire pour un
  fonctionnement optimal (notamment pour la recherche par ISBN).

Réponds en français, avec les chiffres exacts retournés par les outils.
Si un outil ne retourne rien, dis-le clairement."""


def repondre(historique_existant, question, cle_api):
    """Travaille sur une COPIE de l'historique, jamais sur la liste
    st.session_state.messages_api directement. Si une nouvelle question
    arrive pendant qu'une réponse précédente est encore en cours (plusieurs
    recherches web qui prennent du temps), Streamlit peut abandonner
    l'exécution en cours en plein milieu -- sans cette précaution, l'objet
    partagé resterait alors à moitié écrit (un tool_use sans son
    tool_result), et toute la conversation deviendrait invalide. En
    travaillant sur une copie et en ne renvoyant le résultat qu'à la toute
    fin, un abandon en cours de route ne laisse plus aucune trace.

    Chaque appel est journalisé (succès ou échec) dans journal_requetes,
    pour permettre d'étudier l'usage réel de l'outil a posteriori."""
    historique = list(historique_existant)
    historique.append({"role": "user", "content": question})
    client = Anthropic(api_key=cle_api)
    outils = [
        OUTIL_SQL, OUTIL_EXPORT, OUTIL_RAPPORT,
        OUTIL_SUGGESTION, OUTIL_SUPPRESSION_SUGGESTION,
        OUTIL_DESHERBAGE, OUTIL_SUPPRESSION_DESHERBAGE,
        OUTIL_MISE_EN_AVANT, OUTIL_SUPPRESSION_MISE_EN_AVANT,
        OUTIL_DESHERBAGE_EFFECTUE, OUTIL_SUPPRESSION_DESHERBAGE_EFFECTUE,
        {"type": "web_search_20250305", "name": "web_search", "max_uses": 10},
    ]

    sql_executees = []
    nb_recherches_web = 0
    a_exporte = False
    a_modifie_suggestions = False
    erreur_pour_journal = None

    try:
        while True:
            reponse = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=8000,
                system=PROMPT_SYSTEME,
                tools=outils,
                messages=historique,
            )
            historique.append({"role": "assistant", "content": reponse.content})

            try:  # champ officiel de comptage des recherches web côté serveur
                nb_recherches_web += reponse.usage.server_tool_use.web_search_requests
            except Exception:
                pass

            if reponse.stop_reason != "tool_use":
                texte = "".join(b.text for b in reponse.content if b.type == "text")
                return texte, historique

            resultats_outils = []
            for bloc in reponse.content:
                if bloc.type != "tool_use":
                    continue
                if bloc.name == "executer_requete_sql":
                    sql = bloc.input.get("sql", "")
                    sql_executees.append(sql)
                    resultat = executer_requete_sql(sql)
                elif bloc.name == "generer_export_excel":
                    a_exporte = True
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
                    a_modifie_suggestions = True
                    resultat = ajouter_suggestion_acquisition(**bloc.input)
                elif bloc.name == "supprimer_suggestion_acquisition":
                    a_modifie_suggestions = True
                    resultat = supprimer_suggestion_acquisition(**bloc.input)
                elif bloc.name == "ajouter_suggestion_desherbage":
                    a_modifie_suggestions = True
                    resultat = ajouter_suggestion_desherbage(**bloc.input)
                elif bloc.name == "supprimer_suggestion_desherbage":
                    a_modifie_suggestions = True
                    resultat = supprimer_suggestion_desherbage(**bloc.input)
                elif bloc.name == "ajouter_suggestion_mise_en_avant":
                    a_modifie_suggestions = True
                    resultat = ajouter_suggestion_mise_en_avant(**bloc.input)
                elif bloc.name == "supprimer_suggestion_mise_en_avant":
                    a_modifie_suggestions = True
                    resultat = supprimer_suggestion_mise_en_avant(**bloc.input)
                elif bloc.name == "generer_rapport_import":
                    resultat = json.dumps({"rapport": generer_rapport_import()})
                elif bloc.name == "enregistrer_desherbage_effectue":
                    a_modifie_suggestions = True
                    resultat = enregistrer_desherbage_effectue(**bloc.input)
                elif bloc.name == "supprimer_desherbage_effectue":
                    a_modifie_suggestions = True
                    resultat = supprimer_desherbage_effectue(**bloc.input)
                else:
                    resultat = json.dumps({"erreur": "outil inconnu"})
                resultats_outils.append({"type": "tool_result", "tool_use_id": bloc.id, "content": resultat})
            historique.append({"role": "user", "content": resultats_outils})
    except Exception as e:
        erreur_pour_journal = f"{type(e).__name__}: {e}"
        raise
    finally:
        journaliser_requete(question, sql_executees, nb_recherches_web, a_exporte, a_modifie_suggestions, erreur_pour_journal)


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

        # Rapport de synthèse automatique après chaque import catalogue
        if t == 'catalogue':
            print("\n" + "─" * 60)
            print("RAPPORT DE SYNTHÈSE")
            print("─" * 60)
            db.connect = lambda *a, **k: connexion_ecriture  # garder la connexion d'écriture active
            print(generer_rapport_import())
            print("─" * 60)

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
