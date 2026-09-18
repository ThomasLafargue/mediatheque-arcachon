# HAL — Spécifications Techniques Complètes
> Mise à jour : 2026-07-22

---

## ANALYSE CONCURRENTS (juillet 2026)

### CoLibris (colibris.net) — Logiq Systèmes, Aix-en-Provence
- 350 établissements clients
- Gamme Découverte (gratuit) → Intégral → Lynx-Libris
- **Points forts** : bien établi, support français, rapport annuel 1 clic, Magic-Barres
- **Faiblesses critiques** :
  - Windows uniquement ("Installation PC Windows en 1 clic") — pas de PWA, pas de tablette
  - IA superficielle (assistant conversationnel basique)
  - Interface 2000s malgré les mises à jour
  - Pas de workflow acquisitions intégré type e-commerce
  - Pas de RFID natif
- **Ce que HAL fait différemment** : 100% web/PWA, IA native profonde, acquisitions type Place des Libraires, RFID standard sans prestataire, open source

### Decalog — déjà analysé
- SIGB propriétaire dominant en lecture publique FR
- Fermé, cher, interface datée
- API non documentée publiquement

---

## HARDWARE CIBLE

### Tablettes (postes agents)
- **Android** avec NFC ISO 15693 intégré ← standard universel
- Clavier Bluetooth pour les tâches de bureau
- HAL tourne en PWA — installable comme une app native
- Recommandations : Samsung Galaxy Tab S9 FE, Lenovo Tab P12

### Scannettes sans fil
- Code-barres 1D/2D Bluetooth — compatible toutes marques
- Usage : réception commandes, prêts/retours, inventaire, récolement

### RFID — Solution standard sans prestataire
- Standard : **ISO 15693 HF 13.56 MHz** (universel bibliothèques)
- **Encodage sur tablette Android** via Web NFC API (Chrome Android)
  - Tags ISO 15693 standards (~0.30€/tag)
  - Écriture directe depuis HAL dans le navigateur Chrome
- **Alternative USB** : lecteur/encodeur ACR1252U (~50€) via Web Serial API
  - Fonctionne sur tout OS (Mac, Windows, Linux)
  - Format : CSV/JSON → commande en ligne
- **Données encodées** : identifiant HAL + site + bit de sécurité (AFI standard)
- Aucun prestataire, aucun abonnement, aucun SDK propriétaire

---

## SCHÉMA DES NOTICES — CHAMPS OBLIGATOIRES

L'IA enrichit automatiquement depuis BnF/Sudoc/Google Books.

### Identification
```
identifiant       EAN13/ISBN (obligatoire) ou CB:xxx si pas d'EAN
type_document     LIVRE | BD | MANGA | DVD | JEU | PERIODIQUE | CD
```

### Bibliographie
```
titre             obligatoire
sous_titre
serie
tome              TEXT ("1", "2", "HS", "0"...)
collection
createurs         auteur(s) principal/e(s) — obligatoire
createurs_secondaires
editeur           obligatoire
date_publication  YYYY ou YYYY-MM-DD — obligatoire
pays_edition      FR, BE, CH...
langue            fra, eng...
description_physique  "245 p. ; 24 cm"
```

### Classification
```
dewey             obligatoire pour documentaires
dewey_libelle     "Informatique", "Histoire de France"...
genre             Roman | Policier | SF | BD | Manga | Album | Documentaire...
public_vise       Bébé (0-3) | Enfant (3-6) | Jeune (6-9) | Ado (9-15) | Adulte
age_recommande    "8 ans et +" (TEXT)
pegi              3 | 7 | 12 | 16 | 18 (jeux)
```

### Enrichissement IA
```
resume            auto BnF/Google Books
image_url         couverture auto
mots_cles         tags thématiques
score_confiance   0 à 1
date_enrichissement
nb_sources_consultees
```

---

## RÈGLES DE COTE — CONFIGURABLES PAR MÉDIATHÈQUE

Variables : `{TYPE}` `{AUTEUR_3}` `{TITRE_3}` `{DEWEY}` `{TOME}` `{SERIE_3}`

### Exemples MAAT Arcachon
```
Roman jeunesse   MJ/HAR         Harry Potter à l'école des sorciers
Album 0-3 ans    ALB/BEA        Boucle d'Or
BD jeunesse      BDJ/AST/1      Astérix T.1
Manga            MAN/ONE/1      One Piece T.1
Roman adulte     ROM/BEA        Beauvoir
BD adulte        BD/MOE/2       Moebius
Documentaire     DOC/590        (Dewey animaux)
DVD              DVD/AVA        Avatar
Jeu              JEU/CAT        Catane
```

---

## MODULE ACQUISITIONS — HAL Buy

### Inspiration : Place des Libraires
L'interface de commande doit ressembler à une librairie en ligne :
- Navigation par rayon (Manga, BD, Roman Ado, Albums...)
- Recherche ISBN ou titre → fiche complète avec couverture
- [Ajouter au panier] en un geste
- Suivi budget visible en permanence
- Envoi commande et réception intégrés

### Workflow complet
```
Découverte (HAL Buy / scan ISBN / suggestion lecteur)
       ↓
Notice auto-enrichie BnF + couverture Google
       ↓
[+ Panier] → choisir rayon + site + quantité + note
       ↓
Vue panier → budget disponible affiché
       ↓
[Valider] → regroupement automatique par fournisseur
       ↓
Bon de commande généré (PDF + CSV ORB)
       ↓
[Envoyer à Mollat / ORB] par email direct
       ↓
Réception : scan code-barres → rapprochement auto
       ↓
[Créer exemplaire] → cote auto + code-barres + RFID
       ↓
[Imprimer étiquette] → Zebra / Brother / Dymo
       ↓
[Encoder RFID] → approcher tag de la tablette
       ↓
Document disponible dans l'OPAC
```

### Vue panier — inspirée e-commerce
```
┌─────────────────────────────────────────────────────────┐
│ 🛒 Panier BD Jeunesse — Arcachon                        │
│ Budget : ████████░░ 1 840 € / 2 500 € — 660 € restants  │
│                                                          │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ [Cover] Astérix T.40           Goscinny / Uderzo    │ │
│ │         Hachette — 13,95 €     BD Jeunesse · Arcach.│ │
│ │         Note : prix Fauve 2026   Qté : [1] ×  13,95│ │
│ │         ✓ Pas dans le fonds    [Supprimer]          │ │
│ └──────────────────────────────────────────────────────┘ │
│                                                          │
│ [Valider et commander chez Mollat — 3 titres — 41,85 €] │
└─────────────────────────────────────────────────────────┘
```

### Gestion multi-paniers
- Par **rayon** : Manga, BD Jeunesse, Roman Ado, Albums, Documentaires...
- Par **responsable** : Thomas, Marie, Direction...
- Par **fournisseur** : Mollat, ORB, Fnac Pro...
- Vue consolidée ou par critère
- **Partage de panier** : un agent suggère, un autre valide

### Suivi budget
```sql
SELECT
  rayon, site, annee,
  montant_alloue AS budget,
  SUM(CASE WHEN p.statut='commandé' THEN pi.quantite*pi.prix_unitaire ELSE 0 END) AS engage,
  SUM(CASE WHEN p.statut='reçu' THEN pi.quantite*pi.prix_unitaire ELSE 0 END) AS depense,
  montant_alloue
    - SUM(pi.quantite*pi.prix_unitaire) AS disponible
FROM budget b
LEFT JOIN panier p USING (rayon, site)
LEFT JOIN panier_item pi ON pi.panier_id = p.id
GROUP BY rayon, site
```

### Bon de commande — formats supportés
- **PDF** : format standard libraire, logo médiathèque, conditions
- **CSV ORB** : `EAN;Titre;Auteur;Editeur;Prix;Quantité`
- **Email direct** : sujet + corps + PDF en pièce jointe
- **EDI ONIX** : pour les fournisseurs qui le supportent (futur)

### Réception
```
Scan ISBN livre reçu
→ HAL affiche : [titre] commandé le [date] chez [fournisseur]
               Qté commandée : 2 | Qté déjà reçue : 0
→ [Réceptionner 1] ou [Réceptionner tout]
→ Budget : engagé → dépensé
→ [Créer exemplaire(s)]
```

### Si notice déjà en fonds
```
"Harry Potter T.1 est déjà dans le fonds.
 2 exemplaires actuels — 47 prêts au total.
 [Ajouter un nouvel exemplaire] [Annuler]"
```

---

## CRÉATION EXEMPLAIRE — WORKFLOW TABLETTE

```
[CRÉER L'EXEMPLAIRE]
        ↓
HAL génère automatiquement :
  cote          BDJ/AST/1  (règle configurée pour ce site)
  code_barres   300042      (prochain dans la séquence)
  site          Arcachon
  statut        En traitement
  date_acq      2026-07-22
  prix          13.95 €
        ↓
[🖨 IMPRIMER ÉTIQUETTE]
  Imprimante Zebra ZD421 / Brother QL / Dymo LabelWriter
  Format : étiquette dos (cote) + étiquette couverture (code-barres)
  Génération PDF ou ZPL directement depuis le navigateur
        ↓
[📡 ENCODER RFID]
  "Approchez le tag RFID de la tablette"
  Écriture via Web NFC (Chrome Android) :
    - Bloc 0 : identifiant HAL (ISBN/EAN)
    - Bloc 1 : code site (ARC/TES/GUJ/TEI)
    - AFI : 0x07 (sécurité activée)
  ✓ Tag encodé — confirmation visuelle + son
        ↓
[✅ DOCUMENT PRÊT]
  Statut → Disponible
  Visible dans HAL Search immédiatement
```

---

## SCHÉMA BASE DE DONNÉES — ACQUISITIONS

```sql
CREATE TABLE fournisseur (
  id              INTEGER PRIMARY KEY,
  nom             TEXT NOT NULL,
  email           TEXT,
  format_commande TEXT DEFAULT 'PDF',  -- PDF | ORB | CSV | EDI
  remise          REAL DEFAULT 0,
  delai_livraison INTEGER,
  compte_client   TEXT,
  actif           BOOLEAN DEFAULT TRUE
);

CREATE TABLE budget (
  id              INTEGER PRIMARY KEY,
  rayon           TEXT NOT NULL,
  site            TEXT NOT NULL,
  annee           INTEGER NOT NULL,
  montant_alloue  REAL NOT NULL,
  notes           TEXT,
  UNIQUE(rayon, site, annee)
);

CREATE TABLE panier (
  id              INTEGER PRIMARY KEY,
  nom             TEXT,
  responsable     TEXT NOT NULL,
  rayon           TEXT,
  site            TEXT,
  fournisseur_id  INTEGER REFERENCES fournisseur(id),
  statut          TEXT DEFAULT 'brouillon',
  -- brouillon | validé | commandé | partiellement_reçu | reçu | annulé
  date_creation   TEXT NOT NULL,
  date_commande   TEXT,
  date_reception  TEXT,
  notes           TEXT
);

CREATE TABLE panier_item (
  id              INTEGER PRIMARY KEY,
  panier_id       INTEGER NOT NULL REFERENCES panier(id),
  identifiant     TEXT NOT NULL REFERENCES notice(identifiant),
  quantite        INTEGER NOT NULL DEFAULT 1,
  prix_unitaire   REAL,
  statut          TEXT DEFAULT 'en attente',
  -- en attente | commandé | reçu | partiellement_reçu | annulé
  qte_recue       INTEGER DEFAULT 0,
  date_reception  TEXT,
  note            TEXT
);

CREATE TABLE exemplaire (
  id                INTEGER PRIMARY KEY,
  identifiant       TEXT NOT NULL REFERENCES notice(identifiant),
  cote              TEXT,
  code_barre        TEXT UNIQUE,
  rfid_uid          TEXT,           -- UID lu depuis le tag
  rfid_encode_le    TEXT,
  date_acquisition  TEXT,
  prix              REAL,
  fournisseur_id    INTEGER REFERENCES fournisseur(id),
  panier_item_id    INTEGER REFERENCES panier_item(id),
  statut            TEXT DEFAULT 'En traitement',
  site              TEXT,
  localisation      TEXT,
  support           TEXT,
  nb_prets_total    INTEGER DEFAULT 0,
  date_dernier_pret TEXT,
  date_maj          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE regle_cote (
  id              INTEGER PRIMARY KEY,
  site            TEXT NOT NULL,
  type_document   TEXT,
  genre           TEXT,
  public_vise     TEXT,
  modele          TEXT NOT NULL,    -- '{TYPE}/{AUTEUR_3}/{TOME}'
  exemple         TEXT,
  priorite        INTEGER DEFAULT 10
);
```

---

## FOURNISSEURS CIBLES

| Fournisseur | Format | Contact | Notes |
|-------------|--------|---------|-------|
| Mollat Bordeaux | PDF email | - | Libraire local, ~9% remise |
| ORB / Decitre | CSV ORB | cgalliot@decitre.fr | Déjà utilisé, API en cours |
| Fnac Pro | CSV | - | Délais courts |
| Electre | API | - | Base bibliographique (négociation) |

---

## HAL vs CONCURRENTS

| Fonctionnalité | HAL | CoLibris | Decalog | Koha |
|----------------|-----|----------|---------|------|
| PWA / tablette native | ✅ | ❌ Windows only | ❌ | ⚠️ |
| IA native profonde | ✅ | ⚠️ basique | ❌ | ❌ |
| Acquisitions type e-commerce | ✅ | ⚠️ formulaires | ⚠️ | ⚠️ |
| RFID sans prestataire | ✅ ISO standard | ❌ | ❌ | ❌ |
| Open source | ✅ | ❌ | ❌ | ✅ |
| Recherche conversationnelle | ✅ | ❌ | ❌ | ❌ |
| Installation < 10 min | ✅ | ⚠️ | ❌ | ❌ |
| Multi-sites natif | ✅ | ✅ | ✅ | ✅ |

---

*Dernière mise à jour : 2026-07-22*
