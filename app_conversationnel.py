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

PROMPT_SYSTEME = """Tu es l'assistant de la section jeunesse de la Médiathèque d'Arcachon.
Tu réponds aux questions sur le fonds en interrogeant la base via l'outil
executer_requete_sql -- jamais en inventant une réponse à partir de tes
connaissances générales sur les livres. Si une question porte sur un titre,
un auteur, des statistiques de prêt, du désherbage, des acquisitions, des
séries incomplètes, etc., construis la requête SQL adaptée et appelle l'outil.
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
            tools=[OUTIL_SQL],
            messages=messages,
        )
        if reponse.stop_reason != "tool_use":
            texte = "".join(b.text for b in reponse.content if b.type == "text")
            return texte, messages

        messages.append({"role": "assistant", "content": reponse.content})
        resultats_outils = []
        for bloc in reponse.content:
            if bloc.type == "tool_use":
                resultat = executer_requete_sql(bloc.input.get("sql", ""))
                resultats_outils.append({
                    "type": "tool_result", "tool_use_id": bloc.id, "content": resultat,
                })
        messages.append({"role": "user", "content": resultats_outils})


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
