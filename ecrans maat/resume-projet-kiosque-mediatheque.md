# Projet Kiosque Numérique — Médiathèque d'Arcachon
## Résumé complet de la conversation

---

## 1. Contexte général

- **Porteur** : Thomas, responsable jeunesse à la Médiathèque d'Arcachon (réseau COBAS)
- **Objectif** : Deux outils d'affichage numérique autonomes, hébergés sur OVH, alimentés par les données réelles du catalogue Decalog
- **Contrainte principale** : Le site OPAC (`mediatheques.agglo-cobas.fr`) est protégé par un `robots.txt` interdisant l'accès automatisé — scraping impossible. L'accès en temps réel au flux Decalog n'a pas encore pu être obtenu (bureaucratie). **Solution retenue : export UNIMARC mensuel depuis Decalog.**

---

## 2. Outil 1 — Mosaïque tactile (hall d'accueil)

### Accès
**URL :** `http://afwnyvo.cluster021.hosting.ovh.net/mediatheque-cobas-mosaique.html`

### Description
Mosaïque interactive de couvertures de livres en 4 rangées × 11 colonnes = 44 tuiles, affichée en plein écran sur l'écran tactile de l'accueil.

### Fonctionnement technique
- **Fichier** : `mediatheque-cobas-mosaique.html` — fichier HTML/CSS/JS autonome, sans dépendance externe
- **Données** : 1313 titres réels (livres imprimés, BD, mangas) extraits du fichier UNIMARC
- **Couvertures** : URL directe extraite de la zone 856 du fichier MARC (CDN Decalog/ORB), avec fallback Amazon et OpenLibrary
- **Pool de confiance** : au démarrage, toutes les images sont testées en parallèle — seules celles qui chargent réellement constituent le pool affiché (jamais de case vide)
- **Rotation** : toutes les 5 secondes, une tuile se retourne en 3D pour révéler une nouvelle couverture
  - La même tuile ne se retourne jamais deux fois de suite
  - La face cachée (celle qui va apparaître) est mise à jour avant la rotation
  - File mélangée sans doublon visible à l'écran
  - Fallback : si une image échoue, le système parcourt le pool jusqu'à trouver une image fonctionnelle
  - Les images qui échouent deux fois sont retirées définitivement du pool
- **Popup** : clic sur une tuile → fenêtre avec couverture, titre, auteur, éditeur, année, résumé complet, cote, public visé, support — fermeture automatique après 1 minute ou via croix
- **Fond** : noir uniforme (`#000`)

### Données extraites du MARC
| Zone MARC | Contenu |
|-----------|---------|
| 073 / 010 $a | ISBN |
| 200 $a | Titre |
| 700/701 $a+$b | Auteur (nom + prénom) |
| 214 $c / $d | Éditeur / Année |
| 330 $a | Résumé complet |
| 856 $u | URL couverture directe |
| 995 $k | Cote |
| 995 $l | Public visé |
| 995 $e / $w | Type de document |

### Filtres appliqués à l'extraction
- Exemplaire de la **Médiathèque d'Arcachon** uniquement (zone 995)
- Types conservés : `Livre`, `Bande dessinée`, `Manga`, `Imprimé`
- Types exclus : DVD, Jeux vidéo, Jeux de société, Revues

### Mise à jour mensuelle
1. Exporter depuis Decalog un fichier UNIMARC des **4 derniers mois glissants**
2. Envoyer le fichier `.mrc` à Claude
3. Claude extrait les nouveaux ISBN absents de la liste existante et les ajoute
4. Retéléverser le `.html` sur OVH via Cyberduck

### Déploiement OVH
- **Hébergeur** : OVH shared hosting
- **Serveur SFTP** : `ftp.cluster121.hosting.ovh.net` port 22
- **Identifiant** : `afwnyvo`
- **Dossier** : `www/`
- **Outil** : Cyberduck (protocole SFTP, **pas FTP**)
- ⚠️ Toujours vérifier le nom exact du fichier avant l'upload (`mediatheque-cobas-mosaique.html`)

---

## 3. Outil 2 — Diaporama Jeunesse (espace jeunesse, écran non tactile)

### Accès
**URL :** `http://afwnyvo.cluster021.hosting.ovh.net/mediatheque-diaporama-jeunesse.html`

### Description
Diaporama automatique des nouveautés jeunesse et adolescent, affiché en plein écran paysage sur un second écran non tactile dans l'espace jeunesse.

### Fonctionnement technique
- **Fichier** : `mediatheque-diaporama-jeunesse.html` — fichier HTML/CSS/JS autonome
- **Données** : 494 titres jeunesse/adolescent/tout public avec couverture confirmée
- **Filtre** : `pub = Jeunesse | Adolescent | Tout public` uniquement
- **Durée par slide** : 15 secondes
- **Transition** : fondu enchaîné

### Mise en page
- **Colonne gauche (52%)** : illustration en position absolue avec `inset: 20px` et `object-fit: contain` — l'image occupe tout l'espace disponible quelle que soit son format (portrait, paysage, carré), avec 20px de marge tout autour
- **Fond de colonne** : image floutée (blur + assombrie) en arrière-plan pour combler l'espace
- **Colonne droite (48%)** : fond blanc, informations du document
- **Barre de progression** : verticale, positionnée à la jointure des deux colonnes (`left: 52%`), monte de bas en haut, couleur dynamique selon le public visé

### Code couleur par public
| Public | Couleur | Application |
|--------|---------|-------------|
| Jeunesse | Orange `#d4782a` | Badge, auteur, "Nouvelle acquisition", barre de progression |
| Adolescent | Bleu `#3a6ea8` | Idem |
| Tout public | Vert `#3d6b4f` | Idem |

### Contenu affiché par slide
- Badge public visé (haut gauche de la colonne illustration)
- Label "NOUVELLE ACQUISITION" (coloré)
- Titre (grande typographie Playfair Display)
- Auteur en italique (coloré)
- Année · Éditeur
- Résumé complet (scrollable silencieusement si trop long)
- Tags : Cote + Support
- Compteur de slides (bas gauche)
- Signature "Médiathèque d'Arcachon" (bas droite)

### Alternance par type
Les slides sont organisés en **round-robin** entre les buckets de support (Imprimé, BD, Manga) pour alterner au maximum les types de documents.

### Mise à jour mensuelle
Même procédure que la mosaïque — le script Python extrait automatiquement les titres Jeunesse/Adolescent/Tout public avec couverture.

---

## 4. Architecture du script d'extraction UNIMARC

```python
# Logique générale du parseur MARC21 maison (sans dépendance externe)
# 1. Lire le fichier .mrc binaire notice par notice
# 2. Parser le répertoire (directory) pour localiser chaque zone
# 3. Extraire les sous-champs via le séparateur \x1f + code
# 4. Filtrer sur la présence d'un exemplaire Médiathèque d'Arcachon en zone 995
# 5. Exclure les types non souhaités (DVD, Jeux, Revues)
# 6. Générer un bloc JS const BOOKS=[...] ou const SLIDES=[...]
```

---

## 5. Bugs résolus notables

| Bug | Cause | Solution |
|-----|-------|----------|
| Tuiles noires après rotation | `face.style.cssText` écrasait `position:absolute` défini en CSS, décalant la face hors du cadre | Remplacé par `face.style.background='#000'` uniquement |
| `[object Object]` dans popup | Nouveaux livres injectés dans `const m=[]` du popup au lieu de `const BOOKS=[]` (mauvais `];` trouvé par `rindex`) | Correction manuelle par recherche de position exacte |
| Cases vides après rotation | Pool insuffisant + fallback abandonné trop tôt | Fallback récursif parcourant tout le pool ; retrait définitif des images qui échouent deux fois |
| Marge non uniforme sur les tuiles | CSS `padding` en % sur position imbriquée = calcul instable | Mesure JS en pixels réels de la tuile, application du padding en px |
| Upload Excel au lieu de HTML | Erreur humaine dans Cyberduck | Toujours vérifier le nom du fichier avant de glisser |

---

## 6. Prochaines étapes

- [ ] Mise à jour mensuelle (fichier UNIMARC des 4 derniers mois)
- [ ] Intégrer les slides d'information ville dans le diaporama jeunesse (à fournir par Thomas)
- [ ] Déploiement définitif sur l'infrastructure COBAS (si accord de l'informatique)
- [ ] Si flux Decalog obtenu un jour : réactiver la disponibilité en temps réel dans le popup de la mosaïque

---

*Document généré le 22 juillet 2026*
