# HAL — Décisions Architecturales Fondamentales
> Décisions définitives — 2026-07-22
> Ces choix ne sont pas négociables et guident toute l'architecture.

---

## LES 5 PRINCIPES ABSOLUS

### 1. ZÉRO ABONNEMENT
Aucun service tiers payant récurrent.
- Pas d'ORB, pas d'Electre, pas de Nedap, pas de CoLibris
- Pas d'API key payante, pas de SaaS externe
- Bibliographie : BnF SRU (gratuit) + Google Books (gratuit) + base accumulée
- RFID : ISO 15693 standard, tags à 0.25€, Web NFC natif Android
- Hébergement : auto-hébergé ou serveur dédié (one-time)

### 2. TABLETTES + SCANNETTES UNIQUEMENT
Aucun poste fixe. Toutes les tâches sur tablette Android avec clavier Bluetooth.
- Prêts, retours, catalogage, commandes, réception, RFID : tout sur tablette
- Scannettes sans fil Bluetooth pour codes-barres
- PWA installable, fonctionne offline

### 3. TOUT INTÉGRÉ DANS HAL
Un seul outil, tout dedans.
- SIGB (prêts, retours, réservations, adhérents)
- OPAC (catalogue public, recherche conversationnelle)
- Base bibliographique (notices, couvertures, résumés, Dewey)
- Acquisitions (paniers, commandes, réception, exemplaires, RFID)
- Statistiques, désherbage, rapports

### 4. ACHATS DIRECTS AUX LIBRAIRES
Pas d'intermédiaire.
- HAL envoie le bon de commande directement (email PDF ou EDI)
- Aucune plateforme tierce entre HAL et le fournisseur
- Mollat Bordeaux, et tout autre libraire : relation directe

### 5. OPEN SOURCE
Code public, pas de dépendance fournisseur.
- GitHub, licence AGPL
- N'importe quelle bibliothèque peut l'installer et l'adapter
- Communauté = maintenance collective

---

## HARDWARE — SEULS ÉQUIPEMENTS NÉCESSAIRES

### Tablette Android (poste principal)
- NFC ISO 15693 intégré (standard sur tous les Android récents)
- Chrome pour HAL (PWA)
- Clavier Bluetooth pliable pour catalogage/administration
- USB-C pour charge

**Recommandation** : Samsung Galaxy Tab A9+ (~280€) ou Tab S9 FE (~450€)
Les deux ont le NFC ISO 15693. Pas besoin de matériel spécialisé.

### Scannette sans fil Bluetooth
- Code-barres 1D/2D
- Se connecte à la tablette comme un clavier (HID Bluetooth)
- HAL reçoit le scan comme une saisie clavier — zéro driver
- **Recommandation** : Tera D5100 (~60€) ou Zebra CS6080 (~180€)

### Tags RFID
- Standard ISO 15693 HF 13.56 MHz
- **Non propriétaires** — achat en direct (~0.20-0.30€/tag)
- Format autocollant pour documents, antivol intégré (AFI)
- Compatible n'importe quelle tablette Android avec NFC

### Imprimante étiquettes
- Bluetooth, portable ou fixe
- **Recommandation** : Brother QL-820NWBc (~200€) — Bluetooth + Wifi
- HAL génère les étiquettes en PDF ou ZPL directement

### C'est tout.
Pas d'encodeur RFID dédié, pas de borne de prêt propriétaire,
pas de serveur local, pas de PC fixe.

---

## RFID — ARCHITECTURE TECHNIQUE

### Écriture depuis la tablette (Web NFC API)

```javascript
// HAL écrit sur le tag ISO 15693 directement depuis Chrome Android
async function encoderRFID(identifiant, site) {
  const ndef = new NDEFReader();
  await ndef.write({
    records: [{
      recordType: "url",
      data: `hal://doc/${identifiant}?site=${site}`
    }]
  });
  // AFI (sécurité antivol) : géré séparément via commande ISO 15693
}
```

### Données encodées sur chaque tag
```
Identifiant HAL  : ISBN/EAN du document
Site             : ARC | TES | GUJ | TEI
AFI              : 0x07 (actif) → 0xC2 (désactivé au prêt)
```

### Lecture au prêt/retour
- Approcher le document de la tablette → lecture NFC instantanée
- HAL identifie le document sans scan code-barres
- Option : scannette si le lecteur préfère

### Sécurité antivol
- AFI 0x07 = document sécurisé (alarme portique si sorti)
- Au prêt : HAL écrit AFI 0xC2 (désactivé)
- Au retour : HAL écrit AFI 0x07 (réactivé)
- Compatible portiques antivol ISO 15693 standard

---

## BASE BIBLIOGRAPHIQUE INTÉGRÉE

### Sources gratuites, sans abonnement

| Source | Type | Notices | Gratuit |
|--------|------|---------|---------|
| BnF SRU | API | 15M notices françaises | ✅ illimité |
| Google Books | API | Mondial | ✅ gratuit (quota) |
| Open Library | API | 30M notices | ✅ illimité |
| Sudoc | Z39.50 | Universitaire FR | ✅ illimité |
| Base HAL accumulée | Locale | Croît avec l'usage | ✅ toujours |

### Principe d'accumulation
```
Première fois qu'un ISBN est traité :
  → Recherche BnF → si trouvé : stockage
  → Sinon Google Books → si trouvé : stockage
  → Sinon Open Library → si trouvé : stockage
  → Notice incomplète créée + flag "à compléter"

Deuxième fois que le même ISBN est traité :
  → Notice déjà en base, résultat instantané (0 ms, 0 appel externe)
```

### Après 2-3 ans d'utilisation
La base HAL contiendra l'essentiel de la production éditoriale française
sans jamais payer un centime à Electre ou à quiconque.

---

## MODULE ACHATS — SANS INTERMÉDIAIRE

### Workflow direct libraire

```
[Scan ISBN ou recherche titre]
         ↓
Notice enrichie automatiquement
         ↓
[+ Ajouter au panier]
Rayon / Site / Quantité / Note
         ↓
Vue panier avec budget en temps réel
         ↓
[Commander chez Mollat]
HAL génère PDF et envoie l'email directement :
  À : commandes@mollat.com
  Objet : Commande MAAT Arcachon — [date]
  PJ : bon_de_commande_20260722.pdf
         ↓
Mollat livre (3-5 jours)
         ↓
[Réceptionner] — scan code-barres boîte par boîte
  HAL rapproche automatiquement avec la commande
         ↓
[Créer exemplaires] en lot
  Cote auto + code-barres + date acquisition
         ↓
[Imprimer étiquettes] → Brother Bluetooth
         ↓
[Encoder RFID] → approcher tag de la tablette
  Écriture instantanée (1 seconde)
         ↓
Document sur l'étagère, visible dans l'OPAC
```

### Libraires configurés dans HAL
```
nom       : Mollat Bordeaux
email     : commandes@mollat.com
remise    : 9%
format    : PDF (email direct)
délai     : 5 jours

— Ajouter d'autres libraires selon les besoins —
```

### Ce qu'ORB faisait, HAL le fait mieux
- Catalogue de commande : ✅ intégré dans HAL Buy
- Panier : ✅ plus riche (budget, rayon, responsable)
- Bon de commande : ✅ PDF généré directement
- Envoi fournisseur : ✅ email direct sans intermédiaire
- Suivi commande : ✅ dans HAL
- Réception : ✅ dans HAL
- Création exemplaire : ✅ automatique dans HAL

---

## ARCHITECTURE LOGICIELLE

```
HAL (application unique)
  ├── HAL Search     OPAC public — lecteurs
  ├── HAL Desk       Prêts/retours — agents (tablette)
  ├── HAL Catalogue  Notices, enrichissement, désherbage
  ├── HAL Buy        Acquisitions, commandes, réception
  ├── HAL Stats      Tableaux de bord, rapports
  └── HAL Admin      Adhérents, paramètres, utilisateurs

Stack :
  Backend  : Python FastAPI
  Frontend : Next.js 14 PWA + Tailwind
  Base     : PostgreSQL (auto-hébergé)
  Cache    : Redis
  Biblio   : BnF SRU + Google Books + Open Library (gratuits)
  RFID     : Web NFC API (natif Chrome Android)
  Email    : SMTP standard (serveur propre ou Gmail/Brevo gratuit)
  Déploiement : Docker Compose (1 commande)
```

---

## CE QU'ON NE FAIT PAS

| ❌ Hors périmètre | Raison |
|-------------------|--------|
| ORB | Remplacé par achats directs intégrés |
| Nedap / prestataire RFID | Remplacé par Web NFC ISO 15693 standard |
| Electre | Remplacé par BnF + Google Books + base accumulée |
| Postes fixes | Tablettes uniquement |
| Abonnements SaaS | Zéro dépendance externe payante |
| App native iOS/Android | PWA suffit, pas de store |

---

*Décisions validées par Thomas Lafargue — 2026-07-22*
*Ces principes guident toutes les décisions techniques de HAL.*
