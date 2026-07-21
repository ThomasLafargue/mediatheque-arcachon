# ÉTAT DU PROJET — MAAT Arcachon
> Fichier de continuité — à coller en début de nouvelle conversation Claude si besoin.
> Mis à jour le 2026-07-21.

---

## QUI

Thomas Lafargue, responsable section jeunesse, Médiathèque d'Arcachon (MAAT).
Réseau COBAS — 4 sites : Arcachon, La Teste, Gujan-Mestras, Le Teich.
Dépôt GitHub : `ThomasLafargue/mediatheque-arcachon`
Dossier local : `/Users/thomaslafargue/Desktop/inventaire_isbn/`

---

## ARCHITECTURE TECHNIQUE

| Composant | Détail |
|-----------|--------|
| Base | Turso cloud SQLite (`libsql://mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io`) |
| App | `app_conversationnel.py` sur Streamlit Cloud |
| Auth | 2 mots de passe (chat + import) dans secrets Streamlit |
| Import | Scripts locaux Mac → Turso via `bash import_hebdomadaire.sh` |

### Secrets Streamlit requis
```
ANTHROPIC_API_KEY
TURSO_AUTH_TOKEN          (lecture)
TURSO_AUTH_TOKEN_ECRITURE (écriture)
MOT_DE_PASSE              (accès chat)
MOT_DE_PASSE_IMPORT       (import fichiers)
GOOGLE_BOOKS_API_KEY      (CLE_SUPPRIMEE)
```

---

## ÉTAT DE LA BASE (2026-07-21)

- **44 288 notices** | **44 677 exemplaires** | **39 427 enrichies (89%)**
- Fréquentation : 1 921 jours, 2020-01-30 → 2026-07-16
- Dernière MAJ Decalog : 2026-07-19

### Schéma réel — TABLE `notice`
```
identifiant, type_document, titre, serie, tome, collection,
createurs,           ← PAS "auteur"
createurs_secondaires, traducteur, editeur,
date_publication,    ← PAS "annee" — format TEXT "YYYY-MM-DD" ou "YYYY"
categorie, genre, public_vise, age_recommande, pegi,
score_confiance, date_enrichissement, nb_sources_consultees,
resume, image_url, dewey, dewey_libelle, mots_cles,
nb_prets_total,      ← PAS "nb_prets"
nb_prets_annee_courante, nb_prets_n1, nb_prets_n2, nb_prets_n3,
nb_prets_fonctionnels, date_dernier_pret, date_maj_prets
```

### Schéma réel — TABLE `exemplaire`
```
id, identifiant, cote, code_barre_exemplaire, date_acquisition,
statut, site, public_vise, support, prix,
nb_prets_total, annee_dernier_pret, date_maj
```

### ⚠ Curseur Turso
Le curseur Turso (`_CurseurTurso`) n'a **pas** d'attribut `.description`.
Toujours utiliser `fetchall()` avec accès par index ou parseur de colonnes depuis SQL.
Ne jamais écrire `cur.description`.

---

## FICHIERS CLÉS DU REPO

| Fichier | Rôle |
|---------|------|
| `app_conversationnel.py` | App principale — 3 onglets Chat/Dashboard/Acquisitions |
| `analyser_acquisition.py` | Signaux internes SQL + météo Open-Meteo + profil Arcachon INSEE |
| `sources_veille.py` | Ricochet, BeDeTh-que, Booknode, Babelio |
| `sources_api.py` | BnF SRU, Google Books, Sudoc |
| `db.py` | Connexion Turso |
| `traiter_fichier.py` | Import .mrc / .xlsx EPPK / .csv fréquentation |
| `lancer_enrichissement.py` | Enrichissement ISBN (BnF + Google Books + 12 sources web) |
| `actualiser_catalogue.py` | Mapping COBAS → champs notice |
| `actualiser_statistiques.py` | Import prêts EPPK |
| `actualiser_frequentation.py` | Import CSV fréquentation |
| `import_hebdomadaire.sh` | Script import complet hebdomadaire |
| `lancement_recherche_initiale.sh` | Enrichissement nouvelles notices |

---

## CE QUI A ÉTÉ FAIT LE 2026-07-21

### app_conversationnel.py — refonte majeure
- **3 onglets** : 💬 Chat / 📊 Tableau de bord / 📚 Acquisitions
- **Tableau de bord** : KPIs, fréquentation 18 mois (bar chart), rotation genres, top 25 titres, alertes doublons/séries
- **Onglet Acquisitions** : liste suggestions, export ORB-ready (CSV UTF-8 BOM), export Excel, ROI 2023+, profil démographique
- **Tool `lancer_analyse_acquisition()`** : analyse interne + météo + démographie
- **Prompt enrichi** : 30+ prix littéraires (jeunesse + adultes + BD/manga), éditeurs par segment, sources web, calendrier éditorial, couverture adultes complète, contexte MAAT

### analyser_acquisition.py — nouveau module
- 8 requêtes SQL signaux internes (rotation genres, doublons, séries incomplètes, auteurs manquants, ancienneté fonds)
- Corrélation météo/fréquentation via Open-Meteo (gratuit, sans clé)
- Profil démographique Arcachon — données réelles INSEE RP2022 (paru 05/05/2026)

### sources_veille.py — module veille
- Ricochet-jeunes.org (RSS + scraping)
- BeDeTh-que.com (nouveautés BD/Manga)
- Booknode (sorties, meilleures ventes)
- Babelio (notes sur notre fonds)

### Données INSEE RP2022 vérifiées pour Arcachon (33009)
- Population 2022 : **10 895** résidents permanents
- Seniors 60+ : **60.5%** (30.5% de 60-74 ans + 30.0% de 75 ans+)
- Retraités : **56.8%** de la population 15 ans+
- Résidences secondaires : **62.2%** du parc immobilier
- Revenu médian 2023 : **31 420€/an**
- Source : https://www.insee.fr/fr/statistiques/2011101?geo=COM-33009

---

## COMMITS RÉCENTS

```
5c4809c  Ajout sources_veille.py : Ricochet, BeDeTh-que, Booknode, Babelio
f4aff15  Fix cursor.description incompatible Turso — parseur colonnes depuis SQL
7469d1d  Fix colonnes SQL : createurs, nb_prets_total, date_publication (schéma réel)
fe7d318  Suppression COBAS portail du prompt - fonctionnalité non opérationnelle
ec984b0  Import app : état persisté sur disque, résistant aux resets de session
77abf10  Import app : subprocess détaché avec start_new_session=True
```

---

## WORKFLOW HEBDOMADAIRE

```bash
# Déposer les 3 fichiers dans inventaire_isbn, puis :
bash import_hebdomadaire.sh
# Puis Reboot sur Streamlit Cloud
```

---

## PENDING — À FAIRE

### Priorité haute
- [ ] Tester les 3 onglets après reboot Streamlit Cloud
- [ ] Envoyer mail Decalog : c.guilloni@decalog.net
- [ ] Envoyer mail ORB : cgalliot@decitre.fr

### Technique
- [ ] Déboguer import depuis l'app (latence Streamlit Cloud → Turso trop élevée pour 44K updates)
- [ ] Restreindre clé Google Books API sur Google Cloud Console
- [ ] Recherche par titre+auteur pour les ~6 964 CB: (notices sans EAN)

### Plus tard
- [ ] Mosaïque kiosque : intégrer disponibilité (données base hebdo)
- [ ] Intégrer endpoints JSON COBAS portail (disponibilité temps réel)
- [ ] Version publique V3 (après APIs connectées)

---

## CONTEXTE MAAT — NE PAS OUBLIER

- Arcachon est le **pôle économique du sud Bassin** (zone de chalandise ~68 000 hab. COBAS)
- Les **grands-parents retraités (56.8%)** emmènent leurs petits-enfants au MAAT les mercredis, week-ends et vacances → demande jeunesse bien plus forte que les 720 enfants résidents ne le suggèrent
- Les **résidents secondaires** (62.2% du parc) sont des Bordelais/Parisiens CSP+ qui reviennent 4-8 fois/an et sont des habitués réguliers avec une carte
- **Signal acquisitions = nos données réelles (prêts, fréquentation) > démographie INSEE**
- La démographie est un contexte de fond, pas un critère de décision

---

## POUR REPRENDRE UNE SESSION

Coller ce fichier en début de conversation avec :
> "Je travaille sur l'outil de gestion du MAAT Arcachon. Voici l'état du projet : [contenu de ce fichier]"
