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
| Turso (écriture) | — | `TURSO_AUTH_TOKEN_ECRITURE` | ✓ Ajouté au `.env` local, testé fonctionnel (935 notices corrigées avec) |
| Open-Meteo (météo archive) | `archive-api.open-meteo.com` | Aucune | ✓ Opérationnel |
| BnF SRU | `catalogue.bnf.fr/api/SRU` | Aucune | ✓ Opérationnel |
| Open Library (couvertures) | `covers.openlibrary.org` | Aucune | ✓ Opérationnel |
| Geobib (couvertures) | `couverture.geobib.fr` | Aucune | ✗ Retiré du pipeline le 2026-07-22 (instabilité) |
| Google Books | `googleapis.com/books/v1` | Clé API | ✗ Retiré du pipeline le 2026-07-22 (503 reproductibles) |

### Couvertures (ordre de priorité)
1. Open Library : `https://covers.openlibrary.org/b/isbn/{ISBN}-M.jpg`

Google Books et Geobib retirés le 2026-07-22 (voir section "Problèmes connus").
Fonctions conservées dans le code (`chercher_google_books()` dans
`sources_api.py` et `moteur_recherche.py`) mais plus appelées.

### Script de test (2026-07-22)
`test_connexions.py` (à la racine du dossier) teste les connexions ci-dessus
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
GOOGLE_BOOKS_API_KEY = "..."  -- plus utilisée depuis le 2026-07-22, peut être retirée
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

### Google Books + Geobib retirés du pipeline (2026-07-22)
Google Books (API `googleapis.com/books/v1`, avec ou sans clé) a renvoyé des
`503 Service Unavailable` de façon reproductible. Geobib était déjà
documenté comme abandonné (erreur 500). Les deux ont été retirés :
- `sources_api.py` : `enrichir_par_api()` n'appelle plus `chercher_google_books()` ;
  la couverture BnF utilise Open Library au lieu de Geobib.
- `moteur_recherche.py` : "Google Books" retiré de la liste `SOURCES` (12 → 11 sources).
- `app_conversationnel.py` : instructions de couverture simplifiées sur Open Library seule.

Les fonctions restent dans le code, juste plus appelées — faciles à
réactiver si ces services redeviennent fiables.

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
  mot "tome" dans le titre (ex: "Naruto 12") — non traitées par design
  (trop ambigu pour une regex). Une passe IA ciblée sur ces cas serait une
  suite possible, à faire avec prudence (risque de faux positifs plus
  élevé qu'avec un motif explicite).

---

## SOURCES DE VEILLE ACQUISITION

`sources_veille.py` agrège plusieurs sources pour les suggestions
d'acquisition : Ricochet-jeunes.org, BeDeTh-que.com, Booknode, et depuis
le 2026-07-22 **Croqulivre.fr** (association spécialisée jeunesse, 7000+
références) — via son API REST WordPress (`wp-json`), plus fiable qu'un
scraping HTML.
