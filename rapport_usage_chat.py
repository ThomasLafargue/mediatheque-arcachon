#!/usr/bin/env python3
"""
rapport_usage_chat.py — Synthèse de l'usage réel du chat agents, à partir de
la table journal_requetes (déjà alimentée par app_conversationnel.py à
chaque question posée, aucune modification de l'outil de chat nécessaire).

Objectif (2026-07-23) : donner une vue rapide et fiable de la santé de
l'outil -- volume, taux d'erreur, usage des fonctionnalités -- sans jamais
toucher au chat lui-même (script séparé, lecture seule, zéro risque de
régression sur l'outil que les agents utilisent au quotidien).

Usage :
    python3 rapport_usage_chat.py            (30 derniers jours)
    python3 rapport_usage_chat.py 7           (7 derniers jours)
"""

import sys
import db


def _pourcentage(partie, total):
    return round(partie / total * 100, 1) if total else 0.0


def main():
    jours = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    conn = db.connect()
    try:
        lignes = conn.execute(
            """
            SELECT date_requete, question, sql_executees, nb_recherches_web,
                   a_genere_export, a_modifie_suggestions, erreur
            FROM journal_requetes
            WHERE date_requete >= datetime('now', ?)
            ORDER BY date_requete
            """,
            (f"-{jours} days",),
        ).fetchall()
    except Exception as e:
        print(f"Impossible de lire journal_requetes : {type(e).__name__}: {e}")
        print("(La table n'existe peut-être pas encore -- elle est créée au premier "
              "appel du chat qui écrit dedans, voir journaliser_requete() dans "
              "app_conversationnel.py.)")
        return
    finally:
        conn.close()

    print(f"═══ Usage du chat agents — {jours} derniers jours ═══\n")

    total = len(lignes)
    if not total:
        print("Aucune question posée sur cette période.")
        return

    erreurs = [l for l in lignes if l[6]]
    exports = [l for l in lignes if l[4]]
    modifs = [l for l in lignes if l[5]]
    total_recherches_web = sum(l[3] or 0 for l in lignes)

    print(f"Total de questions posées : {total}")
    print(f"Taux d'erreur : {len(erreurs)} ({_pourcentage(len(erreurs), total)}%)")
    print(f"Exports Excel générés : {len(exports)} ({_pourcentage(len(exports), total)}%)")
    print(f"Suggestions/désherbage ajoutés ou supprimés : {len(modifs)} ({_pourcentage(len(modifs), total)}%)")
    print(f"Recherches web déclenchées : {total_recherches_web} "
          f"(moyenne {round(total_recherches_web / total, 2)} par question)")

    # Volume par jour, pour repérer les pics/creux d'usage
    par_jour = {}
    for l in lignes:
        jour = (l[0] or "")[:10]
        par_jour[jour] = par_jour.get(jour, 0) + 1
    print("\n── Volume par jour ──")
    for jour in sorted(par_jour):
        print(f"  {jour} : {'█' * par_jour[jour]} ({par_jour[jour]})")

    # Dernières erreurs -- ce qui mérite un vrai coup d'œil en priorité
    if erreurs:
        print(f"\n── Dernières erreurs (max 10, sur {len(erreurs)}) ──")
        for l in erreurs[-10:]:
            date_requete, question, sql_executees, nb_web, a_export, a_modif, erreur = l
            print(f"\n  [{date_requete}] {question[:120]}")
            print(f"    → {erreur}")
    else:
        print("\nAucune erreur sur la période. ✓")


if __name__ == "__main__":
    main()
