#!/usr/bin/env python3
"""
_diag_frequentation.py — Diagnostic des tables de fréquentation + relecture
des dernières questions « fréquentation » posées au chat (journal_requetes).
STRICTEMENT EN LECTURE.

Usage :  python3 _diag_frequentation.py
"""
import os
import sys

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
import db  # noqa: E402


def main():
    conn = db.connect()
    cur = conn.cursor()

    print("── FREQUENTATION (journalier) ──────────────────────────")
    n, mini, maxi = cur.execute(
        "SELECT COUNT(*), MIN(date), MAX(date) FROM frequentation").fetchone()
    print(f"{n} jours, du {mini} au {maxi}")

    print("\nFormats de date rencontrés (motif, nb) :")
    for motif, nb in cur.execute("""
        SELECT CASE
            WHEN date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN 'AAAA-MM-JJ'
            WHEN date GLOB '[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]' THEN 'JJ/MM/AAAA'
            ELSE 'AUTRE : ' || date END AS motif, COUNT(*)
        FROM frequentation GROUP BY motif ORDER BY 2 DESC LIMIT 10""").fetchall():
        print(f"  {nb:>6}  {motif}")

    print("\nJours par année :")
    for annee, nb, total in cur.execute("""
        SELECT SUBSTR(date,1,4), COUNT(*), SUM(nb_entrees)
        FROM frequentation GROUP BY 1 ORDER BY 1""").fetchall():
        print(f"  {annee} : {nb:>4} jours, {total or 0:>8} entrées")

    print("\nValeurs suspectes :")
    for lib, sql in [
        ("nb_entrees NULL ou <= 0",
         "SELECT COUNT(*) FROM frequentation WHERE nb_entrees IS NULL OR nb_entrees <= 0"),
        ("doublons de date",
         "SELECT COUNT(*) FROM (SELECT date FROM frequentation GROUP BY date HAVING COUNT(*) > 1)"),
        ("jours > 3000 entrées (aberrants ?)",
         "SELECT COUNT(*) FROM frequentation WHERE nb_entrees > 3000"),
    ]:
        print(f"  {cur.execute(sql).fetchone()[0]:>6}  {lib}")

    print("\nTop 5 des journées les plus fortes :")
    for d, e in cur.execute(
            "SELECT date, nb_entrees FROM frequentation "
            "ORDER BY nb_entrees DESC LIMIT 5").fetchall():
        print(f"  {d} : {e}")

    print("\n── COHÉRENCE journalier <-> horaire ────────────────────")
    nh, minh, maxh = cur.execute(
        "SELECT COUNT(DISTINCT date), MIN(date), MAX(date) "
        "FROM frequentation_horaire").fetchone()
    print(f"horaire : {nh} jours, du {minh} au {maxh}")
    seul_j = cur.execute("""
        SELECT COUNT(*) FROM frequentation f WHERE NOT EXISTS
        (SELECT 1 FROM frequentation_horaire h WHERE h.date = f.date)""").fetchone()[0]
    seul_h = cur.execute("""
        SELECT COUNT(DISTINCT date) FROM frequentation_horaire h WHERE NOT EXISTS
        (SELECT 1 FROM frequentation f WHERE f.date = h.date)""").fetchone()[0]
    print(f"jours au journalier sans détail horaire : {seul_j}")
    print(f"jours au détail horaire absents du journalier : {seul_h}")
    ecarts = cur.execute("""
        SELECT COUNT(*) FROM (
            SELECT h.date FROM frequentation_horaire h
            JOIN frequentation f ON f.date = h.date
            GROUP BY h.date HAVING SUM(h.nb_entrees) != f.nb_entrees)""").fetchone()[0]
    print(f"jours où somme(horaire) != total journalier : {ecarts}")
    if ecarts:
        print("  exemples :")
        for d, sh, tj in cur.execute("""
            SELECT h.date, SUM(h.nb_entrees), f.nb_entrees
            FROM frequentation_horaire h JOIN frequentation f ON f.date = h.date
            GROUP BY h.date HAVING SUM(h.nb_entrees) != f.nb_entrees
            ORDER BY ABS(SUM(h.nb_entrees) - f.nb_entrees) DESC LIMIT 5""").fetchall():
            print(f"    {d} : horaire {sh} vs journalier {tj}")

    print("\nTranches horaires hors ouverture (avant 9h / après 19h) :")
    for h, nb, tot in cur.execute("""
        SELECT heure, COUNT(*), SUM(nb_entrees) FROM frequentation_horaire
        WHERE heure < '09:00' OR heure >= '19:00'
        GROUP BY heure ORDER BY heure""").fetchall():
        print(f"  {h} : {nb} jours, {tot} entrées")

    print("\nEntrées un dimanche (fermé toute l'année) :")
    for d, e in cur.execute("""
        SELECT date, nb_entrees FROM frequentation
        WHERE CAST(STRFTIME('%w', date) AS INTEGER) = 0
        ORDER BY nb_entrees DESC LIMIT 5""").fetchall():
        print(f"  {d} : {e}")

    print("\n── DERNIÈRES QUESTIONS « FRÉQUENTATION » AU CHAT ───────")
    for dr, q, sql, err in cur.execute("""
        SELECT date_requete, question, sql_executees, erreur
        FROM journal_requetes
        WHERE question LIKE '%fréquentation%' OR question LIKE '%frequentation%'
           OR question LIKE '%entrées%' OR question LIKE '%visiteurs%'
           OR sql_executees LIKE '%frequentation%'
        ORDER BY date_requete DESC LIMIT 5""").fetchall():
        print(f"\n[{dr}] {q}")
        print(f"  SQL : {(sql or '')[:600]}")
        if err:
            print(f"  ERREUR : {err}")

    conn.close()


if __name__ == "__main__":
    main()
