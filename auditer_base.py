#!/usr/bin/env python3
"""
auditer_base.py — Audit de la base en ligne, en vue de la simplifier et
d'accélérer le chat.

STRICTEMENT EN LECTURE. Ne crée rien, ne supprime rien, ne modifie rien.
Il produit un CONSTAT ; les décisions se prennent ensuite, à deux.

CE QU'IL CHERCHE
  1. Tables vides ou quasi vides — du bruit que le chat doit ignorer à chaque
     question, et autant de schéma à lui faire lire pour rien.
  2. Colonnes jamais remplies — même problème, à l'échelle de la colonne.
  3. Index manquants — la cause probable des 44 millions de lignes lues pour
     une base de 44 000 notices : sans index, chaque question balaie tout.
  4. Ce que le chat demande VRAIMENT (table journal_requetes) — pour indexer
     l'usage réel plutôt que nos suppositions.
  5. Le plan d'exécution des requêtes types (EXPLAIN QUERY PLAN) : « SCAN »
     signale un balayage complet, « SEARCH ... USING INDEX » un accès direct.

Usage :  python3 auditer_base.py > audit_base.txt 2>&1
"""
import sys
import time

sys.path.insert(0, ".")
import db  # noqa: E402

REQUETES_TYPES = [
    ("Tomes manquants d'une série",
     "SELECT titre, tome FROM notice WHERE serie = 'Lucky Luke'"),
    ("Fonds jeunesse par catégorie",
     "SELECT COUNT(*) FROM notice WHERE public_vise = 'Jeunesse' "
     "AND categorie = 'Bande dessinée'"),
    ("Nouveautés de l'année",
     "SELECT titre FROM notice WHERE date_publication LIKE '2026%'"),
    ("Notices à enrichir",
     "SELECT identifiant FROM notice WHERE date_enrichissement IS NULL"),
    ("Documents les plus empruntés",
     "SELECT titre, nb_prets_total FROM notice ORDER BY nb_prets_total DESC "
     "LIMIT 20"),
    ("Jointure notice + exemplaire par cote",
     "SELECT n.titre, e.cote FROM notice n JOIN exemplaire e "
     "ON e.identifiant = n.identifiant WHERE e.cote LIKE 'BD%'"),
]


def q(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def main():
    conn = db.connect()
    print("=" * 72)
    print("AUDIT DE LA BASE — " + time.strftime("%Y-%m-%d %H:%M"))
    print("=" * 72)

    # ---------------------------------------------------------------- tables
    tables = [r[0] for r in q(
        conn,
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    print("\n\n1. TABLES\n" + "-" * 72)
    vides, tailles = [], {}
    for t in tables:
        try:
            n = q(conn, f"SELECT COUNT(*) FROM '{t}'")[0][0]
        except Exception as e:
            print(f"  {t:30} erreur : {str(e)[:50]}")
            continue
        cols = q(conn, f"PRAGMA table_info('{t}')")
        tailles[t] = n
        marque = "  <-- VIDE" if n == 0 else ""
        print(f"  {t:30} {n:>8} lignes  {len(cols):>3} colonnes{marque}")
        if n == 0:
            vides.append(t)

    if vides:
        print(f"\n  => {len(vides)} table(s) vide(s) : {', '.join(vides)}")
        print("     Le chat lit leur schéma à chaque question, pour rien.")

    # ------------------------------------------------- colonnes peu remplies
    print("\n\n2. REMPLISSAGE DES COLONNES DE `notice`\n" + "-" * 72)
    total = tailles.get("notice", 0)
    if total:
        cols = [r[1] for r in q(conn, "PRAGMA table_info('notice')")]
        # une seule requête plutôt qu'une par colonne : bien moins de lignes lues
        expr = ", ".join(f"SUM(CASE WHEN \"{c}\" IS NOT NULL AND "
                         f"CAST(\"{c}\" AS TEXT) != '' THEN 1 ELSE 0 END)"
                         for c in cols)
        remplis = q(conn, f"SELECT {expr} FROM notice")[0]
        paires = sorted(zip(cols, remplis), key=lambda x: x[1])
        for nom, n in paires:
            pct = 100.0 * n / total
            barre = "#" * int(pct / 5)
            alerte = "  <-- VIDE" if n == 0 else ("  <-- rare" if pct < 5 else "")
            print(f"  {nom:26} {pct:5.1f}%  {barre:20} {n:>7}{alerte}")
        mortes = [c for c, n in paires if n == 0]
        if mortes:
            print(f"\n  => {len(mortes)} colonne(s) jamais remplie(s) : "
                  f"{', '.join(mortes)}")

    # ----------------------------------------------------------------- index
    print("\n\n3. INDEX EXISTANTS\n" + "-" * 72)
    idx = q(conn, "SELECT tbl_name, name, sql FROM sqlite_master "
                  "WHERE type='index' ORDER BY tbl_name, name")
    for t, n, sql in idx:
        print(f"  {t:22} {n:38} {(sql or '(automatique)')[:60]}")
    print(f"\n  total : {len(idx)}")

    # ------------------------------------------------- usage réel par le chat
    print("\n\n4. CE QUE LE CHAT DEMANDE VRAIMENT\n" + "-" * 72)
    try:
        # la colonne s'appelle sql_executees (cf. app_conversationnel.py)
        lignes = q(conn,
                   "SELECT sql_executees FROM journal_requetes "
                   "WHERE sql_executees IS NOT NULL "
                   "ORDER BY id DESC LIMIT 400")
        import re
        from collections import Counter
        champs = Counter()
        for (r,) in lignes:
            for m in re.finditer(
                    r"\b(?:WHERE|AND|OR)\s+(?:\w+\.)?(\w+)\s*(?:=|LIKE|IN|>|<)",
                    r or "", re.I):
                champs[m.group(1).lower()] += 1
        print(f"  {len(lignes)} requêtes analysées.")
        print("  Colonnes les plus filtrées (candidates à l'index) :")
        for nom, n in champs.most_common(15):
            print(f"    {n:5}x  {nom}")
    except Exception as e:
        print(f"  (journal_requetes indisponible : {str(e)[:70]})")

    # ------------------------------------------------------ plans d'exécution
    print("\n\n5. PLANS D'EXÉCUTION\n" + "-" * 72)
    print("  SCAN = balayage complet (lent, coûteux en lignes lues)")
    print("  SEARCH ... USING INDEX = accès direct (bon)\n")
    for libelle, sql in REQUETES_TYPES:
        print(f"  {libelle}")
        try:
            for r in q(conn, "EXPLAIN QUERY PLAN " + sql):
                detail = r[-1]
                mauvais = "  <<< BALAYAGE" if str(detail).startswith("SCAN") else ""
                print(f"      {detail}{mauvais}")
        except Exception as e:
            print(f"      erreur : {str(e)[:70]}")
        print()

    conn.close()
    print("=" * 72)
    print("Audit terminé. Rien n'a été modifié.")


if __name__ == "__main__":
    main()
