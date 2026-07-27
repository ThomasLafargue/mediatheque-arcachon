#!/usr/bin/env python3
"""
optimiser_base.py — Ajoute les index qui manquent à la base, d'après l'usage
réel du chat mesuré par auditer_base.py le 2026-07-27.

POURQUOI : les six requêtes types de l'audit faisaient toutes un BALAYAGE
COMPLET des 44 324 notices. D'où les 44 millions de lignes lues affichées par
Turso pour une base qui n'en contient que 44 000. Un index transforme ce
balayage en accès direct.

CE QUE FAIT UN INDEX — et ce qu'il ne fait pas :
  - il N'EFFACE RIEN et NE MODIFIE AUCUNE DONNÉE ;
  - il se supprime d'une ligne (DROP INDEX) sans aucune perte ;
  - il coûte un peu d'espace et ralentit très légèrement les écritures
    (soit, ici, l'import hebdomadaire — quelques secondes).
C'est l'optimisation la plus sûre qui existe : on ajoute, on ne retire pas.

CHOIX DES INDEX — fondés sur le comptage des requêtes réellement posées :
    categorie 185x, serie 130x, type_document 103x, public_vise 100x,
    tome 22x, date_publication 21x
Un index composite (a, b) sert aussi les requêtes qui ne filtrent que sur `a`
(règle du préfixe gauche) : d'où (serie, tome) plutôt que deux index séparés.

NON TRAITÉ ICI : `titre` et `createurs`, pourtant les plus filtrés (324x).
Le chat les interroge en LIKE '%mot%', et AUCUN index classique ne peut
accélérer une recherche qui commence par un joker. Il faudrait une table de
recherche plein texte (FTS5) — plus puissant, mais c'est un objet en plus à
tenir à jour à chaque import. À décider séparément, pas en même temps que ça.

Usage :
    python3 optimiser_base.py              -> simulation, n'écrit rien
    python3 optimiser_base.py --appliquer  -> crée réellement les index
"""
import sys
import time

sys.path.insert(0, ".")
import db  # noqa: E402

INDEX = [
    # (nom, table, colonnes, justification)
    ("idx_notice_serie_tome", "notice", "serie, tome",
     "« quels tomes de Lucky Luke nous manquent » — la question phare. "
     "Sert aussi toute recherche sur la seule série (préfixe gauche)."),
    ("idx_notice_categorie_public", "notice", "categorie, public_vise",
     "« les BD jeunesse », « les romans ado » — les deux colonnes les plus "
     "filtrées, presque toujours ensemble."),
    ("idx_notice_public", "notice", "public_vise",
     "public visé seul, sans catégorie (non couvert par le composite)."),
    ("idx_notice_date_publication", "notice", "date_publication",
     "« les nouveautés de l'année », les acquisitions récentes."),
    ("idx_notice_enrichissement", "notice", "date_enrichissement",
     "requête du service d'enrichissement, rejouée toutes les quelques "
     "minutes : c'est probablement le premier consommateur de lignes lues."),
    ("idx_notice_prets", "notice", "nb_prets_total DESC",
     "« les documents les plus empruntés » — évite en prime le tri "
     "temporaire (USE TEMP B-TREE) relevé par l'audit."),
]

# Index existant devenu inutile : statut_publication est rempli à 0 %.
# On ne le supprime PAS automatiquement — c'est une modification de schéma,
# elle mérite une décision explicite. La commande est indiquée en fin de
# rapport si l'on veut la passer à la main.
INDEX_INUTILE = ("idx_notice_statut", "statut_publication rempli à 0 %")


def main():
    appliquer = "--appliquer" in sys.argv
    conn = db.connect()

    existants = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}

    print("=" * 70)
    print("OPTIMISATION DE LA BASE — " + time.strftime("%Y-%m-%d %H:%M"))
    print("MODE : " + ("APPLICATION RÉELLE" if appliquer else
                       "SIMULATION (rien ne sera écrit)"))
    print("=" * 70)

    faits = 0
    for nom, table, colonnes, pourquoi in INDEX:
        print(f"\n{nom}")
        print(f"  sur {table} ({colonnes})")
        print(f"  → {pourquoi}")
        if nom in existants:
            print("  déjà présent, rien à faire.")
            continue
        if not appliquer:
            print("  [simulation] serait créé.")
            continue
        t0 = time.time()
        try:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {nom} ON {table} ({colonnes})")
            conn.commit()
            print(f"  CRÉÉ en {time.time() - t0:.1f}s")
            faits += 1
        except Exception as e:
            print(f"  ÉCHEC : {str(e)[:120]}")

    # Vérification : les balayages ont-ils disparu ?
    print("\n" + "=" * 70)
    print("VÉRIFICATION — plans d'exécution après l'opération")
    print("=" * 70)
    controles = [
        ("Tomes d'une série",
         "SELECT titre, tome FROM notice WHERE serie = 'Lucky Luke'"),
        ("BD jeunesse",
         "SELECT COUNT(*) FROM notice WHERE categorie = 'Bande dessinée' "
         "AND public_vise = 'Jeune'"),
        ("Nouveautés",
         "SELECT titre FROM notice WHERE date_publication LIKE '2026%'"),
        ("Notices à enrichir",
         "SELECT identifiant FROM notice WHERE date_enrichissement IS NULL"),
        ("Plus empruntés",
         "SELECT titre FROM notice ORDER BY nb_prets_total DESC LIMIT 20"),
    ]
    for libelle, sql in controles:
        print(f"\n  {libelle}")
        try:
            for r in conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall():
                d = str(r[-1])
                if d.startswith("SCAN") and "USING" in d and "INDEX" in d:
                    # parcours ORDONNÉ de l'index, pas de la table : avec un
                    # LIMIT, seules les premières entrées sont lues. C'est bon.
                    verdict = "   OK (parcours d'index ordonné)"
                elif d.startswith("SCAN"):
                    verdict = "   <<< BALAYAGE COMPLET"
                elif "TEMP B-TREE" in d:
                    # tri en mémoire faute d'index utilisable : pas un balayage,
                    # mais un coût supplémentaire qu'un index fait disparaître
                    verdict = "   <<< TRI TEMPORAIRE"
                else:
                    verdict = "   OK"
                print(f"      {d}{verdict}")
        except Exception as e:
            print(f"      erreur : {str(e)[:80]}")

    conn.close()
    print("\n" + "=" * 70)
    if appliquer:
        print(f"{faits} index créé(s). Aucune donnée modifiée.")
        print("\nPour annuler un index :  DROP INDEX <nom>;")
    else:
        print("Simulation terminée. Rien n'a été écrit.")
        print("Pour appliquer :  python3 optimiser_base.py --appliquer")
    print(f"\nÀ décider séparément — index devenu inutile : {INDEX_INUTILE[0]} "
          f"({INDEX_INUTILE[1]}).")


if __name__ == "__main__":
    main()
