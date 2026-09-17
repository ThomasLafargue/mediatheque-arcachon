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
**Esprit** : omniscient, calme, précis — mais cette fois au service des bibliothécaires
**Logo** : œil rouge HAL 9000, stylisé minimaliste
**Couleurs** : noir profond, blanc, rouge HAL (#FF3B30)
**Typographie** : SF Pro (Apple) ou Inter

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
3. **Mobile first** — parfait sur iPhone/iPad comme sur desktop
4. **Données réelles** — chaque suggestion basée sur les comportements réels
5. **Open source** — code public, communauté, pas de dépendance fournisseur
6. **Modulaire** — déployer un module, puis le suivant
7. **Multisite** — un réseau intercommunal = une instance, plusieurs sites

---

## MODULES

### 1. CATALOGUE (base existante à 80%)
Gestion des notices bibliographiques. Enrichissement automatique.

- Import UNIMARC/MARC21 depuis n'importe quel export Decalog/Koha
- Enrichissement automatique : BnF SRU, Sudoc, Google Books, OpenLibrary
- Base bibliographique intégrée : 15M+ notices françaises agrégées
- Couvertures, résumés, genres, séries, classement Dewey automatique
- Détection des doublons, erreurs de catalogage, séries incomplètes
- IA : suggestion de descripteurs, normalisation auteurs/éditeurs

### 2. OPAC PUBLIC — HAL Search (premier module à construire)
Interface de recherche pour les lecteurs. Double rôle :
- **Production** : catalogue en ligne de MAAT Arcachon
- **Vitrine** : démo publique de HAL pour toutes les bibliothèques

Fonctionnalités :
- Recherche conversationnelle : "j'ai 8 ans et j'aime les dragons"
- Disponibilité en temps réel par site
- Réservation en ligne
- Recommandations personnalisées
- Multi-support : livres, DVD, jeux, périodiques
- Accessible RGAA
- Responsive — parfait sur mobile

### 3. CIRCULATION — HAL Desk
Prêts, retours, réservations.

- Scan code-barres ou RFID
- Prêt en 1 geste sur tablette ou smartphone
- Gestion des retards, relances automatiques (email/SMS)
- Réservations et files d'attente
- Statistiques de circulation en temps réel
- Prêt entre sites du réseau

### 4. ACQUISITIONS — HAL Buy (base existante à 70%)
Suggestions et commandes de nouveaux documents.

- Suggestions IA basées sur rotation, prix littéraires, météo, démographie
- Veille automatique : Ricochet-jeunes, BeDeTh-que, Booknode, Babelio
- Vérification d'absence dans le fonds avant suggestion
- Export commande ORB/Electre/fournisseur (CSV/EDI)
- ROI par acquisition : combien de prêts générés

### 5. DÉSHERBAGE — HAL Weed
Aide à la décision pour retirer les documents obsolètes.

- Score IOUPI automatique
- Liste priorisée avec justification IA
- Comparaison avec d'autres bibliothèques du réseau
- Historique des retraits

### 6. STATISTIQUES — HAL Stats
Tableaux de bord pour direction et équipes.

- Fréquentation vs météo, saisonnalité
- Taux de rotation par genre, support, public
- Rapport annuel auto-généré (format Ministère de la Culture)
- Comparaison inter-sites du réseau
- Export Excel/PDF en un clic

### 7. ADMINISTRATION — HAL Admin
Gestion des adhérents, paramétrage.

- Fichier adhérents (RGPD-compliant)
- Paramétrage durées de prêt, tarifs, quotas
- Gestion des utilisateurs staff (admin, bibliothécaire, bénévole)
- Multi-sites avec droits différenciés

---

## STACK TECHNIQUE

### Backend
- **Python + FastAPI** — API REST, async, documentation auto
- **PostgreSQL** (Supabase) — base principale, temps réel, auth intégrée
- **Redis** — cache, sessions, files d'attente

### Frontend
- **Next.js 14** (App Router) — SSR pour OPAC (SEO), performance
- **Tailwind CSS + shadcn/ui** — design system cohérent, accessible
- **Framer Motion** — animations fluides
- **PWA** — installable sur mobile comme app native

### IA
- **Claude API** (Anthropic) — chat, suggestions, enrichissement
- **Embeddings** — recherche sémantique dans le catalogue
- **BnF SRU / Sudoc / Google Books** — données bibliographiques

### Infrastructure
- **Vercel** — frontend, CDN mondial
- **Railway ou Fly.io** — backend FastAPI
- **GitHub Actions** — CI/CD, imports hebdomadaires automatiques
- **Supabase** — PostgreSQL + Auth + Storage

### Base bibliographique intégrée
- Agrégation BnF (15M notices), Sudoc, Open Library
- Mise à jour hebdomadaire automatique
- API publique réutilisable par d'autres bibliothèques

---

## ROADMAP

### Phase 0 — Fondations MAAT (en cours)
Stabiliser l'existant Arcachon :
- ✅ Base Turso 44K notices enrichies
- ✅ Moteur d'acquisition IA
- ✅ Connexion GitHub directe depuis Claude
- ⬜ GitHub Actions import hebdomadaire
- ⬜ Tests automatisés requêtes SQL critiques

### Phase 1 — HAL Search V1 (mois 1-4)
OPAC public pour MAAT + vitrine HAL :
- Interface recherche responsive (mobile first)
- Recherche conversationnelle avec Claude
- Disponibilité temps réel depuis base Turso
- URL publique : hal.maat-arcachon.fr (ou similaire)
- Page vitrine : hal.library (domaine à réserver)

### Phase 2 — HAL Desk V1 (mois 3-8)
Circulation :
- Prêt/retour sur tablette (scan code-barres)
- Gestion des adhérents (RGPD)
- Réservations depuis HAL Search
- Intégration avec la base notices existante

### Phase 3 — Multi-sites COBAS (mois 6-12)
Déploiement sur 4 sites du réseau COBAS :
- Arcachon, La Teste, Gujan-Mestras, Le Teich
- Instance partagée, données séparées par site
- Statistiques consolidées réseau

### Phase 4 — HAL Open Source V1 (mois 12-18)
Ouverture à toutes les bibliothèques :
- Documentation complète
- Script d'installation en 5 minutes
- Migration depuis Koha/PMB/Decalog
- Site communautaire GitHub
- Conférence BBF (Bibliothèques Bibliothécaires Francophones)

---

## CE QU'ON A DÉJÀ

| Composant | État | Module HAL |
|-----------|------|-----------|
| Base 44K notices enrichies | ✅ Production | Catalogue |
| Moteur enrichissement BnF/Google | ✅ Production | Catalogue |
| Moteur acquisition IA | ✅ Production | HAL Buy |
| Corrélation météo/fréquentation | ✅ Validé | HAL Stats |
| Chat conversationnel Claude | ✅ Production | HAL Search |
| Export ORB | ✅ Production | HAL Buy |
| Connexion GitHub depuis Claude | ✅ Opérationnel | Infra |

---

## DIFFÉRENCIANTS

Ce qu'aucun SIGB existant ne propose :

1. **Recherche conversationnelle** — "je cherche un roman pour ma fille de 10 ans qui adore les chevaux"
2. **Suggestions d'acquisition IA** — basées sur les vrais prêts, la météo, la démographie
3. **Installation en 5 minutes** — un `docker compose up` suffit
4. **Interface 2026** — pas une interface de 2003 avec un thème moderne
5. **Open source natif IA** — pas un plugin, l'IA est dans l'architecture

---

*Ce document est vivant. Il évolue à chaque session de travail.*
*Dernière mise à jour : 2026-07-22*
