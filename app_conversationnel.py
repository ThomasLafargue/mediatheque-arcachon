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
        "Autres tables disponibles si besoin : frequentation (date, nb_entrees). "
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


def generer_excel_bytes(sql=None):
    """Construit un export xlsx en mémoire. Sans sql : fonds complet. Avec sql :
    export filtré selon la demande de l'utilisateur (mêmes garde-fous SELECT-only
    qu'executer_requete_sql)."""
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
            cellule = ws.cell(row=i, column=c, value=ligne[cle])
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
        "Génère un fichier Excel téléchargeable. Utilise cet outil dès que "
        "l'utilisateur demande un export, un tableau, un fichier Excel/xlsx, ou "
        "veut 'télécharger' une liste. Sans argument sql : exporte le fonds "
        "complet avec toutes les colonnes utiles. Avec sql : exporte uniquement "
        "le résultat de cette requête SELECT (ex. seulement les mangas, ou les "
        "livres jamais prêtés) -- reprends les mêmes colonnes que celles "
        "décrites pour executer_requete_sql."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "Requête SELECT optionnelle pour filtrer l'export"}
        },
    },
}

PROMPT_SYSTEME = """Tu es l'assistant de la section jeunesse de la Médiathèque d'Arcachon.
Tu réponds aux questions sur le fonds en interrogeant la base via l'outil
executer_requete_sql -- jamais en inventant une réponse à partir de tes
connaissances générales sur les livres. Si une question porte sur un titre,
un auteur, des statistiques de prêt, du désherbage, des acquisitions, des
séries incomplètes, etc., construis la requête SQL adaptée et appelle l'outil.
Si l'utilisateur demande un export, un tableau, ou un fichier Excel à
télécharger, utilise l'outil generer_export_excel (avec ou sans filtre selon
la demande) -- ne décris jamais son contenu en table dans le texte, le bouton
de téléchargement apparaîtra automatiquement après ta réponse.
Réponds de façon concise, en français, avec les chiffres exacts retournés
par la base. Si une requête ne retourne rien, dis-le clairement plutôt que
de deviner. N'utilise jamais d'autre source que la base de données."""


def repondre(messages, cle_api):
    client = Anthropic(api_key=cle_api)
    while True:
        reponse = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=PROMPT_SYSTEME,
            tools=[OUTIL_SQL, OUTIL_EXPORT],
            messages=messages,
        )
        if reponse.stop_reason != "tool_use":
            texte = "".join(b.text for b in reponse.content if b.type == "text")
            return texte, messages

        messages.append({"role": "assistant", "content": reponse.content})
        resultats_outils = []
        for bloc in reponse.content:
            if bloc.type != "tool_use":
                continue
            if bloc.name == "executer_requete_sql":
                resultat = executer_requete_sql(bloc.input.get("sql", ""))
            elif bloc.name == "generer_export_excel":
                contenu, n_lignes, erreur = generer_excel_bytes(bloc.input.get("sql"))
                if erreur:
                    resultat = json.dumps({"erreur": erreur})
                else:
                    st.session_state["export_xlsx_pret"] = contenu
                    st.session_state["export_xlsx_lignes"] = n_lignes
                    resultat = json.dumps({
                        "statut": "ok", "lignes": n_lignes,
                        "info": "Fichier généré -- un bouton de téléchargement va apparaître juste sous ta réponse.",
                    })
            else:
                resultat = json.dumps({"erreur": "outil inconnu"})
            resultats_outils.append({"type": "tool_result", "tool_use_id": bloc.id, "content": resultat})
        messages.append({"role": "user", "content": resultats_outils})


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


def traiter_fichier_depose(fichier_televerse, url_turso, jeton_ecriture):
    suffixe = os.path.splitext(fichier_televerse.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffixe) as tmp:
        tmp.write(fichier_televerse.getvalue())
        chemin_tmp = tmp.name

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import actualiser_catalogue
    import actualiser_statistiques
    import actualiser_frequentation

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

mot_de_passe_requis = st.secrets.get("MOT_DE_PASSE", "")
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

    st.session_state.messages_api.append({"role": "user", "content": question})

    with st.chat_message("assistant"):
        with st.spinner("Interrogation de la base..."):
            try:
                texte, st.session_state.messages_api = repondre(st.session_state.messages_api, cle_api)
            except Exception as e:
                texte = f"Erreur : {e}"
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
        jeton_ecriture = st.secrets.get("TURSO_AUTH_TOKEN_ECRITURE", "")
        if not jeton_ecriture:
            st.caption("Non configuré -- ajoute TURSO_AUTH_TOKEN_ECRITURE dans les secrets pour activer cette fonction.")
        else:
            st.caption("Catalogue (.mrc), statistiques (.xlsx/.xls) ou fréquentation (.csv).")
            fichier_depose = st.file_uploader("Déposer un fichier", type=['mrc', 'xlsx', 'xls', 'csv'], key="depot")
            if fichier_depose and st.button("Traiter ce fichier"):
                with st.spinner("Traitement en cours..."):
                    succes, sortie = traiter_fichier_depose(fichier_depose, db.TURSO_URL, jeton_ecriture)
                if succes:
                    st.success("Fichier traité.")
                else:
                    st.error("Une erreur s'est produite.")
                st.code(sortie, language=None)
                st.caption("Rappel : la qualification par recherche internet (catégorie/genre "
                           "pour les nouveaux livres) se fait toujours séparément, sur ton Mac.")
