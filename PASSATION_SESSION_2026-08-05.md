# Passation de session — 30 juillet 2026 (mis à jour le 13/08)

Document de reprise pour une nouvelle conversation Claude. Tout l'état du
projet MAAT (Médiathèque d'Arcachon) au 30/07/2026 au soir, après la
session « audit DVD » du soir même (voir section Chantier DVD). Voir en
bas de fichier la section « Session du 10-13/08 » pour les tout derniers
événements (appel Tite Live, remontée COBAS, scénarios comparatifs).

## Le projet en une phrase

Outil de gestion du fonds de la Médiathèque d'Arcachon : base Turso en ligne
(copie enrichie de l'export Decalog), chat Streamlit pour les agents,
écrans du hall (mosaïque + diaporama jeunesse sur OVH), veille acquisitions,
récolement, et fichiers de correction à ressaisir dans Decalog.

## Architecture

- **Base** : Turso (libSQL), `mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io`.
  Connexion unique via `db.py` (correctif SSL certifi inclus). Copie locale
  `inventaire.db` = instantané du 28/06, roue de secours uniquement.
- **Chat** : `app_conversationnel.py`, déployé sur Streamlit Cloud depuis
  GitHub (`ThomasLafargue/mediatheque-arcachon`) → **tout changement du chat
  exige commit + push**. SELECT-only sur le catalogue, jeton d'écriture
  séparé (`TURSO_AUTH_TOKEN_ECRITURE`) pour ses propres tables.
- **Écrans** : `generer_ecrans_maat.py` lit le dernier `.mrc`, génère
  2 HTML dans `ecrans maat/`, envoie sur OVH par SFTP (`OVH_SFTP_*` dans
  `.env`). URLs publiques :
  - `http://afwnyvo.cluster021.hosting.ovh.net/mediatheque-diaporama-jeunesse.html`
  - `http://afwnyvo.cluster021.hosting.ovh.net/mediatheque-cobas-mosaique.html`
- **Sécurité (règles absolues)** : Claude ne pousse jamais sur GitHub —
  Thomas fait `git add/commit/push` lui-même. `.env` jamais versionné.
  Le chat ne modifie jamais le catalogue.
- **Mac mini** : seul point d'accès réseau à Turso. L'environnement Claude
  (sandbox) ne peut PAS joindre la base en ligne → Claude écrit les
  scripts, Thomas les exécute et colle les résultats.

## Services automatiques (launchd)

| Service | Quand | Rôle |
|---|---|---|
| `com.maat.enrichissementseries` | permanent (KeepAlive) | enrichissement par lots de 200, s'arrête seul quand la file est vide |
| `com.maat.veillehebdo` | lundi 8h | 4 veilles + surveillance des sources |
| `com.maat.recolement` | lundi 7h30 | verse `recolement_scans.txt`, régénère `Recolement_etat.xlsx` |
| import hebdo | manuel (`import_hebdomadaire.sh`) | .mrc + flux + écrans + kickstart enrichissement |

Logs dans `/tmp/journal_*.log`. Suivi enrichissement :
`_series_deja_tentees.txt` (mtime = dernier lot fini).

## Décisions structurantes (à ne pas défaire)

- **public_vise normalisé (27/07)** : 4 valeurs exactement — `Adulte`,
  `Jeunesse`, `Adolescent`, `Tout public`. Règle unique dans
  `public_vise.py`, appliquée par TOUS les canaux d'écriture (import,
  enrichissement, veille) et à la lecture du `.mrc` par les écrans.
- **Règle manga (Thomas)** : PEGI ≥ 14 → Adulte, sinon Jeunesse. Pas de
  rayon manga ado. `pegi` = nombre pur (« 12 », plus jamais « PEGI 12 »).
- **Genres** : souvent composés (« Aventure / Humour »). Le chat filtre
  TOUJOURS en `LIKE '%mot%'`. Fusion des synonymes faite (fichier validé
  `Fusion_genres_2026-07-27.xlsx`, appliqué). Canonisation à l'écriture via
  `proposer_fusion_genres.proposer()`.
- **Collections d'éditeur ≠ séries** : `collections_editeur.py` (règle
  parenthèse MARC = collection ; « Mes p'tits docs » etc. restent séries
  par décision de Thomas ; « 16-17 » = gros caractères À vue d'œil, écarté).
- **Zone MARC 410** lue comme lien de collection→série pour les BD
  (correction majeure : Lucky Luke 6→14 albums).
- **Périodiques exclus** de toutes les listes de correction Decalog (type
  `REVUE`, 3 882 notices, légitimement sans EAN ni statut). Livres < 2000
  exclus des recherches d'EAN (fonds local patrimonial).
- **Suggestions** : catégorie/public/genre TOUJOURS renseignés, par le
  moteur complet (`chercher_isbn`) dès l'insertion en veille. Défauts
  d'aveu : « À classer » / « Tout public » / « À préciser » (rares).
  Panneau de tri : menu Public en liste fixe des 4 valeurs.
- **Écritures Turso par paquets** (400 lignes/requête) : tout script qui
  écrit en masse doit grouper (leçon : fréquentation 1h → 2 s).
- **Longs scripts** : lancer avec `python3 -u ... > log 2>&1 &` (sinon
  sortie invisible : mise en tampon).

## Base : état au 30/07

44 324 notices (32 378 livres). 6 index posés le 27/07 (serie+tome,
categorie+public, public, date_publication, date_enrichissement, prets).
**Enrichissement terminé** : 0 notice jamais tentée, 17 820 traitées au
total, taux de réussite final 94-96 % (Place des Libraires en 1re source).
Restes incompressibles : 441 BD/manga sans série, 2 135 livres sans
catégorie, 14 309 sans couverture.

## Livrables prêts pour l'équipe

- `Corrections_Decalog_2026-07-30.xlsx` : **6 241 corrections sûres**
  (4 372 séries, 1 869 tomes) + 3 620 à vérifier + 989 sans EAN.
- `Audit_DVD_2026-07-30.xlsx` : **550 anomalies de cotation DVD** +
  `Supports_a_corriger_2026-07-30.xlsx` : 12 erreurs de support (détail
  section Chantier DVD).
- `EAN_a_corriger_2026-07-30.xlsx` + table **`ean_retrouve`** en base :
  969/989 EAN retrouvés (294 confiance élevée, 485 moyenne, 190 faible).
  Le chat sait répondre « quels EAN en confiance élevée reste-t-il à
  saisir ? » et gérer `statut_saisie`.
- `Guide_vocabulaire_chat_2026-07-30.docx` : guide agents à jour
  (4 publics, genres en LIKE, règle 500 lignes/export Excel, listes de
  correction ean_retrouve + support_a_corriger et marquage « saisie »).
- Fréquentation chargée : 1 931 jours (30/01/2020 → 28/07/2026) + détail
  horaire.

## Récolement (rentrée)

Choix : scanette code-barres filaire (0 €). Un seul fichier
`recolement_scans.txt` alimenté au fil de l'eau (zones mélangées, retours
compris) ; mémoire `_recolement_memoire.txt` avec dates multiples par
document (re-scan = probable prêt/retour, jamais recompté à tort) ;
rapport auto le lundi 7h30. Scanner le CODE-BARRES EXEMPLAIRE, pas l'ISBN.
Piste RFID : étiquettes Nedap/Boingtech probablement **UHF** (mail envoyé à
Nedap pour confirmer + convention EPC↔code-barres). Si achat : Zebra
RFD8500 d'occasion **version EU** (250-500 €) ou Chainway R5 neuf (~450 €).

## Chantier DVD : audit TERMINÉ le 30/07 au soir

Règle de cotation (Thomas) : films adultes « F XXX » (3 lettres du
réalisateur), jeunesse « FJ XXX », **Disney tous à « FJ DIS »**,
documentaires DVD en cote Dewey, **« B XXX » = biographies filmées
(rayon légitime, décision Thomas 30/07)**, pas de séries. Nom de
réalisateur de 2 lettres (Ly, Sy, To, Do, Oh) → cote de 2 lettres,
conforme. Cotes « JV ... » = jeux vidéo égarés en support DVD : exclus
de l'audit (décision Thomas : pas de liste de correction pour eux).

**Bilan final (`Audit_DVD_2026-07-30.xlsx`, run validé)** : 550 anomalies
sur 3 412 exemplaires (16,1 %) — 275 lettres≠réalisateur, 80 cote/public
contradictoires, 77 sans réalisateur, 59 Disney pas en FJ DIS, 36 cotes
hors norme (typos à recoter : F ALlM, FSTE, J xxx→FJ, PAR→F PAR… + le jeu
« tru »→JV TRU), 18 FJ DIS non-Disney, 5 sans cote. C'est la liste de
correction Decalog pour l'équipe.

**Découverte majeure** : parmi les cotes hors norme, 15 identifiants en
978/979 vérifiés UN PAR UN sur internet (librairies, éditeurs) →
**11 LIVRES saisis à tort en support DVD dans Decalog** (2 albums
jeunesse, 4 BD, 1 roman, 1 roman jeunesse, 3 romans gros caractères) +
1 vrai DVD mal coté « BD BRO »→F BRO ; les 4 autres sont de vrais DVD
documentaires à ISBN (L'Harmattan…), légitimes en rayon B.
→ `Supports_a_corriger_2026-07-30.xlsx` + table **`support_a_corriger`**
en base (chargée, 12 lignes, script `charger_supports_en_base.py`,
même mécanique que `charger_ean_en_base.py` : statut_saisie préservé).

**Chat enrichi (commit 7694e74, poussé et déployé)** : table
`support_a_corriger` documentée dans le prompt + nouvel outil
`marquer_statut_saisie(table, identifiant, statut)` limité aux tables
`ean_retrouve` et `support_a_corriger` — comblait un trou : le prompt
promettait le marquage « saisie » mais aucun outil n'existait.
Guide agents mis à jour : `Guide_vocabulaire_chat_2026-07-30.docx`
(section 3 : les deux listes de correction suivies en base).

**Point en suspens (Thomas n'a pas tranché)** : les 59 « Disney pas en
FJ DIS » incluent des films seulement DISTRIBUÉS par Disney (Sister act,
La Plage/Fox, publics Adulte) — la détection se fait sur l'éditeur. Si la
règle FJ DIS ne vise que l'animation/jeunesse Disney, resserrer
`est_disney()` et la liste fondra.

## En attente / à venir

- **Diversifier les sources de suggestions (décidé le 05/08)** — audit
  fait : PdL/Kibookin ≈ 28 % des ~450 suggestions, correct globalement
  mais diversité JEUNESSE trop étroite. À faire, dans l'ordre :
  1. **Ricochet** : seulement 10 suggestions — examiner le rendement de
     `veille_ricochet.py` lundi après la veille hebdo (site difficile à
     scraper, cf. note « rendu côté client »), renforcer si possible ;
  2. **Mollat** à évaluer comme source de sélections (demande Thomas) —
     ⚠ même problème connu : pages illisibles sans JavaScript, vérifier
     s'il existe des flux/pages exploitables (RSS, sitemap) ;
  3. **Revue des livres pour enfants (BnF-CNLJ)** : intégrer la sélection
     annuelle (la prescription bibliothécaire jeunesse de référence) ;
  4. **Hygiène** : 57 suggestions avec source « None » — renseigner une
     source (« chat/manuel ») pour garder les statistiques fiables.
- **RÉPONSES REÇUES le 06/08** :
  - **Nedap (Sylvain Duret, sylvain.duret@nedap.fr, 06.33.04.15.70)** :
    puces **HF 13,56 MHz ISO 15693** (PAS UHF !) — Zebra RFD8500/Chainway R5
    inutilisables, abandonner cette piste. Leur lecteur d'inventaire
    **PRH200** fait le récolement (codes-barres + RCR → LibNet, zones de
    récolement, mode recherche, antivol en masse). → DEMANDER DEVIS PRH200
    (achat/location) vs scanette 0 €. Le PRH200 = FEIG ISC.PRH200-BW
    (2 000-3 500 € HT constatés, sur devis). Test smartphone NFC fait le
    07/08 : les puces répondent mais portée ~2 cm → inutilisable en rayon ;
    la valeur du PRH200 est son antenne (30-40 cm à travers les dos).
    Verdict Thomas : scanette codes-barres conservée pour la rentrée.
    Comptage : horaires LibNet réglés
    8h-20h (confirme l'écart écran) ; option affichage « ignorer les
    horaires » possible → à demander pour recoller à la série historique.
  - **ORB = Decitre (Catherine Galliot, cgalliot@decitre.fr — vacances
    jusqu'à fin août ; relais nboyer@/ncentazzo@/chargeclientele@decitre.fr)** :
    API Search très complète MAIS 150 € + 500 €/an + **18 480 € HT
    d'initialisation 44 000 notices** + 0,49 €/notice ensuite → sans
    intérêt, l'enrichissement est déjà fait gratuitement via PdL. À saisir
    gratuitement : test API (doc.api.base-orb.fr, comptes démo) et offre de
    **taux de correspondance** (leur envoyer nos EAN). Leur équipe technique
    veut une **présentation du cas d'usage IA en bibliothèque** — carte à jouer.
    **PERCÉE du 07/08 — accents cassés des imports ORB→Decalog RÉSOLUS** :
    l'export .not des bons de commande ORB est en ISO 5426 (leur défaut
    documenté `unimarc_encoding`), lu de travers par Decalog. Remède local :
    `convertir_orb_utf8.py` (reconstruit l'ISO 2709 en UTF-8, zone 100 mise
    à jour ; testé sur « Commande 4-2026 » : 322/322 notices propres, import
    Decalog à valider par Thomas). Remède définitif À DEMANDER à Decitre :
    passer le compte en `unimarc_encoding = utf8` (paramètre standard).
    L'automatisation complète (supprimer export/import) = endpoint /orders
    de leur API, à négocier. `orb_test_api.py` prêt pour le compte démo.
  - **Tite Live contacté le 06/08** (mail « réseau de 4 médiathèques
    COBAS, >100 000 documents ») : proposition API Mediabase + paniers +
    commande Librairie Générale + export UNIMARC. Réponse attendue. La
    Librairie Générale a déjà un site de réservation sur la plateforme
    Tite Live (librairiegeneralearcachon.fr, 1 M+ titres) — le circuit
    existe à moitié.
  - **Sélection officielle des Incorruptibles** à ajouter en source de
    veille : https://prix.lesincos.com/la-selection (liste par niveau).
- **Réponse toujours attendue** : Decalog (API + situations d'exemplaires
  dans l'export).
- **Diapos ville** : 4 visuels dans `diapos_ville/` intercalés toutes les
  4 diapos du diaporama (mécanisme : déposer/supprimer un fichier image
  dans ce dossier suffit). Demander les originaux au service com de la
  mairie (l'Olympia a des reflets).
- **Mesure du gain Place des Libraires** : rappel du 29/07 9h jamais
  examiné ; le gain est de fait démontré (94-96 % vs ~50 % avant).
- **EAN non-livres** (optionnel) : 262 jeux, 214 DVD, 170 CD sans EAN —
  nécessiterait des sources par support (jeux prioritaires si un jour).
- **Fonds de tiroir sans urgence** : 3 tables vides (commande, livraison,
  flux_mensuel), 3 colonnes mortes de notice (statut_publication,
  score_confiance, nb_sources_consultees) + index inutile
  `idx_notice_statut` ; recherche plein texte FTS5 titres/auteurs (le plus
  gros gain restant pour le chat) ; formulation dates `LIKE '2026%'` →
  bornes dans le prompt.
- 7 300 exemplaires LIVRE sans statut dans Decalog = vrai trou de saisie
  (PAS des périodiques — vérifié).

## Sessions des 01-05/08 (résumé)

- **Fréquentation, DEUX SÉRIES en base** (05/08) : `frequentation`/`_horaire`
  = heures d'ouverture public seulement ; `frequentation_brute`/`_horaire_brute`
  = journée entière, TOUS passages — c'est la série comparable à l'historique
  de Marie (ses chiffres 2023-2025 = brut exactement). Le chat DEMANDE quelle
  série utiliser si la question ne précise pas. Écart brut/écran Nedap 2026 :
  l'écran LibNet exclut les lignes « Fermé » (paramétrage horaires activé
  fin janvier 2026, heures 4h-8h ≈ 40 passages/jour = équipe/ménage) —
  juillet 2026 : brut 22 615 (à annoncer), écran 21 498, ouverture 20 805.
  Marie 2020-2022 ≠ capteur (autre comptage, à éclaircir avec elle).
- **Commande jeunesse ORB finalisée** : `Commande_finale_2026-08-05.xlsx`
  + `commande_orb_finale_2026-08-05.txt/.csv` — 548 titres, 6 494,77 €
  (401 jeunesse hors mangas + 147 BD nouveautés à 1 493,55 € via
  `complement_bd_jeunesse.py`, rayon BD jeunesse PdL). Mangas RETIRÉS
  (gérés par une collègue, onglet dédié) ; adultes/rentrée littéraire
  retirés (restent en suggestion_acquisition pour une commande adulte) ;
  plafond 10 tomes/série BD ; exclusions durables via `a cataloguer*.txt`
  et `exclusions_*.txt` (EAN scannés non catalogués). Leçons scraping :
  filtres coffret/présentoir/marque-page, catégories fausses en base
  (Yo-Kai Watch en « Album », 2 mangas en « Roman jeunesse ») à corriger.
- **Désherbage** : doc ENSSIB reçu de Marie (méthode IOUPI) →
  `proposer_desherbage.py` écrit (candidats par formules âge/usage par
  rayon, Excel pour examen en rayon + délibération municipale). Premier
  run à faire/valider ; volumes à contrôler avant diffusion équipe.
- **Statuts .mrc — TRANCHÉ le 06/08** : « Prêt fonctionnel »,
  « En équipement Arcachon », « Pilon », « Non prêtable » absents AUSSI de
  l'export du 05/08 → Decalog n'exporte pas les « situations », seulement
  les statuts (A - Prêtable, A - Réserve...). Parade : fichiers de scans
  `a cataloguer*.txt` / `exclusions_*.txt` (intégrés au dédoublonnage des
  commandes). À demander à Decalog (dossier API en cours) : ajouter la
  situation des exemplaires à l'export hebdo.
- **Import hebdo du 05/08 : FAIT le 06/08** (catalogue 44 365 notices,
  EPPK, fréquentation jusqu'au 05/08 dans les 4 tables, écrans OVH, push).
  Piège corrigé dans `import_hebdomadaire.sh` : détection des fichiers
  par date de modification (`ls -t`) — l'ancien tri alphabétique prenait
  « Donnees_Comptage(3).csv » avant le fichier daté.
- Crédits API du chat rechargés (panne du 31/07 = crédits épuisés, pas un bug).

## Session du 10-13/08 (résumé)

- **Import hebdo du 10/08 : FAIT** (catalogue 44 185 notices/44 777
  exemplaires, EPPK `export-eppk 2026-08-10.xlsx`, fréquentation à jour
  au 10/08 dans les 4 tables — 1 666 jours ouverture, 1 940 jours brut).
  Écrans OVH régénérés (728 titres mosaïque, 359 diaporama jeunesse),
  push GitHub OK. Un premier lancement interrompu au Ctrl+C en pleine
  écriture SQL — sans dégât, le script détecte le ré-import (même date)
  et relance proprement de bout en bout. Toujours 7 024 notices sans EAN
  Decalog (id substitut CB:) — connu, pas un bug.
- **Tite Live — appel du 12/08 avec Giuseppe Salza** (Directeur commercial
  & éditorial des bases de données), 20 min, très positif : nos 3 demandes
  (webservice Mediabase, paniers/commande vers la Librairie Générale,
  export UNIMARC vers Decalog) confirmées **réalisables techniquement**.
  Aucun tarif communiqué à ce stade (viendra dans un second temps) ;
  points techniques encore à clarifier avec leur équipe technique.
  Tite Live commence tout juste à s'intéresser au marché des médiathèques
  et connaît bien les limites d'ORB.
- **Debrief remonté jusqu'à la COBAS** : Thomas → Marie (responsable) →
  mail de Marie le 13/08 aux décisionnaires COBAS (Pauline, Sylvie),
  avant que les choix de remplacement d'ORB ne soient arrêtés. Reprend :
  richesse multi-supports de Mediabase, l'API comme point structurant
  (fin des export/import manuels), l'ancrage Place des Libraires/Librairie
  Générale d'Arcachon, le positionnement stratégique de site pilote, et
  la piste d'une couche IA développée avec leurs équipes techniques.
  **Point nouveau non confirmé officiellement** : Tite Live développerait
  un module logiciel qui pourrait un jour remplacer Decalog (mentionné
  par Marie dans son mail — à vérifier/creuser).
- **Analyse comparative marché** (à la demande de Thomas, avant d'aller
  plus loin avec Tite Live) : Electre (Cercle de la Librairie, réseau
  Carel) fait déjà l'essentiel côté acquisition — sélection multi-supports,
  commande directe aux fournisseurs, export SIGB — mais n'est PAS un SIGB,
  c'est un module qui se branche sur l'existant, comme Mediabase. Orphée
  (C3RB, 3 500+ établissements) est un vrai SIGB avec budgets/fournisseurs/
  commandes intégrés, mais sans base bibliographique propre aussi riche
  que Mediabase/Electre (connexion à des bases externes). Conclusion :
  la combinaison « SIGB + base bibliographique riche multi-supports +
  acquisition, en un seul outil du même éditeur » n'existe encore nulle
  part — c'est l'intérêt du pari Tite Live, mais un pari plus long/risqué
  qu'un Decalog simplement doté d'une API (chantier de plusieurs années
  pour bâtir un SIGB complet : circulation, adhérents, RGPD, statistiques
  réglementaires).
- **Nouveau document** : `documentation_projet/Scenarios_comparatifs_
  circuit_document_2026-08.docx` — deux scénarios détaillés étape par
  étape sur le même exemple concret (tome manquant d'une série BD
  jeunesse à forte demande) : Scénario A (Mediabase + Place des Libraires
  + Decalog doté d'une API + MAAT) et Scénario B (même chose avec un
  hypothétique SIGB Tite Live tout intégré). Complété par des exemples de
  questions agent → MAAT interne (recherche, suggestions d'acquisition,
  désherbage, statistiques/fréquentation, rapports de gestion) et
  usager → MAAT public (disponibilité/réservation, recommandations,
  infos pratiques, suivi personnel authentifié). **Corrections métier de
  Thomas intégrées** : (1) à l'étape « constitution du panier », deux cas
  distingués — si un exemplaire du même titre est déjà au fonds, la
  notice existe déjà dans Decalog (pas de nouvelle dérivation) ; si le
  titre est inédit, la notice est dérivée depuis Mediabase à partir de
  l'ISBN ; (2) à l'étape « réception et équipement », distinction
  explicite ISBN (identifie le titre, chez l'éditeur) / code-barres
  (identifie l'exemplaire physique, attribué par le réseau, comme la
  cote et la puce RFID), plus l'étape d'encodage reliant le code-barres
  à la puce RFID, absente de la première version du document.
- **Mail de suivi envoyé à Giuseppe Salza (13/08)** : information sur la
  remontée en interne/COBAS, puis suggestion prudente (« vous y avez
  sans doute déjà réfléchi ») qu'un SIGB développé par Tite Live serait
  une offre inédite sur le marché des médiathèques, qu'une couche IA
  associée en ferait l'outil idéal du bibliothécaire, et positionnement
  discret du réseau comme interlocuteur privilégié si cette piste avance.
- **En attente** : réponse Tite Live à ce mail ; décision/retour de la
  COBAS suite au mail de Marie ; Decitre/ORB (retour attendu fin août —
  bascule `unimarc_encoding = utf8`, identifiants API démo, taux de
  correspondance EAN) ; devis PRH200 et réglage horaires Nedap ; devis
  comparatif Bibliotheca DLA InventoryWand (pas encore demandé) ; dossier
  API + rapport d'amélioration Decalog (pas encore rédigé) ; dump mémoire
  RFID complet (Android TagInfo « Full scan ») pour trancher lecteur
  générique vs PRH200.
- **RÉPONSE DECALOG SUR L'API — NÉGATIVE (14/08)**, de Demba Thiam (chef
  de projets Decalog). Point par point : (1) pas d'historique des
  exemplaires disponible via l'API ; (2) pas de statistiques — module
  séparé payant « Saikuu » ; (3) l'API donne accès aux notices par
  différents critères de recherche + services abonnés, utilisée par des
  structures qui ne prennent pas leur portail (remarque à éclaircir :
  bridage éventuel pour les clients portail comme nous, ou simple
  constat) ; (4) confirmé disponible (point non détaillé côté nous, à
  vérifier lequel de nos points originaux) ; (5) recherche multi-dates
  possible (capture d'écran fournie) ; (6) **pas de mode Push** — ni
  confirmé ni infirmé formellement mais « pas l'impression ». Conclusion
  de Decalog lui-même : « aucune API Decalog ne permettra de répondre à
  l'ensemble de vos attentes », une période d'essai serait « vaine ».
  Reste ouvert à discuter avec Cécile. **Conséquence directe** : le
  scénario A (Decalog + API) du document `Scenarios_comparatifs_
  circuit_document_2026-08.docx` est affaibli sur 3 points clés (pas de
  pré-notice en temps réel sans push, pas d'historique exemplaire pour
  le récolement/désherbage par API, stats à payer en plus) — argument
  factuel désormais utilisé pour pousser la piste scénario B (SIGB Tite
  Live) lors du rendez-vous du 19/08.
- **RDV visio Tite Live confirmé mercredi 19/08 après-midi**, avec
  Giuseppe Salza + un responsable technique. Suite à la réponse Decalog
  ci-dessus, Thomas penche pour la solution tout intégrée (scénario B).
  Trame de réunion créée et mise à jour : `documentation_projet/
  Trame_visio_TiteLive_2026-08.docx` — fil rouge « expérience
  utilisateur » façon Apple (simplicité maximale agents + public, IA
  capable de répondre à toute question), encart sur la réponse Decalog
  à utiliser dès le début comme argument factuel, question sur les
  ambitions SIGB de Tite Live remontée en position 2 (plus en question
  de clôture), questions détaillées par thème (webservice, paniers/
  commandes, export UNIMARC, conditions), réflexes de fin de réunion
  (pas de négociation tarifaire en séance, repartir avec contact
  technique + date + accès test si possible).
- **Token GitHub « Claude MAAT » régénéré (14/08)**, sans usage identifié
  (ni connecteur Claude, ni `git push` du Mac mini qui passe par le
  Trousseau macOS) — à surveiller quelques jours puis supprimer sur
  GitHub si rien ne casse. Fichiers `Commande 4-2026.not` et
  `Commande 4-2026 (utf8).not` retirés du dépôt public (`git rm
  --cached`, commit `2890cb9`) suite à leur commit accidentel lors de
  l'import du 10/08 ; `*.not` ajouté au `.gitignore`. Fichiers toujours
  présents en local, juste plus sur GitHub.

## Consommation Claude (contexte du changement de conversation)

Depuis le 20/07/2026, Fable 5 n'est plus inclus dans le plan Pro (fin de
promo) : il tourne en crédits pay-as-you-go — d'où les rechargements de
Thomas. Total et historique : claude.ai → Réglages → Usage. Conseils
appliqués : nouvelles conversations par sujet, Sonnet/Opus pour le suivi
courant, Fable 5 pour la conception. Thomas compare avec le plan Max.

## Style de travail avec Thomas

Réponses concises, en français. « fait » = il a exécuté ; Claude lit alors
les fichiers de sortie dans le dossier. Toujours : simulation avant
application, rien qui casse l'existant (« si c'est pour dégrader quelque
chose qui fonctionne, mieux vaut ne pas le faire »), décisions métier
= Thomas (bibliothécaire), vérification finale par une question test au
chat. Jamais deux scrapers en même temps sur Place des Libraires.
