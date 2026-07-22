-- ============================================================================
-- SCHÉMA DE RÉFÉRENCE — inventaire_isbn, Médiathèque d'Arcachon
-- Vérifié le 28 juin 2026 par extraction directe depuis inventaire.db
-- (sqlite_master) -- réécriture propre du schéma réel, pas une reconstruction
-- théorique : recrée une base neuve strictement équivalente à la production.
-- ============================================================================

PRAGMA foreign_keys = ON;

CREATE TABLE type_document (
    code            TEXT PRIMARY KEY,
    libelle         TEXT NOT NULL,
    actif           INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE notice (
    identifiant             TEXT PRIMARY KEY,
    type_document           TEXT NOT NULL DEFAULT 'LIVRE' REFERENCES type_document(code),
    titre                   TEXT,
    serie                   TEXT,
    tome                    TEXT,
    collection              TEXT,
    createurs               TEXT,
    createurs_secondaires   TEXT,
    traducteur              TEXT,
    editeur                 TEXT,
    date_publication        TEXT,
    categorie               TEXT,
    genre                   TEXT,
    public_vise             TEXT,
    age_recommande          TEXT,
    pegi                    TEXT,
    statut_publication      TEXT,
    score_confiance         REAL,
    date_enrichissement     TEXT,
    nb_sources_consultees   INTEGER,
    resume                  TEXT,
    image_url               TEXT,
    dewey                   TEXT,
    dewey_libelle           TEXT,
    mots_cles               TEXT,
    description_physique    TEXT,
    date_creation           TEXT,
    nb_prets_total          INTEGER,
    nb_prets_annee_courante INTEGER,
    nb_prets_n1             INTEGER,
    nb_prets_n2             INTEGER,
    nb_prets_n3             INTEGER,
    nb_prets_fonctionnels   INTEGER,
    date_dernier_pret       TEXT,
    date_maj_prets          TEXT,
    champs_a_verifier_decalog TEXT
);

CREATE INDEX idx_notice_type ON notice(type_document);
CREATE INDEX idx_notice_statut ON notice(statut_publication);

CREATE TABLE exemplaire (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant             TEXT NOT NULL REFERENCES notice(identifiant),
    cote                    TEXT,
    code_barre_exemplaire   TEXT,
    date_acquisition        TEXT,
    statut                  TEXT,
    site                    TEXT,
    public_vise             TEXT,
    support                 TEXT,
    prix                    REAL,
    nb_prets_total          INTEGER,
    annee_dernier_pret      TEXT,
    date_maj                TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX idx_exemplaire_code_barre_unique ON exemplaire(code_barre_exemplaire);
CREATE INDEX idx_exemplaire_identifiant ON exemplaire(identifiant);
CREATE INDEX idx_exemplaire_cote ON exemplaire(cote);

CREATE TABLE frequentation (
    date                    TEXT PRIMARY KEY,
    nb_entrees              INTEGER
);

CREATE TABLE flux_historique (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant             TEXT NOT NULL REFERENCES notice(identifiant),
    date_export             TEXT NOT NULL,
    nb_prets_total          INTEGER,
    UNIQUE(identifiant, date_export)
);

CREATE INDEX idx_flux_historique_identifiant ON flux_historique(identifiant);

CREATE TABLE flux_mensuel (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant             TEXT NOT NULL REFERENCES notice(identifiant),
    mois_export             TEXT NOT NULL,
    nb_prets                INTEGER,
    date_dernier_pret       TEXT,
    date_import             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(identifiant, mois_export)
);

CREATE INDEX idx_flux_identifiant ON flux_mensuel(identifiant);
CREATE INDEX idx_flux_mois ON flux_mensuel(mois_export);

CREATE TABLE commande (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    identifiant             TEXT NOT NULL REFERENCES notice(identifiant),
    date_commande           TEXT NOT NULL,
    fournisseur             TEXT,
    quantite_commandee      INTEGER NOT NULL DEFAULT 1,
    prix_unitaire           REAL,
    statut                  TEXT NOT NULL DEFAULT 'commandé'
                            CHECK (statut IN ('commandé', 'livré partiel', 'livré complet', 'annulé'))
);

CREATE INDEX idx_commande_identifiant ON commande(identifiant);
CREATE INDEX idx_commande_statut ON commande(statut);

CREATE TABLE livraison (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    commande_id             INTEGER NOT NULL REFERENCES commande(id),
    date_livraison          TEXT NOT NULL,
    quantite_livree         INTEGER NOT NULL,
    reference_bon           TEXT
);

CREATE INDEX idx_livraison_commande ON livraison(commande_id);

CREATE TABLE schema_info (
    version         INTEGER PRIMARY KEY,
    date_application TEXT NOT NULL DEFAULT (datetime('now')),
    commentaire     TEXT
);

-- Une ligne par exemplaire réel d'Arcachon. C'est cette vue que l'outil
-- conversationnel interroge.
CREATE VIEW vue_inventaire AS
SELECT
    n.identifiant AS isbn, n.titre AS titre, n.serie AS serie, n.tome AS tome,
    n.collection AS collection, n.type_document AS type, n.categorie AS categorie,
    n.genre AS genre, n.public_vise AS public, n.age_recommande AS age_recommande,
    n.pegi AS pegi, n.createurs AS auteur, n.createurs_secondaires AS illustrateur,
    n.traducteur AS traducteur, n.editeur AS editeur, n.date_publication AS annee,
    n.dewey AS dewey, n.dewey_libelle AS dewey_libelle, n.mots_cles AS mots_cles,
    n.description_physique AS description_physique,
    n.champs_a_verifier_decalog AS champs_a_verifier_decalog,
    e.code_barre_exemplaire AS code_barres, e.cote AS cote, e.statut AS statut_exemplaire,
    e.prix AS prix, n.nb_prets_total AS nb_prets_titre_reseau,
    e.nb_prets_total AS nb_prets_cet_exemplaire,
    n.date_dernier_pret AS dernier_pret_titre_reseau,
    e.annee_dernier_pret AS dernier_pret_cet_exemplaire, n.resume AS resume
FROM notice n LEFT JOIN exemplaire e ON e.identifiant = n.identifiant;

CREATE VIEW v_rapprochement_commande AS
SELECT
    c.id AS commande_id, c.identifiant, n.titre, c.date_commande, c.fournisseur,
    c.quantite_commandee, COALESCE(SUM(l.quantite_livree), 0) AS quantite_livree_totale,
    c.quantite_commandee - COALESCE(SUM(l.quantite_livree), 0) AS ecart, c.statut
FROM commande c
LEFT JOIN livraison l ON l.commande_id = c.id
LEFT JOIN notice n ON n.identifiant = c.identifiant
GROUP BY c.id;
