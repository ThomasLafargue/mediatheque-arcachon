# HAL — Hub d'Accès à la Lecture
### Système Intégré de Gestion de Bibliothèque — Document de Vision
> Initié le 2026-07-22 — Thomas Lafargue / MAAT Arcachon
> *"I'm sorry Dave, I can't do that."* — mais HAL, lui, fait tout ce qu'on lui demande.

---

## VISION

HAL est le premier SIGB conçu nativement avec l'IA, dans un esprit Apple :
chaque tâche est évidente, chaque écran est épuré, chaque décision est guidée
par les données réelles du fonds.

Un outil que n'importe qui dans une bibliothèque peut utiliser sans formation
technique — du bénévole à la directrice — et qui anticipe les besoins avant
qu'on les exprime.

Open source. Accessible à toutes les bibliothèques, des plus petites aux réseaux
intercommunaux.

**Déploiement de référence** : Médiathèque d'Arcachon (MAAT) — réseau COBAS,
4 sites, 44 000+ documents.

---

## IDENTITÉ

**Nom** : HAL
**Sous-titre** : Hub d'Accès à la Lecture
**Référence** : HAL 9000, 2001 : L'Odyssée de l'espace (Kubrick, 1968)
**Esprit** : omniscient, calme, précis — au service des bibliothécaires
**Logo** : œil rouge HAL 9000, stylisé minimaliste
**Couleurs** : noir profond, blanc, rouge HAL (#FF3B30)
**Typographie** : Inter (open source, qualité Apple)

---

## ANALYSE DU MARCHÉ (juillet 2026)

### Le marché en chiffres
- **15 500 bibliothèques publiques** en France (Ministère de la Culture, 2024)
- **94 millions d'entrées** déclarées en 2024
- **37% des Français** fréquentent une bibliothèque — en hausse (+7 pts vs 2023)
- Marché des logiciels SIGB **en stagnation** selon Archimag (mai 2026)

### Les concurrents

| Solution | Type | Part marché FR | Forces | Faiblesses |
|----------|------|---------------|--------|-----------|
| **Decalog** | Propriétaire | ~30% lecture publique | 30 ans d'expérience, support FR | Interface 2000s, cher, fermé |
| **Koha** | Open source | Fort en universitaire | Mondial, gratuit, MARC complet | Installation complexe, UI datée |
| **PMB** | Open source | ~20% lecture publique | Francophone, modulaire | Maintenance aléatoire |
| **BibLibre/Pikoloco** | Service Koha | Petites biblio | Clé en main, abordable | Dépendance prestataire |
| **Ex Libris Alma** | SaaS premium | Universités | Très complet | Très cher, complexe |

### La faille du marché

Aucune solution ne combine :
1. UX moderne pensée pour les agents (pas pour les informaticiens)
2. IA native (catalogage, acquisitions, désherbage automatisés)
3. Open source et installation simple
4. Recherche conversationnelle pour les lecteurs
5. Rapport qualité/prix adapté aux petites et moyennes bibliothèques

**C'est exactement ce que HAL adresse.**

### Taille du marché adressable

- France : 15 500 bibliothèques publiques
- Francophonie : +30 000 établissements (Belgique, Suisse, Canada, Afrique)
- Prix cible : 1 500 à 8 000 €/an selon la taille (vs 5 000 à 25 000 € pour Decalog)
- Potentiel : 10% du marché FR = 1 550 bibliothèques × 3 000 €/an = **4,6 M€/an**

### Modèle économique (open source / freemium)

- **Gratuit** : code source, auto-hébergement, communauté
- **HAL Cloud** : hébergement géré, mises à jour auto — à partir de 99 €/mois
- **HAL Pro** : support prioritaire, onboarding, formation — à partir de 199 €/mois
- **HAL Réseau** : déploiement multi-sites (intercommunal) — sur devis

---

## PROBLÈME À RÉSOUDRE

Les SIGB existants ont été conçus dans les années 2000 pour des informaticiens.
Ils sont puissants mais :
- Interfaces datées, formations longues, résistance au changement
- Aucune IA native — tout est saisi manuellement
- Propriétaires (Decalog) ou mal maintenus (PMB)
- Aucune vision "expérience lecteur"

La question que personne ne s'est posée : *et si on recommençait depuis zéro en 2026 ?*

---

## PRINCIPES FONDATEURS

1. **IA invisible** — elle travaille en arrière-plan, jamais imposée
2. **3 clics maximum** — chaque tâche métier en 3 actions
3. **Mobile first** — parfait sur iPhone/iPad comme sur desktop
4. **Données réelles** — chaque suggestion basée sur les comportements réels
5. **Open source** — code public, communauté, pas de dépendance fournisseur
6. **Modulaire** — déployer un module, puis le suivant
7. **Multisite** — un réseau intercommunal = une instance, plusieurs sites

---

## MODULES

### 1. CATALOGUE (base existante à 80%)
- Import UNIMARC/MARC21 depuis n'importe quel export Decalog/Koha
- Enrichissement automatique : BnF SRU, Sudoc, Google Books, OpenLibrary
- Base bibliographique intégrée : 15M+ notices françaises agrégées
- Couvertures, résumés, genres, séries, Dewey automatique
- Détection doublons, erreurs de catalogage, séries incomplètes
- IA : normalisation auteurs/éditeurs, suggestion de descripteurs

### 2. OPAC PUBLIC — HAL Search ⭐ PREMIER MODULE
Interface de recherche pour les lecteurs. Double rôle :
- **Production** : catalogue en ligne de MAAT Arcachon dès la V1
- **Vitrine** : démo publique de HAL pour toutes les bibliothèques

Fonctionnalités V1 :
- Recherche par mot-clé + filtres (genre, public, support, disponibilité)
- Recherche conversationnelle : "j'ai 8 ans et j'aime les dragons"
- Disponibilité en temps réel par site
- Couvertures + résumé + infos pratiques
- 100% responsive — parfait sur mobile

### 3. CIRCULATION — HAL Desk
- Scan code-barres ou RFID sur tablette/smartphone
- Prêt en 1 geste
- Gestion des retards, relances automatiques
- Réservations depuis HAL Search
- Prêt entre sites du réseau

### 4. ACQUISITIONS — HAL Buy (base existante à 70%)
- Suggestions IA : rotation, prix littéraires, météo, démographie
- Veille : Ricochet-jeunes, BeDeTh-que, Booknode, Babelio
- Vérification d'absence avant suggestion
- Export commande ORB/Electre (CSV/EDI)
- ROI par acquisition

### 5. DÉSHERBAGE — HAL Weed
- Score IOUPI automatique
- Liste priorisée avec justification IA
- Comparaison réseau

### 6. STATISTIQUES — HAL Stats
- Fréquentation vs météo, saisonnalité
- Rapport annuel format Ministère de la Culture
- Export Excel/PDF en 1 clic

### 7. ADMINISTRATION — HAL Admin
- Adhérents (RGPD-compliant)
- Paramétrage durées prêt, tarifs, quotas
- Rôles : admin, bibliothécaire, bénévole

---

## STACK TECHNIQUE

### Backend
- **Python + FastAPI** — API REST, async, doc auto (Thomas maîtrise Python)
- **PostgreSQL** (Supabase) — base principale, temps réel, auth intégrée
- **Turso/libsql** — mode offline et migration depuis l'existant

### Frontend
- **Next.js 14** (App Router) — SSR pour SEO, performance
- **Tailwind CSS + shadcn/ui** — design system accessible
- **Framer Motion** — animations fluides (esprit Apple)
- **PWA** — installable sur mobile

### IA
- **Claude API** — chat, suggestions, enrichissement
- **Embeddings** — recherche sémantique
- **BnF SRU / Sudoc / Google Books** — données bibliographiques

### Infrastructure
- **Vercel** — frontend, CDN mondial, gratuit pour open source
- **Railway ou Fly.io** — backend FastAPI
- **GitHub Actions** — CI/CD, imports automatiques
- **Supabase** — PostgreSQL + Auth + Storage (plan gratuit généreux)

---

## ROADMAP

### Phase 0 — Fondations MAAT ✅ En cours
- ✅ Base Turso 44K notices enrichies
- ✅ Moteur d'acquisition IA
- ✅ Connexion GitHub directe depuis Claude
- ✅ Workflow GitHub Actions prêt (à activer)
- ⬜ Secrets GitHub à configurer (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN_ECRITURE)
- ⬜ Dossier `imports/` à créer dans le repo

### Phase 1 — HAL Search V1 (mois 1-3)
- Interface recherche responsive (mobile first)
- Recherche conversationnelle Claude
- Disponibilité temps réel Turso
- URL : hal-search.vercel.app (démo) + intégration MAAT

### Phase 2 — HAL Desk V1 (mois 3-8)
- Prêt/retour tablette
- Adhérents RGPD
- Réservations depuis HAL Search

### Phase 3 — COBAS (mois 6-12)
- 4 sites : Arcachon, La Teste, Gujan-Mestras, Le Teich
- Instance partagée, données séparées par site

### Phase 4 — Open Source V1 (mois 12-18)
- Documentation + installation 5 minutes
- Migration Koha/PMB/Decalog
- Conférence BBF + GitHub communauté

---

## CE QU'ON A DÉJÀ

| Composant | État | Module HAL |
|-----------|------|-----------|
| Base 44K notices enrichies | ✅ Production | Catalogue |
| Enrichissement BnF/Google | ✅ Production | Catalogue |
| Moteur acquisition IA | ✅ Production | HAL Buy |
| Corrélation météo/fréquentation | ✅ Validé (+15.4% pluie) | HAL Stats |
| Chat conversationnel Claude | ✅ Production | HAL Search |
| Export ORB | ✅ Production | HAL Buy |
| GitHub direct depuis Claude | ✅ Opérationnel | Infra |
| Workflow GitHub Actions | ✅ Prêt | Infra |

---

## DIFFÉRENCIANTS HAL vs CONCURRENTS

| Fonctionnalité | HAL | Decalog | Koha | PMB |
|----------------|-----|---------|------|-----|
| Recherche conversationnelle | ✅ | ❌ | ❌ | ❌ |
| IA native | ✅ | ❌ | ❌ | ❌ |
| Installation < 10 min | ✅ | ❌ | ❌ | ⚠️ |
| Interface mobile first | ✅ | ⚠️ | ⚠️ | ❌ |
| Open source | ✅ | ❌ | ✅ | ✅ |
| Suggestions acquisition IA | ✅ | ❌ | ❌ | ❌ |
| Corrélation météo/données | ✅ | ❌ | ❌ | ❌ |
| Rapport annuel auto | ✅ | ⚠️ | ⚠️ | ⚠️ |

---

## POUR ACTIVER LE WORKFLOW D'IMPORT (GitHub Actions)

1. github.com → repo → **Settings** → **Secrets and variables** → **Actions**
2. Ajouter :
   - `TURSO_DATABASE_URL` = `libsql://mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io`
   - `TURSO_AUTH_TOKEN_ECRITURE` = (token écriture dans .env)
3. Renommer `import_hebdomadaire_workflow.yml` → `.github/workflows/import_hebdomadaire.yml`
4. Créer un dossier `imports/` dans le repo
5. Dès qu'un fichier `.mrc`, `.xlsx` ou `.csv` est pushé dans `imports/` → import automatique

---

*Ce document est vivant. Dernière mise à jour : 2026-07-22*
