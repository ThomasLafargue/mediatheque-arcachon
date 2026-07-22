#!/usr/bin/env python3
"""
Enrichissement par lots des nouvelles notices Decalog via le moteur de
recherche multi-sources, écrit directement dans inventaire.db.

Ne réécrit JAMAIS titre / editeur / date_publication : ces champs viennent
de Decalog et sont déjà fiables. Complète les champs que Decalog ne
fournit pas : categorie (type), genre, public_vise (si encore vide), pegi,
createurs_secondaires (illustrateur), et depuis le 2026-07-22 serie/tome
quand ils sont vides (le moteur multi-sources les extrait déjà -- ils
n'étaient simplement pas écrits en base jusqu'ici).

Depuis le 2026-07-22, le moteur à 11 sites (chercher_isbn) tourne
SYSTÉMATIQUEMENT pour chaque ISBN -- avant, il était court-circuité dès que
BnF/Sudoc répondait avec un résumé, ce qui privait ces notices de
serie/tome (BnF/Sudoc ne les fournissent pas). BnF/Sudoc restent
interrogés en complément pour dewey/mots_cles/couverture, plus rapides à
obtenir de leur côté. Ce choix ralentit l'enrichissement (le moteur à 11
sites est plus lent que BnF/Sudoc seul) mais garantit serie/tome partout
où c'est possible.

Reprise automatique : chaque ISBN traité avec succès est marqué
(date_enrichissement renseignée) — relancer ce script reprend exactement
où il s'est arrêté, sans repasser sur ce qui est déjà fait.

Usage :
    python3 lancer_enrichissement.py liste_isbn_a_enrichir.txt
    python3 lancer_enrichissement.py liste_isbn_a_enrichir.txt --limite 500
    python3 lancer_enrichissement.py liste_isbn_backfill.txt --forcer

--limite N   : traite au plus N ISBN sur cette exécution (pour avancer par
               petites sessions plutôt que de tout lancer d'un coup).
--forcer     : retraite même les ISBN déjà marqués enrichis (date_enrichissement
               déjà renseignée). Utile pour un backfill ciblé (ex: notices
               enrichies avant le fix serie/tome du 2026-07-22) -- sans danger
               pour les champs déjà bons grâce aux COALESCE. Pour reprendre un
               backfill interrompu, régénère la liste depuis la base (les
               notices déjà corrigées ne seront alors plus dans le fichier)
               plutôt que de relancer --forcer sur l'ancienne liste complète.
"""

import sys
import os
import sqlite3
import db
import argparse
import datetime
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from moteur_recherche import chercher_isbn  # noqa: E402
try:
    from sources_api import enrichir_par_api
    API_OK = True
except ImportError:
    API_OK = False

FICHIER_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventaire.db")


def deviner_categorie(classifications, public_vise):
    """Best-effort : déduit 'manga'/'bd'/'roman_jeunesse'/... depuis ce que
    Decalog a déjà classé, pour orienter le moteur vers les bonnes sources
    en priorité. Ce n'est qu'une optimisation -- si rien ne correspond, le
    moteur utilise son ordre de sources par défaut."""
    if not classifications:
        return None
    c = classifications.lower()
    if 'manga' in c:
        return 'manga'
    if 'bande dessinée' in c or 'bd' in c:
        return 'bd'
    if 'documentaire' in c:
        return 'documentaire'
    if 'roman' in c:
        return 'roman_ado' if public_vise == 'Ado (12+)' else 'roman_jeunesse'
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fichier_isbn")
    parser.add_argument("--limite", type=int, default=None)
    parser.add_argument("--forcer", action="store_true")
    args = parser.parse_args()

    with open(args.fichier_isbn, encoding="utf-8") as f:
        isbns = [l.strip() for l in f if l.strip()]

    conn = db.connect(FICHIER_DB)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    def reconnecter():
        """Reconnexion après une erreur (coupure réseau, session Turso expirée
        après une longue inactivité, etc.) -- sans ça, un incident passager
        ferait planter tout un calcul de plusieurs jours."""
        nonlocal conn, cur
        try:
            conn.close()
        except Exception:
            pass
        conn = db.connect(FICHIER_DB)
        conn.execute("PRAGMA foreign_keys = ON;")
        cur = conn.cursor()

    def executer_avec_reprise(sql, params, max_essais=4):
        """Exécute + commit, en réessayant avec reconnexion si la connexion
        a été coupée. Si tout échoue malgré les essais, renvoie False --
        l'appelant passe alors à l'ISBN suivant plutôt que de tout arrêter."""
        for essai in range(1, max_essais + 1):
            try:
                cur.execute(sql, params)
                conn.commit()
                return True
            except Exception as e:
                print(f"    (erreur de connexion, tentative {essai}/{max_essais} : {e})")
                time.sleep(min(5 * essai, 30))
                reconnecter()
        return False

    traites, trouves, non_trouves, ignores_erreur = 0, 0, 0, 0
    debut = time.time()

    for i, isbn in enumerate(isbns, 1):
        if args.limite and traites >= args.limite:
            print(f"\nLimite de {args.limite} atteinte — relancez la commande pour continuer.")
            break

        try:
            cur.execute("SELECT public_vise, date_enrichissement FROM notice WHERE identifiant = ?", (isbn,))
            row = cur.fetchone()
        except Exception as e:
            print(f"  [{i}/{len(isbns)}] {isbn} -> connexion perdue en lecture ({e}), reconnexion...")
            reconnecter()
            try:
                cur.execute("SELECT public_vise, date_enrichissement FROM notice WHERE identifiant = ?", (isbn,))
                row = cur.fetchone()
            except Exception as e2:
                print(f"  [{i}/{len(isbns)}] {isbn} -> toujours en échec après reconnexion ({e2}), ISBN ignoré pour cette session")
                ignores_erreur += 1
                continue

        if not row:
            continue
        public_vise_actuel, deja_fait = row
        if deja_fait and not args.forcer:
            continue  # déjà traité lors d'une session précédente -- reprise automatique

        categorie_hint = deviner_categorie(None, public_vise_actuel)

        # Le moteur à 11 sites tourne systématiquement -- c'est lui qui
        # calcule serie/tome (BnF/Sudoc ne les fournissent jamais).
        try:
            res = chercher_isbn(isbn, categorie_hint)
        except Exception as e:
            print(f"  [{i}/{len(isbns)}] {isbn} -> erreur ({e})")
            continue

        # Complément BnF/Sudoc : dewey, mots-clés Rameau, couverture, et
        # résumé de secours si le moteur à 11 sites n'en a pas trouvé.
        if API_OK:
            try:
                api_data = enrichir_par_api(isbn)
                if api_data:
                    res['_image_url'] = api_data.get('image_url')
                    res['_mots_cles'] = api_data.get('mots_cles')
                    res['_dewey'] = api_data.get('dewey')
                    if not res.get('resume'):
                        res['resume'] = api_data.get('resume')
            except Exception:
                pass

        traites += 1
        if res.get("statut") == "trouvé":
            trouves += 1
            sql = """
                UPDATE notice SET
                    categorie = COALESCE(categorie, ?),
                    genre = COALESCE(genre, ?),
                    public_vise = COALESCE(public_vise, ?),
                    pegi = COALESCE(pegi, ?),
                    createurs_secondaires = COALESCE(createurs_secondaires, ?),
                    collection = COALESCE(collection, ?),
                    resume = COALESCE(resume, ?),
                    serie = COALESCE(serie, ?),
                    tome = COALESCE(tome, ?),
                    score_confiance = ?,
                    nb_sources_consultees = ?,
                    date_enrichissement = ?
                WHERE identifiant = ?
            """
            params = (
                res.get("type") or None, res.get("genre") or None,
                res.get("public") or None, res.get("pegi") or None,
                res.get("illustrateur") or None, res.get("collection") or None,
                res.get("resume") or None,
                res.get("serie") or None, res.get("tome") or None,
                None, None, datetime.datetime.now().isoformat(), isbn,
            )
        else:
            non_trouves += 1
            sql = "UPDATE notice SET date_enrichissement = ? WHERE identifiant = ?"
            params = (datetime.datetime.now().isoformat(), isbn)

        ok = executer_avec_reprise(sql, params)
        if ok and res.get('statut') in ('trouvé', 'trouve'):
            img, mc, dw = res.get('_image_url'), res.get('_mots_cles'), res.get('_dewey')
            if img or mc or dw:
                executer_avec_reprise(
                    "UPDATE notice SET image_url=COALESCE(image_url,?), mots_cles=COALESCE(mots_cles,?), dewey=COALESCE(dewey,?) WHERE identifiant=?",
                    (img, mc, dw, isbn))
        if not ok:
            print(f"  [{i}/{len(isbns)}] {isbn} -> écriture impossible malgré les tentatives, "
                  f"sera repris automatiquement lors d'une prochaine exécution")
            ignores_erreur += 1
            traites -= 1
            if res.get("statut") == "trouvé":
                trouves -= 1
            else:
                non_trouves -= 1

        if traites % 20 == 0 and traites > 0:
            ecoule = time.time() - debut
            vitesse = ecoule / traites
            restant = len(isbns) - i
            eta_h = (restant * vitesse) / 3600
            print(f"  [{i}/{len(isbns)}] traités={traites} trouvés={trouves} "
                  f"non_trouvés={non_trouves} ignorés_erreur={ignores_erreur} — ~{vitesse:.1f}s/ISBN — "
                  f"reste estimé {eta_h:.1f}h si on continue jusqu'au bout")

    conn.close()
    print(f"\n{'='*60}")
    print(f"  ISBN traités cette session : {traites}")
    print(f"  Trouvés                    : {trouves}")
    print(f"  Non trouvés                : {non_trouves}")
    print(f"  Ignorés (erreur persistante) : {ignores_erreur}")
    print(f"{'='*60}")
    print("Relancer la même commande reprend automatiquement où on s'est arrêté.")


if __name__ == "__main__":
    while True:
        try:
            main()
            break  # terminé normalement (liste épuisée ou --limite atteinte)
        except Exception as e:
            print(f"\n⚠ Erreur imprévue, redémarrage automatique dans 30s : {e}")
            time.sleep(30)
