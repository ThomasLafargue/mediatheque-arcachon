#!/usr/bin/env python3
"""
nettoyer_suggestions_perimees.py — Remet la liste de suggestions à zéro pour
repartir sur une base propre.

Contexte (2026-07-25) : les suggestions accumulées avant aujourd'hui l'ont été
avec un code encore imparfait -- sans ISBN pour la plupart, sans classement
(catégorie / public / genre), et incluant des sélections périmées (« Rentrée
littéraire 2025 » alors qu'on est en 2026). Plutôt que de rafistoler, on
efface ces suggestions automatiques et on relance les veilles : tout sera
alors renseigné et trié correctement dès l'enregistrement.

CE QUI EST SUPPRIMÉ : uniquement les suggestions produites par les veilles
(demandeur = « Veille automatique ») et créées AVANT aujourd'hui.

CE QUI EST CONSERVÉ, dans tous les cas :
  - les suggestions saisies par un agent (demandeur = un prénom) ;
  - celles déjà traitées (statut « à commander », « acquise », « écartée »),
    car elles portent une décision humaine -- et les « écartée » empêchent un
    titre refusé de revenir.

APERÇU PAR DÉFAUT : rien n'est supprimé sans --confirmer.

Usage :
    python3 nettoyer_suggestions_perimees.py              (aperçu seul)
    python3 nettoyer_suggestions_perimees.py --confirmer  (suppression)
"""

import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

DEMANDEUR_VEILLE = "Veille automatique"


def _connexion_ecriture():
    jeton = os.environ.get("TURSO_AUTH_TOKEN_ECRITURE")
    if not jeton or not db.MODE_EN_LIGNE:
        return None
    return db.connect_avec_jeton(db.TURSO_URL, jeton)


def main():
    confirmer = "--confirmer" in sys.argv
    aujourdhui = datetime.date.today().isoformat()

    conn = _connexion_ecriture()
    if conn is None:
        print("TURSO_AUTH_TOKEN_ECRITURE absent ou base locale -- rien à faire.")
        return

    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM suggestion_acquisition").fetchall()[0][0]

        # Toutes les suggestions automatiques encore « à étudier », quelle que
        # soit leur date : celles d'aujourd'hui ont elles aussi été produites
        # avant les corrections (sélections périmées, classement absent). On
        # repart réellement de zéro, la veille les régénérera proprement.
        a_supprimer = conn.execute(
            "SELECT id, titre, source, date_ajout FROM suggestion_acquisition "
            "WHERE demandeur = ? AND statut = 'à étudier' "
            "ORDER BY date_ajout",
            (DEMANDEUR_VEILLE,),
        ).fetchall()

        conserves = total - len(a_supprimer)

        if not a_supprimer:
            print("Aucune suggestion automatique en attente. Rien à faire.")
            return

        print(f"Remise à zéro complète des suggestions automatiques "
              f"(au {aujourdhui})\n")
        print(f"  À SUPPRIMER : {len(a_supprimer)} suggestion(s) de la veille")
        print(f"  CONSERVÉES  : {conserves} (saisies par un agent, ou déjà décidées)\n")

        # récapitulatif par source, plus lisible que 200 lignes
        par_source = {}
        for _, _, source, _ in a_supprimer:
            par_source[source or "(sans source)"] = par_source.get(source or "(sans source)", 0) + 1
        print("  Détail par source :")
        for source, n in sorted(par_source.items(), key=lambda x: -x[1]):
            print(f"    {n:4}  {source[:60]}")

        print("\n  Aperçu (10 premières) :")
        for i, t, source, d in a_supprimer[:10]:
            print(f"    #{i:<5} {str(t)[:44]:44} {str(d)[:10]}")

        if not confirmer:
            print("\nAPERÇU seulement — rien n'a été supprimé.")
            print("Pour supprimer réellement :")
            print("    python3 nettoyer_suggestions_perimees.py --confirmer")
            print("\nPuis relancer les veilles pour repartir proprement :")
            print("    bash veille_hebdomadaire.sh")
            return

        for i, _, _, _ in a_supprimer:
            conn.execute("DELETE FROM suggestion_acquisition WHERE id = ?", (i,))
        conn.commit()
        print(f"\n✓ {len(a_supprimer)} suggestion(s) supprimée(s). "
              f"{conserves} conservée(s).")
        print("\nRelance maintenant les veilles pour une liste propre :")
        print("    bash veille_hebdomadaire.sh")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
