"""
Point de connexion UNIQUE à la base, partagé par tous les scripts.

  - Si TURSO_DATABASE_URL et TURSO_AUTH_TOKEN sont définies (dans l'environnement
    ou dans un fichier .env à côté de ce module) -> connexion à la base
    hébergée en ligne chez Turso.
  - Sinon -> connexion locale classique à inventaire.db, comme avant.

Chaque script n'a besoin que d'un seul changement :
    AVANT : import sqlite3 ; conn = sqlite3.connect(FICHIER_DB)
    APRÈS : import db       ; conn = db.connect()

Tout le reste (cur.execute, cur.fetchall, conn.commit, conn.row_factory...)
continue de fonctionner à l'identique, en local comme en ligne.

IMPORTANT -- non testé contre une vraie base Turso depuis cet environnement
(pas d'accès réseau ici). À valider ensemble une fois la base créée.
"""

import os
import sqlite3

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# Correctif connu macOS + Python.org : sans ça, toute connexion HTTPS
# (donc Turso) échoue avec "certificate verify failed". On pointe Python
# vers le paquet de certificats fourni par 'certifi' -- une fois pour
# toutes, sans dépendre d'un script d'installation externe à retrouver.
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(certifi.where()))
except ImportError:
    pass


def _charger_dotenv():
    """Lit un éventuel fichier .env (TURSO_DATABASE_URL=... / TURSO_AUTH_TOKEN=...)
    pour éviter d'avoir à définir les variables d'environnement à la main
    à chaque session de Terminal."""
    chemin = os.path.join(DOSSIER, ".env")
    if not os.path.exists(chemin):
        return
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


_charger_dotenv()

TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")
MODE_EN_LIGNE = bool(TURSO_URL and TURSO_TOKEN)


# ----------------------------------------------------------------------------
# Mode local -- comportement strictement inchangé (compatibilité totale avec
# tout ce qui a déjà été testé jusqu'ici)
# ----------------------------------------------------------------------------
def _connect_local(fichier_db=None):
    chemin = fichier_db or os.path.join(DOSSIER, "inventaire.db")
    return sqlite3.connect(chemin)


# ----------------------------------------------------------------------------
# Mode Turso -- adaptateur minimal qui imite l'interface sqlite3 utilisée
# dans nos scripts (cursor / execute / fetchall / fetchone / commit / close /
# row_factory). Non testé en conditions réelles -- à valider ensemble.
# ----------------------------------------------------------------------------
class _LigneAdaptee:
    """Imite sqlite3.Row : accès par position OU par nom de colonne, et
    convertible en dict (utilisé par exporter_fonds.py et app_conversationnel.py)."""
    def __init__(self, colonnes, valeurs):
        self._colonnes = colonnes
        self._valeurs = valeurs

    def __getitem__(self, cle):
        if isinstance(cle, int):
            return self._valeurs[cle]
        return self._valeurs[self._colonnes.index(cle)]

    def keys(self):
        return self._colonnes

    def __iter__(self):
        return iter(self._valeurs)

    def __len__(self):
        return len(self._valeurs)

    def __repr__(self):
        return repr(dict(zip(self._colonnes, self._valeurs)))


import concurrent.futures

_executeur_global = concurrent.futures.ThreadPoolExecutor(max_workers=4)
DELAI_MAX_SECONDES = 30  # au-delà, on considère que c'est bloqué, pas juste lent


def _appeler_avec_delai_max(fonction, *args, **kwargs):
    """Exécute un appel potentiellement bloquant avec une limite de temps
    stricte -- sans ça, une connexion qui ne répond plus (ni erreur, ni
    succès) bloquerait le script indéfiniment et silencieusement, sans
    qu'aucun message n'apparaisse jamais dans le journal."""
    futur = _executeur_global.submit(fonction, *args, **kwargs)
    return futur.result(timeout=DELAI_MAX_SECONDES)


class _CurseurTurso:
    """Enveloppe légère autour du curseur réel de 'libsql' -- son interface
    est déjà très proche de sqlite3 (DB-API), donc peu de traduction à faire.
    Reconnecte automatiquement si le flux Turso a expiré (scripts qui
    tournent plusieurs heures/jours sans interruption), avec une limite de
    temps stricte à chaque tentative pour ne jamais bloquer en silence."""
    def __init__(self, curseur_reel, connexion):
        self._curseur = curseur_reel
        self._connexion = connexion

    def execute(self, sql, params=()):
        valeurs = list(params) if params else []
        try:
            _appeler_avec_delai_max(self._curseur.execute, sql, valeurs)
        except Exception:
            # Le flux Turso peut expirer sur une connexion ouverte trop
            # longtemps -- on reconnecte et on retente, jusqu'à 3 fois,
            # plutôt que de laisser planter un calcul de plusieurs jours
            # pour une coupure de session normale côté serveur.
            derniere_erreur = None
            for _ in range(3):
                try:
                    self._connexion._reconnecter()
                    self._curseur = self._connexion._conn.cursor()
                    _appeler_avec_delai_max(self._curseur.execute, sql, valeurs)
                    derniere_erreur = None
                    break
                except Exception as e:
                    derniere_erreur = e
            if derniere_erreur is not None:
                raise derniere_erreur
        return self

    def executemany(self, sql, sequence_params):
        for params in sequence_params:
            self.execute(sql, params)
        return self

    def _colonnes(self):
        desc = getattr(self._curseur, "description", None)
        return [c[0] for c in desc] if desc else None

    def _ligne(self, valeurs):
        if self._connexion.row_factory is not None:
            colonnes = self._colonnes()
            if colonnes:
                return _LigneAdaptee(colonnes, list(valeurs))
        return tuple(valeurs)

    def fetchall(self):
        return [self._ligne(r) for r in self._curseur.fetchall()]

    def fetchone(self):
        r = self._curseur.fetchone()
        return self._ligne(r) if r is not None else None

    @property
    def rowcount(self):
        return getattr(self._curseur, "rowcount", -1)

    def close(self):
        pass


class _ConnexionTurso:
    def __init__(self, url, auth_token):
        self._url = url
        self._auth_token = auth_token
        self.row_factory = None
        self._reconnecter()

    def _reconnecter(self):
        import libsql
        self._conn = _appeler_avec_delai_max(
            libsql.connect, database=self._url, auth_token=self._auth_token
        )

    def cursor(self):
        return _CurseurTurso(self._conn.cursor(), self)

    def execute(self, sql, params=()):
        return self.cursor().execute(sql, params)

    def executescript(self, script_sql):
        for instruction in script_sql.split(";"):
            instruction = instruction.strip()
            if instruction:
                self._conn.execute(instruction)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def connect(fichier_db_local=None):
    """Point d'entrée unique : retourne une connexion Turso si configurée,
    sinon une connexion sqlite3 locale classique."""
    if MODE_EN_LIGNE:
        return _ConnexionTurso(TURSO_URL, TURSO_TOKEN)
    return _connect_local(fichier_db_local)


def connect_avec_jeton(url, auth_token):
    """Connexion Turso explicite avec un jeton précis, sans passer par la
    détection automatique via variables d'environnement -- utile quand un
    jeton différent du jeton par défaut est nécessaire (ex: un jeton
    d'écriture dédié, distinct du jeton lecture-seule utilisé ailleurs)."""
    return _ConnexionTurso(url, auth_token)


# Compatibilité avec le code existant qui fait parfois `sqlite3.Row` --
# en mode Turso, on active simplement le mode "ligne nommée" sur la connexion.
Row = sqlite3.Row
