# SIGB — Document de Vision
> Initié le 2026-07-22 — Thomas Lafargue / MAAT Arcachon
> Projet open source, IA-native, expérience utilisateur first

---

## VISION

Construire le premier SIGB conçu nativement avec l'IA, dans un esprit Apple :
chaque tâche est évidente, chaque écran est épuré, chaque décision est guidée
par les données réelles du fonds.

Un outil que n'importe qui dans une bibliothèque peut utiliser sans formation
technique — du bénévole à la directrice — et qui anticipe les besoins avant
qu'on les exprime.

Open source. Accessible à toutes les bibliothèques, des plus petites aux réseaux
intercommunaux.

---

## PROBLÈME À RÉSOUDRE

Les SIGB existants (Koha, PMB, Decalog, Evergreen) ont été conçus dans les années
2000 pour des informaticiens. Ils sont puissants mais :
- Interfaces datées et complexes, nécessitant des formations longues
- Aucune IA native — tout est manuel (catalogage, acquisitions, désherbage)
- Propriétaires ou mal maintenus
- Aucune vision "expérience lecteur"

Aucun ne répond à la question : *et si on recommençait depuis zéro en 2026 ?*

---

## PRINCIPES FONDATEURS

1. **IA invisible** — elle travaille en arrière-plan, jamais imposée
2. **3 clics maximum** — chaque tâche métier en 3 actions
3. **Mobile first** — fonctionne sur iPhone/iPad comme sur desktop
4. **Données réelles** — chaque suggestion basée sur les comportements réels
5. **Open source** — code public, communauté, pas de dépendance fournisseur
6. **Modulaire** — déployer un module, puis le suivant
7. **Multisite** — un réseau intercommunal = une instance, plusieurs sites

---

## MODULES

### 1. CATALOGUE (base existante à 80%)
Gestion des notices bibliographiques. Enrichissement automatique.

Fonctionnalités :
- Import UNIMARC/MARC21 depuis n'importe quel export Decalog/Koha
- Enrichissement automatique : BnF SRU, Sudoc, Google Books, OpenLibrary
- Base bibliographique intégrée : 15M+ notices françaises agrégées
- Couvertures, résumés, genres, séries, classement Dewey automatique
- Détection des doublons, des erreurs de catalogage, des séries incomplètes
- IA : suggestion de descripteurs, normalisation automatique des auteurs/éditeurs

### 2. OPAC PUBLIC (premier module à construire)
Interface de recherche pour les lecteurs.

Fonctionnalités :
- Recherche conversationnelle : "j'ai 8 ans et j'aime les dragons"
- Disponibilité en temps réel par site
- Réservation en ligne
- Recommandations personnalisées basées sur l'historique
- Multi-support : livres, DVD, jeux, périodiques
- Accessible RGAA (accessibilité)
- Interface responsive — parfaite sur mobile

### 3. CIRCULATION
Gestion des prêts, retours, réservations.

Fonctionnalités :
- Scan code-barres ou RFID
- Prêt en 1 geste sur tablette ou smartphone
- Gestion des retards, relances automatiques (email/SMS)
- Réservations et files d'attente
- Statistiques de circulation en temps réel
- Prêt entre sites du réseau

### 4. ACQUISITIONS (base existante à 70%)
Suggestions et commandes de nouveaux documents.

Fonctionnalités :
- Suggestions IA basées sur rotation du fonds, prix littéraires, météo, démographie
- Veille automatique : Ricochet-jeunes, BeDeTh-que, Booknode, Babelio
- Vérification d'absence dans le fonds avant suggestion
- Export commande ORB/Electre/fournisseur (CSV/EDI)
- ROI par acquisition : combien de prêts générés
- Alertes : doublons nécessaires, séries à compléter

### 5. DÉSHERBAGE
Aide à la décision pour retirer les documents obsolètes.

Fonctionnalités :
- Score IOUPI automatique (âge, état, usure, pertinence, inadéquation)
- Liste de désherbage priorisée avec justification IA
- Comparaison avec d'autres bibliothèques du réseau
- Historique des retraits

### 6. STATISTIQUES & RAPPORTS
Tableaux de bord pour la direction et les équipes.

Fonctionnalités :
- Fréquentation vs météo, saisonnalité
- Taux de rotation par genre, support, public
- Rapport annuel auto-généré (format Ministère de la Culture)
- Comparaison inter-sites du réseau
- Export Excel/PDF en un clic

### 7. ADMINISTRATION
Gestion des adhérents, paramétrage.

Fonctionnalités :
- Fichier adhérents (RGPD-compliant)
- Paramétrage des durées de prêt, tarifs, quotas
- Gestion des utilisateurs staff (rôles : admin, bibliothécaire, bénévole)
- Multi-sites avec droits différenciés

---

## STACK TECHNIQUE

### Backend
- **Python + FastAPI** — API REST performante, async, documentation auto
- **PostgreSQL** (Supabase) — base de données principale, temps réel, RLS
- **Turso/SQLite** — mode offline et déploiements légers
- **Redis** — cache, files d'attente, sessions

### Frontend
- **Next.js 14** (App Router) — SSR pour OPAC (SEO), RSC, performance
- **Tailwind CSS + shadcn/ui** — design system cohérent, accessible
- **Framer Motion** — animations fluides (esprit Apple)
- **PWA** — installable sur mobile comme une app native

### IA
- **Claude API** (Anthropic) — chat conversationnel, suggestions, enrichissement
- **Embeddings** — recherche sémantique dans le catalogue
- **BnF SRU / Sudoc / Google Books** — enrichissement bibliographique

### Infrastructure
- **Vercel** — déploiement frontend, CDN mondial
- **Railway ou Fly.io** — backend FastAPI
- **GitHub Actions** — CI/CD, imports hebdomadaires automatiques
- **Supabase** — PostgreSQL + Auth + Storage

### Base bibliographique intégrée
- Agrégation BnF (15M notices), Sudoc, Open Library
- Mise à jour hebdomadaire automatique
- API publique pour d'autres bibliothèques

---

## ROADMAP

### Phase 0 — Fondations (en cours, 3 mois)
Stabiliser l'existant MAAT Arcachon :
- ✅ Base Turso 44K notices enrichies
- ✅ Moteur d'acquisition IA
- ✅ Connexion GitHub directe
- ⬜ GitHub Actions pour import hebdomadaire
- ⬜ API Google Books stabilisée
- ⬜ Tests automatisés sur les requêtes SQL critiques

### Phase 1 — OPAC Public V1 (mois 1-4)
Premier module visible, premier contact avec les lecteurs :
- Interface de recherche responsive (mobile first)
- Recherche conversationnelle avec Claude
- Disponibilité en temps réel depuis la base Turso
- Déployé sur arcachon.maat.fr (ou similaire)

### Phase 2 — Circulation V1 (mois 3-8)
Le cœur du SIGB :
- Prêt/retour sur tablette (scan code-barres)
- Gestion des adhérents (RGPD)
- Réservations depuis l'OPAC
- Intégration avec la base notices existante

### Phase 3 — Multi-sites COBAS (mois 6-12)
Déploiement sur les 4 sites du réseau :
- Arcachon, La Teste, Gujan-Mestras, Le Teich
- Instance partagée, données séparées par site
- Statistiques consolidées réseau

### Phase 4 — Open Source V1 (mois 12-18)
Ouverture à d'autres bibliothèques :
- Documentation complète
- Script d'installation en 5 minutes
- Migration depuis Koha/PMB/Decalog
- Communauté GitHub

---

## CE QU'ON A DÉJÀ

| Composant | État | Réutilisable |
|-----------|------|-------------|
| Base 44K notices enrichies | ✅ Production | ✅ Direct |
| Moteur enrichissement BnF/Google | ✅ Production | ✅ Direct |
| Moteur acquisition IA | ✅ Production | ✅ Direct |
| Corrélation météo/fréquentation | ✅ Validé | ✅ Direct |
| Schéma SQL Turso | ✅ Production | ✅ Migration PostgreSQL |
| Chat conversationnel | ✅ Production | ✅ Base OPAC |
| Export ORB | ✅ Production | ✅ Direct |

---

## PREMIER MODULE À CONSTRUIRE : OPAC PUBLIC

Pourquoi commencer par l'OPAC :
- Visible immédiatement par les lecteurs → motivation
- Pas de gestion de données personnelles (RGPD simplifié)
- Techniquement faisable en 4 semaines pour une V1
- Différenciant immédiat : aucun SIGB n'a de recherche conversationnelle
- Base pour tout le reste : l'OPAC génère les données d'usage

**URL cible** : une page publique accessible depuis le site de la médiathèque
**Interface** : une barre de recherche + chat + résultats avec couvertures
**Stack** : Next.js + Tailwind + Claude API + Turso (lecture seule)

---

## NOM DU PROJET

À définir. Pistes :
- **Biblio** — simple, universel
- **Lumen** — la lumière, l'accès au savoir
- **Folio** — la page, le livre
- **Stacks** — les rayonnages (bibliothèque anglais)
- **Mnemosyne** — déesse grecque de la mémoire

---

*Ce document est vivant. Il évolue à chaque session de travail.*
