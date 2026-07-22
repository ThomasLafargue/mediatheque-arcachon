# MIGRATION TURSO — Médiathèque d'Arcachon (MAAT)

> Document de référence technique — mis à jour le 2026-07-22

---

## CONTEXTE

L'application de gestion du fonds de la Médiathèque d'Arcachon (MAAT) utilise
**Turso** comme base de données cloud SQLite, accessible depuis Streamlit Cloud
et depuis le Mac local via le même driver `libsql`.

---

## CONNEXION

### URL de la base
```
libsql://mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io
```

### Jetons (dans `.env` local et secrets Streamlit)
```
TURSO_DATABASE_URL=libsql://mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io
TURSO_AUTH_TOKEN=<jeton lecture>
TURSO_AUTH_TOKEN_ECRITURE=<jeton écriture>
```

### Connexion via `db.py`
```python
import db
conn = db.connect()          # lecture
conn = db.connect_ecriture() # écriture
```

---

## SCHÉMA DE LA BASE

### TABLE `notice` (une ligne par titre)
```sql
identifiant          TEXT     -- EAN/ISBN ou CB:xxxxx si pas d'EAN
type_document        TEXT     -- 'LIVRE', 'DVD', 'JEU', 'CD'
titre                TEXT
serie                TEXT     -- nom de la série (NULL si hors-série)
tome                 TEXT     -- numéro de tome en texte ('1','2','HS'…)
collection           TEXT
createurs            TEXT     -- auteur(s) ← PAS "auteur"
createurs_secondaires TEXT
traducteur           TEXT
editeur              TEXT
date_publication     TEXT     -- 'YYYY' ou 'YYYY-MM-DD' ← PAS "annee"
categorie            TEXT     -- 'Roman jeunesse','BD','Manga','Album'…
genre                TEXT     -- peut être double : 'Policier / SF'
public_vise          TEXT     -- 'Jeune','Ado (12+)','Adulte'…
age_recommande       TEXT
score_confiance      REAL
date_enrichissement  TEXT
resume               TEXT
image_url            TEXT
dewey                TEXT
dewey_libelle        TEXT
mots_cles            TEXT
nb_prets_total       INTEGER  -- ← PAS "nb_prets"
nb_prets_annee_courante INTEGER
nb_prets_n1          INTEGER
nb_prets_n2          INTEGER
nb_prets_n3          INTEGER
nb_prets_fonctionnels INTEGER
date_dernier_pret    TEXT
date_maj_prets       TEXT
champs_a_verifier_decalog TEXT  -- ajoutée 2026-07-22, cf. section provenance ci-dessous
```

### TABLE `exemplaire` (une ligne par exemplaire physique)
```sql
id                    INTEGER
identifiant           TEXT     -- clé vers notice
cote                  TEXT     -- ex: 'BDJ/ONE/1'
code_barre_exemplaire TEXT
date_acquisition      TEXT
statut                TEXT     -- 'A - Prêtable', 'P - En prêt'…
site                  TEXT     -- 'Arcachon', 'La Teste'…
public_vise           TEXT
support               TEXT
prix                  REAL
nb_prets_total        INTEGER
annee_dernier_pret    TEXT
date_maj              TEXT
```

### TABLE `frequentation`
```sql
date        TEXT     -- 'YYYY-MM-DD'
nb_entrees  INTEGER
```

### TABLE `suggestion_acquisition`
```sql
id, titre, auteur, editeur, isbn, prix, motif, source, demandeur, date_ajout
```

### TABLE `desherbage_effectue`
```sql
id, identifiant, titre, createurs, motif, date_retrait, operateur
```

---

## CONTRAINTES TURSO (IMPORTANT)

- **Pas de `cursor.description`** — utiliser `fetchall()` avec accès par index
- **Pas de `ORDER BY` dans `GROUP_CONCAT()`** — utiliser un tri externe
- **Dates** : stocker en TEXT 'YYYY-MM-DD', filtrer avec `SUBSTR(date_publication,1,4)`
- **Tomes numériques** : `tome GLOB '[0-9]*'` puis `CAST(tome AS INTEGER)`
- **LIKE** insensible à la casse pour ASCII mais PAS pour les accents

---

## ÉTAT DE LA BASE (2026-07-21)

| Indicateur | Valeur |
|------------|--------|
| Notices | 44 288 |
| Exemplaires | 44 677 |
| Notices enrichies | 39 427 (89%) |
| Jours de fréquentation | 1 921 (2020-01-30 → 2026-07-16) |
| Dernière MAJ Decalog | 2026-07-19 |

---

## SCRIPTS D'IMPORT

| Script | Rôle | Déclenchement |
|--------|------|---------------|
| `traiter_fichier.py` | Routeur — détecte le type de fichier | `python3 traiter_fichier.py <fichier>` |
| `actualiser_catalogue.py` | Import notices .mrc | via traiter_fichier |
| `actualiser_statistiques.py` | Import prêts EPPK .xlsx | via traiter_fichier |
| `actualiser_frequentation.py` | Import fréquentation .csv | via traiter_fichier |
| `import_hebdomadaire.sh` | Import complet des 3 fichiers | `bash import_hebdomadaire.sh` |
| `lancer_enrichissement.py` | Enrichissement ISBN | `bash lancement_recherche_initiale.sh` |

### Format de progression dans les logs
- Catalogue : `X/Y notices traitées...` puis `X/Y exemplaires traités...`
- Statistiques : `X/Y traités...`
- Fréquentation : aucun compteur (rapide)

---

## APIS EXTERNES

| API | URL | Auth | Statut (testé 2026-07-22 via `test_connexions.py`) |
|-----|-----|------|--------|
| Turso (lecture) | — | `TURSO_AUTH_TOKEN` | ✓ Opérationnel — 44 288 notices, 44 677 exemplaires |
| Turso (écriture) | — | `TURSO_AUTH_TOKEN_ECRITURE` | ✗ Non testable — variable absente du `.env` local (à copier depuis les secrets Streamlit) |
| Open-Meteo (météo archive) | `archive-api.open-meteo.com` | Aucune | ✓ Opérationnel |
| BnF SRU | `catalogue.bnf.fr/api/SRU` | Aucune | ✓ Opérationnel |
| Open Library (couvertures) | `covers.openlibrary.org` | Aucune | ✓ Opérationnel |
| Geobib (couvertures) | `couverture.geobib.fr` | Aucune | ⚠️ La page d'accueil répond 200 (site relevé), mais l'échec documenté portait sur l'endpoint de récupération de couverture précis, non retesté — toujours considéré abandonné tant que l'endpoint réel n'est pas revalidé |
| Google Books | `googleapis.com/books/v1` | Clé API | ✗ `503 Service Unavailable` reproduit deux fois (test manuel + `test_connexions.py`) — à vérifier côté Google Cloud Console (quota / statut de la clé), ne pas conclure trop vite à une simple panne passagère |

### Couvertures (ordre de priorité)
1. Google Books : `https://books.google.com/books/content?vid=ISBN{ISBN}&printsec=frontcover&img=1&zoom=1`
2. Open Library : `https://covers.openlibrary.org/b/isbn/{ISBN}-M.jpg`

### Script de test (2026-07-22)
`test_connexions.py` (à la racine du dossier) teste les 6 connexions ci-dessus
en une commande, sans jamais afficher les jetons/clés :
```bash
cd ~/Desktop/inventaire_isbn
python3 test_connexions.py
```
Note : ce test doit être lancé depuis le Mac local — l'environnement Claude
(Cowork) est derrière un proxy qui n'autorise que certains domaines et ne
peut pas atteindre Turso/Google/BnF/Open-Meteo/Open Library directement.

---

## APPLICATION STREAMLIT

- **URL** : sur Streamlit Cloud (repo GitHub `ThomasLafargue/mediatheque-arcachon`)
- **Interface** : chat conversationnel + sidebar (KPIs, import)
- **Secrets requis** :

```toml
ANTHROPIC_API_KEY = "..."
TURSO_DATABASE_URL = "libsql://..."
TURSO_AUTH_TOKEN = "..."
TURSO_AUTH_TOKEN_ECRITURE = "..."
MOT_DE_PASSE = "..."
MOT_DE_PASSE_IMPORT = "..."
GOOGLE_BOOKS_API_KEY = "..."
```

---

## PROBLÈMES CONNUS

### Import depuis l'app Streamlit Cloud
`app_conversationnel.py` (fonction `lancer_import_background`, ~ligne 1677)
lance déjà l'import dans un **subprocess détaché** (pas dans la requête HTTP),
avec suivi de progression via un fichier d'état sur disque relu toutes les
3s. Ça règle en principe le problème de timeout réseau documenté ici.
**Restent deux risques non testés** :
- Streamlit Cloud peut mettre l'app en veille (inactivité) ou redéployer le
  conteneur pendant un import long → le subprocess et son fichier d'état
  disparaissent avec le conteneur.
- Le filesystem de Streamlit Cloud est éphémère : si le conteneur redémarre
  entre le dépôt du fichier et la fin du traitement, l'import est perdu.

**Piste "GitHub Actions" abandonnée dans sa forme initiale** : l'idée de
déclencher un import en poussant les 3 fichiers dans `imports/` du repo ne
fonctionne pas telle quelle — le fichier `.mrc` pèse ~112-113 Mo, au-dessus
de la limite dure de 100 Mo par fichier de GitHub (push refusé sans Git
LFS). À reconsidérer avec Git LFS, ou en gardant le flux actuel (dépôt via
l'app → subprocess local à l'app) et en testant sa robustesse face aux
redémarrages de conteneur.

### Connexion GitHub depuis Cowork (résolu le 2026-07-22)
Le connecteur GitHub de Cowork lisait le repo sans problème mais l'écriture
échouait (`Permission Denied: Resource not accessible by personal access
token`). Cause : le token utilisé n'avait pas le scope d'écriture.
**Corrigé** en générant un Personal Access Token classic avec le scope
`repo` (lecture + écriture complète), remplacé dans
`claude_desktop_config.json`, puis redémarrage de l'app. Écriture
confirmée fonctionnelle.

### Sécurité — `.gitignore` incomplet (corrigé le 2026-07-22)
`.env` et `.env.save` (jetons Turso, clé Google Books) n'étaient **pas**
dans `.gitignore`, alors que le repo est public. Vérifié : ils n'ont jamais
été commités (historique propre). Corrigé et poussé.

---

## WORKFLOW HEBDOMADAIRE

```bash
cd /Users/thomaslafargue/Desktop/inventaire_isbn

# 1. Déposer les 3 fichiers dans le dossier
# 2. Lancer l'import
bash import_hebdomadaire.sh

# 3. Reboot sur Streamlit Cloud
```

---

## CORRÉLATION MÉTÉO / FRÉQUENTATION (validée 2026-07-21)

Résultat réel sur données 2024-2026 :
- Jours de pluie (≥5mm) : **659 entrées/jour** (160 jours)
- Jours secs : **571 entrées/jour** (605 jours)
- **+15.4% de fréquentation les jours de pluie**

Source météo : Open-Meteo archive (gratuit, sans clé)
Source fréquentation : table `frequentation` (colonnes `date` et `nb_entrees`)

---

## SÉRIE / TOME MAL RENSEIGNÉS PAR DECALOG

`actualiser_catalogue.py` extrait serie/tome depuis les champs MARC
structurés de Decalog (lien 461, ou sous-champs $h/$i du champ 200). Quand
le catalogueur tape "One Piece tome 98" en texte libre dans le titre sans
utiliser ces champs, l'extraction échoue et serie/tome restent NULL.
`lancer_enrichissement.py` ne les corrige **jamais** (Decalog = source de
vérité sur ces champs, par design explicite dans le script).

`corriger_serie_tome_manquants.py` comble ce trou : détecte série + tome
depuis le titre par motif explicite ("tome", "T.", "vol."), UNIQUEMENT sur
les notices où serie ET tome sont NULL — ne touche jamais une notice où
Decalog a fourni une valeur. Dry-run par défaut, `--appliquer` pour écrire.
Nécessite `TURSO_AUTH_TOKEN_ECRITURE` dans `.env`.

### Résultat (2026-07-22) — appliqué en base
- **24 546** notices LIVRE sans serie/tome renseigné par Decalog (55% du
  fonds) — répartition dominée par Documentaire (5 806), Roman jeunesse
  (3 094), Album (2 730), BD (1 649), et 8 612 sans catégorie.
- **935 corrigées en base** (motif "tome"/"T."/"vol." explicite dans le
  titre) via `python3 corriger_serie_tome_manquants.py --appliquer`.
- **23 611** restent ambigus : en grande partie des ouvrages hors-série
  (documentaires, albums isolés) pour lesquels l'absence de serie/tome est
  normale, mais aussi des séries BD/Manga/Roman jeunesse numérotées sans le
  mot "tome" dans le titre (ex: "Naruto 12") — traitées par le moteur
  multi-sources plutôt que par une regex (voir ci-dessous).

### Correction d'architecture (2026-07-22) — le vrai bug était ailleurs

Le projet dispose déjà d'un moteur d'enrichissement multi-sources
(`moteur_recherche.py`, fonction `chercher_isbn()`) qui interroge BnF +
11 sites web pour **chaque ISBN importé**, précisément pour compléter ce
que Decalog laisse mal renseigné — y compris serie/tome. Ce moteur
calculait déjà correctement serie/tome, mais `lancer_enrichissement.py`
ne les incluait jamais dans la requête SQL d'écriture : la donnée était
calculée puis jetée. Corrigé en ajoutant
`serie = COALESCE(serie, ?), tome = COALESCE(tome, ?)` à l'UPDATE.

Deux changements supplémentaires actés avec Thomas :
- Le moteur à 11 sites tourne désormais **systématiquement** pour chaque
  ISBN (avant : court-circuité dès que BnF/Sudoc répondait avec un résumé,
  ce qui privait ces notices de serie/tome puisque BnF/Sudoc ne les
  fournissent pas). BnF/Sudoc restent interrogés en complément pour
  dewey/mots-clés/couverture.
- Backfill des 23 611 notices déjà enrichies avant ce fix :
  `lancement_backfill_serie_tome.sh` régénère la liste depuis la base et
  relance `lancer_enrichissement.py --forcer` en tâche de fond
  (nohup + caffeinate, même schéma que `lancement_recherche_initiale.sh`).

Le fichier `.mrc`/`.xlsx`/`.csv` hebdomadaire reste la source de vérité
pour titre/auteur/éditeur/dates/prêts/cote/code-barres — le moteur BnF +
sites web ne fait que **compléter** ce que Decalog laisse vide (jamais de
réécriture, toutes les écritures sont `COALESCE`).

### Traçabilité provenance — `champs_a_verifier_decalog`

Comme on ne réécrit jamais les notices Decalog, une valeur que notre
moteur déduit (ex: serie/tome) est correcte dans notre base mais reste
fausse/vide dans Decalog tant que personne ne la corrige manuellement
là-bas. La colonne `notice.champs_a_verifier_decalog` (ex: `'serie,tome'`)
trace précisément ces cas :
- Ajoutée par `migration_colonne_verification_decalog.py` (ALTER TABLE +
  recréation de `vue_inventaire` pour l'exposer, une VIEW ne pouvant pas
  gagner une colonne sans être recréée).
- Renseignée par `lancer_enrichissement.py` et `corriger_serie_tome_manquants.py`
  via `COALESCE(champs_a_verifier_decalog, ...)` — jamais écrasée, jamais
  posée quand la valeur vient réellement de Decalog.
- Les 935 notices déjà corrigées avant l'existence de cette colonne sont
  marquées rétroactivement par `marquer_provenance_retroactive.py`
  (rejoue la détection déterministe pour confirmer la provenance).
- Le chat (`app_conversationnel.py`) sait désormais répondre à "qu'est-ce
  qui est mal renseigné dans Decalog ?" en filtrant sur cette colonne et
  en formulant, par exemple : "Tu as bien le tome 5 de Mortelle Adèle,
  mais il est mal renseigné dans Decalog (serie=null, tome=null)."

---

## SOURCES DE VEILLE ACQUISITION

`sources_veille.py` agrège plusieurs sources pour les suggestions
d'acquisition : Ricochet-jeunes.org, BeDeTh-que.com, Booknode, et depuis
le 2026-07-22 **Croqulivre.fr** (association spécialisée jeunesse, 7000+
références) — via son API REST WordPress (`wp-json`), plus fiable qu'un
scraping HTML.
