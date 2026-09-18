# HAL — Spécifications Techniques Complètes
> Capture des exigences fonctionnelles détaillées — 2026-07-22

---

## HARDWARE CIBLE

### Tablettes (postes agents)
- Tablettes Android ou iPad avec **lecteur RFID intégré** (NFC/HF 13.56 MHz ISO 15693)
- Clavier Bluetooth pour les tâches administratives (catalogage, commandes)
- Recommandations : Samsung Galaxy Tab S9, Zebra ET60, Honeywell RT10A
- Interface HAL : PWA installable, fonctionne en mode offline

### Scannettes sans fil
- Code-barres 1D/2D sans fil (Bluetooth ou USB)
- Utilisées pour : réception de commandes, prêts/retours, inventaire
- Compatible avec n'importe quelle scannette standard (Zebra, Honeywell, Socket)

### RFID — Nedap
- Standard : HF 13.56 MHz ISO 15693 (bibliothèques)
- Encodage via : tablette NFC intégrée OU encodeur USB Nedap (Web Serial API)
- Tags : Tectus (Nedap) ou compatibles ISO 15693
- Données encodées : identifiant document + site + sécurité antivol (AFI)

---

## SCHÉMA DES NOTICES — CHAMPS OBLIGATOIRES

Tout document dans HAL doit avoir ces champs. L'IA complète automatiquement
depuis BnF/Sudoc/Google Books au moment de la commande.

### Identification
```
identifiant      — EAN13/ISBN (obligatoire) ou CB: si pas d'EAN
type_document    — LIVRE | BD | MANGA | DVD | JEU | PERIODIQUE | CD
```

### Description bibliographique
```
titre            — titre principal (obligatoire)
sous_titre       — sous-titre
serie            — nom de la série
tome             — numéro dans la série (TEXT pour gérer "HS", "0", etc.)
collection       — collection éditeur
createurs        — auteur(s) principal/e(s) (obligatoire)
createurs_secondaires — illustrateur, traducteur...
editeur          — éditeur (obligatoire)
date_publication — YYYY ou YYYY-MM-DD (obligatoire)
pays_edition     — FR, BE, CH...
langue           — fra, eng...
description_physique — "245 p. ; 24 cm" ou "1 DVD (90 min)"
```

### Classification
```
dewey            — indice Dewey (obligatoire pour documentaires)
dewey_libelle    — libellé associé ("Informatique", "Histoire de France"...)
genre            — Roman | Policier | SF | Fantasy | BD | Manga | Album | Documentaire...
public_vise      — Bébé (0-3) | Enfant (3-6) | Jeune (6-9) | Ado (9-15) | Adulte
age_recommande   — "8 ans et +" (TEXT)
pegi             — pour les jeux : 3 | 7 | 12 | 16 | 18
```

### Enrichissement IA
```
resume           — résumé (auto BnF/Google ou saisi)
image_url        — couverture (auto Google Books)
mots_cles        — tags thématiques
score_confiance  — 0 à 1 : qualité de l'enrichissement automatique
date_enrichissement — date du dernier enrichissement
nb_sources_consultees — combien de sources ont répondu
```

### Statistiques de prêt (sync Decalog/HAL)
```
nb_prets_total
nb_prets_annee_courante
nb_prets_n1, n2, n3
date_dernier_pret
```

---

## RÈGLES DE COTE — CONFIGURABLES PAR MÉDIATHÈQUE

La cote est générée automatiquement selon des règles configurables.
Chaque médiathèque peut définir ses propres règles.

### Format général
```
[TYPE]/[AUTEUR 3 lettres]/[TOME ou TITRE 3 lettres]
```

### Exemples MAAT Arcachon
```
Roman jeunesse     → MJ/HAR        (Harry Potter)
Album 0-3 ans      → ALB/BEA       (Boucle d'Or)
BD jeunesse        → BDJ/AST/1     (Astérix T.1)
Manga              → MAN/ONE/1     (One Piece T.1)
Roman adulte       → ROM/BEA       (Beauvoir)
BD adulte          → BD/MOE/2      (Moebius)
Documentaire       → DOC/590       (Dewey pour animaux)
DVD                → DVD/AVA       (Avatar)
Jeu                → JEU/CAT       (Catane)
```

### Interface de configuration
- Chaque type de document → règle de cote (modèle avec variables)
- Variables disponibles : {TYPE}, {AUTEUR_3}, {TITRE_3}, {DEWEY}, {TOME}, {SERIE_3}
- Prévisualisation en temps réel lors du paramétrage

---

## MODULE ACQUISITIONS — WORKFLOW COMPLET

### Vue d'ensemble
```
Suggestion → Panier → Validation budget → Bon de commande → 
Envoi fournisseur → Réception → Création exemplaire → OPAC
```

### 1. SUGGESTION / RECHERCHE

Depuis n'importe quel écran :
- Scan ISBN → notice récupérée instantanément (BnF/Google Books)
- Recherche titre/auteur → sélection dans les résultats
- Suggestion depuis HAL Buy (IA) ou HAL Search (demande lecteur)

À ce stade : notice complète disponible, pas encore d'exemplaire.

### 2. PANIER D'ACQUISITION

Chaque item de panier contient :
```
notice         → identifiant + titre + auteur + éditeur + prix
quantite       → nombre d'exemplaires à commander
rayon          → Roman Ado | BD Jeunesse | Manga | Albums | Documentaires...
site           → Arcachon | La Teste | Gujan-Mestras | Le Teich
responsable    → qui a fait la suggestion
note           → justification ("demandé par 3 lecteurs", "prix Sorcières 2026")
prix_unitaire  → prix catalogue (auto depuis BnF/libraire)
```

Paniers **par rayon** et **par responsable** — vues combinables :
- "Toutes les suggestions BD de Thomas ce mois"
- "Budget Manga — Arcachon — juillet 2026"
- "Commande Mollat en attente"

### 3. SUIVI BUDGET

```
Par rayon × site × période :
  Budget alloué    : 2 500 € (défini en début d'année)
  Engagé           : 1 840 € (commandes passées)
  Dépensé          : 1 240 € (commandes reçues)
  Disponible       : 660 €
  
Alertes :
  ⚠ BD Jeunesse Arcachon — 94% du budget consommé
  ✓ Manga — 67% — en ordre
```

### 4. BON DE COMMANDE

Depuis le panier validé :
- Regroupement par **fournisseur** (chaque item a un fournisseur préféré ou auto)
- Génération du bon de commande :
  - **PDF imprimable** (format standard libraire)
  - **CSV/Excel** (format ORB, Electre)
  - **Email direct** avec PDF en pièce jointe
  - **EDI ONIX** pour les fournisseurs qui le supportent

### 5. FOURNISSEURS

Chaque fournisseur paramétré dans HAL :
```
nom          → "Mollat Bordeaux", "Fnac Pro", "ORB Decitre"
email        → cgalliot@decitre.fr
format       → ORB | CSV | PDF_email | EDI
remise       → 9% (remise habituelle)
delai_livraison → 5 jours ouvrés
compte_client → ref compte
```

### 6. RÉCEPTION

Scan du code-barres à l'arrivée du colis :
```
[SCAN ISBN]
↓
HAL trouve la notice ET le bon de commande associé
↓
Affiche : titre / qté commandée / qté déjà reçue
↓
[VALIDER RÉCEPTION]
↓
Statut bon de commande mis à jour
Budget : engagé → dépensé
```

### 7. CRÉATION EXEMPLAIRE (1 bouton)

Depuis la fiche de réception :
```
[CRÉER L'EXEMPLAIRE]
↓
HAL génère automatiquement :
  cote         → selon règles du site (BDJ/AST/1)
  code_barres  → prochain disponible dans la séquence
  site         → celui du panier
  statut       → "En traitement"
  date_acq     → aujourd'hui
  prix         → prix de commande
↓
IMPRESSION ÉTIQUETTE :
  • Étiquette dos : cote + code-barres
  • Étiquette couverture : code-barres
  • Format : compatible imprimante Zebra, Brother, Dymo
↓
ENCODAGE RFID :
  • HAL ouvre le dialogue d'encodage
  • Approcher le tag RFID de la tablette
  • Données encodées : ID document + site + AFI
  • Confirmation visuelle + sonore
↓
[DOCUMENT PRÊT] → apparaît dans l'OPAC, disponible au prêt
```

Si une notice existe déjà avec des exemplaires :
```
"Ce titre est déjà dans le fonds (2 exemplaires — 23 prêts)"
[AJOUTER UN EXEMPLAIRE] ou [ANNULER]
```

---

## BASE DE DONNÉES — SCHÉMA MODULE ACQUISITIONS

```sql
-- Panier d'acquisition
CREATE TABLE panier (
  id              INTEGER PRIMARY KEY,
  nom             TEXT,
  responsable     TEXT,
  rayon           TEXT,     -- 'Manga', 'BD Jeunesse', 'Roman Ado'...
  site            TEXT,
  fournisseur_id  INTEGER REFERENCES fournisseur(id),
  budget_alloue   REAL,
  statut          TEXT,     -- 'brouillon' | 'validé' | 'commandé' | 'reçu'
  date_creation   TEXT,
  date_commande   TEXT,
  date_reception  TEXT,
  notes           TEXT
);

-- Items du panier
CREATE TABLE panier_item (
  id              INTEGER PRIMARY KEY,
  panier_id       INTEGER REFERENCES panier(id),
  identifiant     TEXT REFERENCES notice(identifiant),
  quantite        INTEGER DEFAULT 1,
  prix_unitaire   REAL,
  statut          TEXT,     -- 'en attente' | 'commandé' | 'reçu' | 'annulé'
  qte_recue       INTEGER DEFAULT 0,
  date_reception  TEXT,
  note            TEXT
);

-- Fournisseurs
CREATE TABLE fournisseur (
  id              INTEGER PRIMARY KEY,
  nom             TEXT,
  email           TEXT,
  format_commande TEXT,     -- 'ORB' | 'CSV' | 'PDF' | 'EDI'
  remise          REAL,
  delai_livraison INTEGER,
  compte_client   TEXT,
  actif           BOOLEAN DEFAULT TRUE
);

-- Budgets par rayon × site × année
CREATE TABLE budget (
  id              INTEGER PRIMARY KEY,
  rayon           TEXT,
  site            TEXT,
  annee           INTEGER,
  montant_alloue  REAL,
  notes           TEXT
);

-- Exemplaires (enrichi vs schéma actuel)
CREATE TABLE exemplaire (
  id                    INTEGER PRIMARY KEY,
  identifiant           TEXT REFERENCES notice(identifiant),
  cote                  TEXT,
  code_barre            TEXT UNIQUE,
  rfid_uid              TEXT,     -- UID du tag RFID Nedap
  rfid_encode_le        TEXT,     -- date d'encodage RFID
  date_acquisition      TEXT,
  prix                  REAL,
  fournisseur_id        INTEGER REFERENCES fournisseur(id),
  panier_item_id        INTEGER REFERENCES panier_item(id),
  statut                TEXT,     -- 'En traitement' | 'Disponible' | 'En prêt'...
  site                  TEXT,
  localisation          TEXT,     -- 'Rayon A3' | 'Réserve'...
  support               TEXT,
  nb_prets_total        INTEGER DEFAULT 0,
  date_dernier_pret     TEXT,
  date_maj              TEXT
);

-- Règles de cote par médiathèque
CREATE TABLE regle_cote (
  id              INTEGER PRIMARY KEY,
  site            TEXT,
  type_document   TEXT,
  genre           TEXT,
  public_vise     TEXT,
  modele          TEXT,     -- '{TYPE}/{AUTEUR_3}/{TOME}'
  exemple         TEXT,
  priorite        INTEGER
);
```

---

## INTERFACE ACQUISITIONS — ÉCRANS

### Écran 1 : Recherche & Ajout au panier
- Barre de scan ISBN ou recherche texte
- Résultat : notice complète + couverture + prix + disponibilité dans le fonds
- Bouton "Ajouter au panier" → choisir rayon + site + quantité

### Écran 2 : Mon panier / Tous les paniers
- Vue par rayon et par responsable
- Total panier + budget disponible
- Filtres : rayon, site, fournisseur, statut
- Actions : valider, supprimer, déplacer vers autre fournisseur

### Écran 3 : Bon de commande
- Récapitulatif par fournisseur
- Remise automatique appliquée
- Total HT + TVA + TTC
- [Envoyer par email] [Exporter CSV/ORB] [Imprimer PDF]

### Écran 4 : Réception
- Scan des codes-barres à l'arrivée
- Comparaison commandé / reçu
- Signalement des manquants ou erreurs
- [Créer les exemplaires] en lot

### Écran 5 : Création exemplaire + RFID
- Cote générée (modifiable)
- Code-barres attribué
- [Imprimer étiquettes]
- [Encoder RFID] → dialogue NFC/tablette
- [Document prêt]

---

## INTÉGRATIONS EXTERNES

### Mollat (libraire local — Bordeaux)
- Format commande : email + PDF ou CSV
- Remise habituelle : à négocier (~9%)
- Livraison : 3-5 jours

### ORB / Decitre
- Format : CSV ORB (EAN;Titre;Auteur;Editeur;Prix;Quantité)
- Contact : cgalliot@decitre.fr
- API en négociation

### Electre (base bibliographique)
- API données bibliographiques (en cours de négociation)
- Remplacerait partiellement BnF + Google Books

### Decalog (SIGB actuel COBAS)
- Export EPPK (statistiques prêts) → HAL Stats
- Export UNIMARC (.mrc) → HAL Catalogue
- Pas d'API native — contournement par exports hebdomadaires

---

*Dernière mise à jour : 2026-07-22*
