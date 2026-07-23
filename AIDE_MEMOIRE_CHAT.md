# Aide-mémoire — Assistant conversationnel du fonds

Médiathèque d'Arcachon · réseau COBAS

Ce mémo liste ce que le chat sait faire et des exemples de questions qui
marchent. Il interroge la base à jour (issue de Decalog + notre
enrichissement) en langage naturel : pas besoin de connaître le vocabulaire
exact, il gère les synonymes (« ados » = Ado (12+)/Adolescent, « BD jeunesse »,
« manga », etc.).

---

## 1. Interroger le fonds

- « Combien de mangas jeunesse avons-nous ? »
- « Liste les romans ado de science-fiction disponibles. »
- « Quels albums de moins de 3 ans avons-nous en plusieurs exemplaires ? »
- « Montre les documentaires jeunesse sur les dinosaures. »
- « Quelles BD jeunesse avons-nous de l'autrice Pénélope Bagieu ? »
- « Combien d'exemplaires du tome 1 de One Piece, et combien sont en prêt ? »

## 2. Séries et tomes

- « La série Mortelle Adèle est-elle complète chez nous ? »
- « Quelles séries de manga jeunesse ont des tomes manquants ? »
- « Jusqu'à quel tome avons-nous Les Légendaires ? »

  (Fiable une fois le backfill série/tome terminé. Le chat distingue un tome
  *absent du fonds* d'un tome *actuellement en prêt* — il ne signale jamais un
  tome emprunté comme manquant.)

## 3. Prêts, rotation, usage

- « Quels sont les 20 titres jeunesse les plus empruntés ? »
- « Quels genres tournent le mieux (prêts par titre) ? »
- « Quels titres récents (2024+) n'ont jamais été empruntés ? »
- « Quels exemplaires uniques sont très empruntés (à doubler) ? »
- « Quel a été notre créneau horaire le plus fréquenté mardi dernier ? »

## 4. Suggestions d'acquisition (alimentées par la veille automatique)

Une veille tourne chaque semaine (nouveautés BnF, critiques Ricochet dont BD et
manga) + les prix littéraires jeunesse (Sorcières, Incorruptibles, rafraîchis
2×/an). Elle pré-remplit une liste de titres **absents du fonds**.

- « Montre-moi les suggestions d'acquisition de la veille automatique. »
- « Quels titres primés (Sorcières, Incorruptibles) nous manquent ? »
- « Propose-moi des acquisitions BD jeunesse selon nos besoins réels. »
- « Trouve 15 nouveautés albums pour un budget de 200 €. »

Décider du sort d'un titre (sans jamais effacer l'historique) :

- « Commande *Les Adelphides* et *Finding Phoebe*. » → statut « à commander »
- « On a reçu *Loupiotes*. » → statut « acquise »
- « Écarte *Mon gros cahier de coloriage*. » → statut « écartée » (ne
  réapparaîtra plus dans la veille)

## 5. Désherbage (retrait du fonds)

- « Quels documentaires n'ont pas été empruntés depuis 2015 ? »
- « Note *[titre]* comme à désherber pour moi. »
- « Enregistre le retrait effectif de *[titre]*. » (conserve les données de
  prêt avant que Decalog supprime la notice)

## 6. Mise en avant / pépites

- « Trouve des pépites peu empruntées mais primées à mettre en avant. »
- « Ajoute *[titre]* à ma liste de coups de cœur. »

## 7. Fiches Decalog mal renseignées (à corriger à la main dans Decalog)

- « Quelles fiches sont mal renseignées dans Decalog ? »
- « Quels titres ont une série ou un tome que nous avons déduit mais qui
  manque encore dans Decalog ? »
- « Quels documents n'ont pas d'EAN (ISBN) dans Decalog ? » (identifiants CB:)

  (Se remplit au fil du backfill — complet et fiable une fois celui-ci fini.)

## 8. Exports et rapports

- « Exporte cette liste en Excel. » (n'importe quelle liste ci-dessus)
- « Fais-moi le bilan hebdomadaire du fonds. » (totaux, taux d'enrichissement,
  nouveautés, top séries, séries incomplètes, points d'attention Decalog)
- « Exporte le fonds jeunesse complet. »

## 9. Analyse stratégique d'acquisition

- « Sur quoi devrions-nous investir en priorité en jeunesse ? »

  Croise les signaux internes (genres à forte rotation, doublons nécessaires,
  séries incomplètes, auteurs très empruntés, public sous-servi) avec le profil
  démographique d'Arcachon, puis complète par une recherche web.

---

## Ce que le chat NE fait pas / limites à connaître

- Il travaille en **lecture seule** sur le catalogue : il ne modifie jamais une
  notice ni Decalog. Il n'écrit que dans ses propres listes (suggestions,
  désherbage, coups de cœur).
- Il ne connaît que **le fonds réel d'Arcachon** : il n'invente jamais un
  titre, un prix ou un chiffre de prêt — tout vient d'une requête ou d'une
  recherche web réelle.
- Il reflète l'**état du catalogue**, pas la présence physique en rayon (voir la
  question du récolement RFID — un document volé mais toujours listé « prêtable »
  dans Decalog apparaîtra comme présent).
- La disponibilité temps réel (réservations, transits) dépend de Decalog ; sans
  API Decalog/ORB branchée, elle reflète le dernier export, pas la minute.
