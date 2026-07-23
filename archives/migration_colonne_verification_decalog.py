#!/usr/bin/env python3
"""
migration_colonne_verification_decalog.py — Ajoute la colonne
notice.champs_a_verifier_decalog, pour que le chat puisse dire "ce champ
est correct dans NOTRE base mais absent/faux dans Decalog, va le corriger
là-bas".

Contexte : on ne réécrit jamais les notices Decalog elles-mêmes. Quand
notre moteur d'enrichissement (BnF + 11 sites) déduit une valeur que
Decalog n'avait pas fournie (ex: serie/tome), cette valeur est juste sur
NOTRE base -- Decalog reste, lui, mal renseigné tant que quelqu'un n'y
corrige pas manuellement. Cette colonne liste les champs concernés
(ex: "serie,tome") pour qu'on puisse les retrouver et les signaler.

Idempotent : peut être relancé sans risque (ignore l'erreur si la colonne
existe déjà).

Usage :
    python3 migration_colonne_verification_decalog.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def main():
    jeton = os.environ.get('TURSO_AUTH_TOKEN_ECRITURE')
    if not jeton:
        print("✗ TURSO_AUTH_TOKEN_ECRITURE absent de .env -- impossible d'écrire.")
        sys.exit(1)

    conn = db.connect_avec_jeton(db.TURSO_URL, jeton)
    try:
        conn.execute("ALTER TABLE notice ADD COLUMN champs_a_verifier_decalog TEXT")
        conn.commit()
        print("✓ Colonne notice.champs_a_verifier_decalog ajoutée.")
    except Exception as e:
        if 'duplicate column' in str(e).lower() or 'already exists' in str(e).lower():
            print("(colonne déjà présente -- rien à faire)")
        else:
            raise

    # La vue doit être recréée pour exposer la nouvelle colonne (SQLite/Turso
    # ne permet pas d'ajouter une colonne à une VIEW existante).
    try:
        conn.execute("DROP VIEW IF EXISTS vue_inventaire")
        conn.execute("""
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
            FROM notice n LEFT JOIN exemplaire e ON e.identifiant = n.identifiant
        """)
        conn.commit()
        print("✓ Vue vue_inventaire recréée avec champs_a_verifier_decalog.")
    finally:
        conn.close()


if __name__ == '__main__':
    main()
