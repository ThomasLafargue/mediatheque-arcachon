#!/usr/bin/env python3
"""
normaliser_public_vise.py — Rattrapage INITIAL : applique la règle de
public_vise.py à tout l'existant (tables notice ET exemplaire).

ORDRE DES OPÉRATIONS — pensé pour ne rien perdre :
  1. Les valeurs d'ÂGE (« Dès 3 ans »...) sont d'abord RECOPIÉES dans
     age_recommande quand celle-ci est vide. Seulement ensuite le public
     devient « Jeunesse ». L'information d'âge n'est donc jamais détruite,
     elle change de colonne — celle où elle aurait toujours dû être.
  2. Chaque valeur non canonique est remplacée par sa forme canonique,
     une valeur à la fois, avec le décompte affiché avant/après.
  3. Contrôle final : la liste des valeurs restantes. Attendu : Adulte,
     Jeunesse, Adolescent, Tout public (+ NULL).

À ne lancer QU'UNE FOIS ; l'import hebdomadaire entretient ensuite la
propreté (actualiser_catalogue.py normalise à l'entrée). Relancer par erreur
est sans danger : normaliser une valeur déjà canonique ne change rien.

Usage :
    python3 normaliser_public_vise.py               (simulation, n'écrit rien)
    python3 normaliser_public_vise.py --appliquer   (modifie réellement)
"""
import sys
import time

sys.path.insert(0, ".")
import db  # noqa: E402
from public_vise import normaliser, est_age, SEUIL_PEGI_MANGA_ADULTE  # noqa: E402


def etat(conn, table):
    return conn.execute(
        f"SELECT public_vise, COUNT(*) FROM {table} "
        f"GROUP BY public_vise ORDER BY 2 DESC").fetchall()


def main():
    appliquer = "--appliquer" in sys.argv
    conn = db.connect()

    print("=" * 68)
    print("NORMALISATION DU PUBLIC VISÉ — " + time.strftime("%Y-%m-%d %H:%M"))
    print("MODE : " + ("APPLICATION RÉELLE" if appliquer else
                       "SIMULATION (rien ne sera écrit)"))
    print("=" * 68)

    for table in ("notice", "exemplaire"):
        print(f"\n--- table {table} ---")
        avant = etat(conn, table)
        for v, n in avant:
            cible = normaliser(v)
            fleche = f" -> {cible!r}" if cible != v else "   (inchangé)"
            print(f"  {str(v)!r:24} {n:>7}{fleche}")

        # 1. sauvegarde des âges (notice seulement : exemplaire n'a pas
        #    de colonne age_recommande)
        ages = [v for v, _ in avant if v and est_age(v)]
        if table == "notice" and ages:
            marqueurs = ",".join("?" * len(ages))
            if appliquer:
                r = conn.execute(
                    f"UPDATE notice SET age_recommande = public_vise "
                    f"WHERE public_vise IN ({marqueurs}) "
                    f"AND (age_recommande IS NULL OR age_recommande = '')",
                    ages)
                conn.commit()
                print(f"\n  ages recopiés vers age_recommande : "
                      f"{r.rowcount if hasattr(r, 'rowcount') else '?'}")
            else:
                print(f"\n  [simulation] {len(ages)} valeur(s) d'âge seraient "
                      f"recopiées vers age_recommande avant conversion")

        # 2. conversion, valeur par valeur
        total = 0
        for v, n in avant:
            cible = normaliser(v)
            if cible == v or v is None:
                continue
            if appliquer:
                conn.execute(
                    f"UPDATE {table} SET public_vise = ? WHERE public_vise = ?",
                    (cible, v))
                conn.commit()
            total += n
        print(f"  {'lignes modifiées' if appliquer else 'lignes à modifier'} : "
              f"{total}")

    # 2 pré. NETTOYAGE PEGI : le champ contenait « PEGI 12 » au lieu de
    # « 12 » — CAST lisait 0 et toute comparaison numérique mentait
    # silencieusement (découvert par _verif_pegi_mangas.py le 2026-07-27 :
    # 0 manga « >= 14 » alors que la comparaison était juste cassée).
    # On garde le nombre seul ; moteur_recherche n'écrit plus que ça.
    print("\n--- nettoyage du champ pegi ---")
    n_pegi = conn.execute(
        "SELECT COUNT(*) FROM notice WHERE pegi LIKE 'PEGI %'").fetchone()[0]
    if appliquer and n_pegi:
        conn.execute(
            "UPDATE notice SET pegi = TRIM(REPLACE(pegi, 'PEGI', '')) "
            "WHERE pegi LIKE 'PEGI %'")
        conn.commit()
    print(f"  « PEGI n » -> « n » : {n_pegi} notice(s) "
          f"{'nettoyées' if appliquer else 'à nettoyer'}")

    # 2 bis. RÈGLE MANGA (Thomas, 2026-07-27) : le public d'un manga découle
    # de son PEGI — >= 14 c'est Adulte, en dessous c'est Jeunesse (pas de
    # rayon manga ado à la MAAT). PEGI absent -> on ne touche pas : décider
    # « Jeunesse » pour un seinen non renseigné serait pire que le statu quo.
    print("\n--- règle manga (PEGI) ---")
    # REPLACE avant CAST : robuste que le nettoyage soit déjà passé ou non
    # (indispensable en simulation, où l'étape 2 pré n'écrit rien)
    pegi_num = "CAST(TRIM(REPLACE(pegi, 'PEGI', '')) AS INTEGER)"
    for sens, cond in (
            ("Adulte", f"{pegi_num} >= {SEUIL_PEGI_MANGA_ADULTE}"),
            ("Jeunesse", f"{pegi_num} < {SEUIL_PEGI_MANGA_ADULTE}")):
        sql_ou = (f"categorie = 'Manga' AND pegi IS NOT NULL AND pegi != '' "
                  f"AND {cond} AND (public_vise IS NULL OR public_vise != ?)")
        n = conn.execute(
            f"SELECT COUNT(*) FROM notice WHERE {sql_ou}", (sens,)
        ).fetchone()[0]
        if appliquer and n:
            conn.execute(
                f"UPDATE notice SET public_vise = ? WHERE {sql_ou}",
                (sens, sens))
            conn.commit()
        print(f"  mangas PEGI {'>=' if sens == 'Adulte' else '<'}"
              f" {SEUIL_PEGI_MANGA_ADULTE} -> {sens:9} : "
              f"{n} notice(s) {'corrigées' if appliquer else 'à corriger'}")
    n_sans = conn.execute(
        "SELECT COUNT(*) FROM notice WHERE categorie = 'Manga' "
        "AND (pegi IS NULL OR pegi = '')").fetchone()[0]
    print(f"  mangas sans PEGI (public conservé tel quel) : {n_sans}")

    # 3. contrôle final
    if appliquer:
        print("\n--- CONTRÔLE FINAL ---")
        for table in ("notice", "exemplaire"):
            restantes = [str(v) for v, _ in etat(conn, table)]
            print(f"  {table:12} : {', '.join(restantes)}")

    conn.close()
    print("\n" + "=" * 68)
    if appliquer:
        print("Terminé. L'import hebdomadaire entretient désormais la règle.")
    else:
        print("Simulation terminée, rien n'a été écrit.")
        print("Pour appliquer :  python3 normaliser_public_vise.py --appliquer")


if __name__ == "__main__":
    main()
