#!/usr/bin/env python3
"""
identifier_series_ambigues.py — Détecte les séries BD/Manga/Roman jeunesse
numérotées SANS marqueur explicite dans le titre (ex: "Naruto 12" au lieu
de "Naruto tome 12"), que corriger_serie_tome_manquants.py laisse
volontairement de côté (trop ambigu pour une regex seule).

DEUX ÉTAPES SÉPARÉES, pour ne jamais dépenser d'appels IA à l'aveugle :

  Étape 1 (gratuite, toujours exécutée) -- IDENTIFICATION
    Repère les notices dont le titre se termine par un nombre nu
    ("Naruto 12"), UNIQUEMENT dans les catégories où ce motif est courant
    (BD, Manga, Comics, Roman jeunesse, Roman ado / YA). Volontairement
    exclu : Documentaire, Album, Jeu vidéo, etc. -- trop de faux positifs
    possibles (un titre qui se termine par un nombre n'y est presque
    jamais un numéro de tome). Résultat écrit dans candidats_serie_ia.csv,
    AUCUN appel IA, AUCUNE écriture en base.

  Étape 2 (payante -- quelques centimes à ~3$, avec --verifier-ia N)
    Envoie les N premiers candidats à Claude un par un, avec consigne
    stricte de distinguer "Naruto 12" (série) de "Fahrenheit 451" ou
    "1984" (le nombre fait partie du titre, pas un numéro de tome).
    Résultat (avec niveau de confiance) réécrit dans le même CSV.
    AUCUNE écriture en base à ce stade.

  Étape 3 (avec --appliquer, après --verifier-ia)
    Écrit en base UNIQUEMENT les lignes confiance="haute" du CSV, et
    UNIQUEMENT si serie ET tome sont encore NULL au moment de l'écriture
    (même garde-fou que corriger_serie_tome_manquants.py). Les
    confiance="moyenne"/"basse" ne sont jamais écrites automatiquement --
    à revoir à la main dans le CSV si tu veux les traiter quand même.

Usage :
    python3 identifier_series_ambigues.py                    # étape 1 seule
    python3 identifier_series_ambigues.py --verifier-ia 30    # + étape 2 sur 30 candidats (test)
    python3 identifier_series_ambigues.py --verifier-ia 9999  # + étape 2 sur tous les candidats
    python3 identifier_series_ambigues.py --appliquer         # étape 3 (nécessite un CSV déjà vérifié)

Nécessite ANTHROPIC_API_KEY dans .env pour --verifier-ia (à copier depuis
les secrets Streamlit -- absente du .env local au 2026-07-22).
Nécessite TURSO_AUTH_TOKEN_ECRITURE dans .env pour --appliquer.
"""

import sys
import os
import re
import csv
import json
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

CSV_CANDIDATS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'candidats_serie_ia.csv')

# Catégories où "Titre + nombre nu" est un motif de série courant et fiable.
# Volontairement restrictif : ailleurs (Documentaire, Album, Jeu vidéo...)
# un titre qui se termine par un nombre est presque toujours un titre normal.
CATEGORIES_CIBLEES = {'BD', 'Manga', 'Comics', 'Roman jeunesse', 'Roman ado / YA'}

# Titre se terminant par un nombre nu (1 à 3 chiffres), précédé d'au moins
# 2 caractères de nom de série. Le séparateur peut être un espace ou une
# ponctuation légère -- jamais "tome"/"T."/"vol." (déjà traité ailleurs).
MOTIF_NOMBRE_NU = re.compile(r'^(?P<serie>.{2,}?)[\s\-–—:,]+(?P<tome>\d{1,3})\s*$')

PROMPT_TEMPLATE = """Tu analyses un titre de livre issu d'un catalogue de médiathèque, pour déterminer si le nombre en fin de titre est un numéro de tome de série, ou s'il fait partie intégrante du titre de l'œuvre.

Titre exact du catalogue : "{titre}"
Catégorie catalographique : {categorie}

Exemples de VRAIS numéros de tome (est_serie=true) :
- "Naruto 12" -> série "Naruto", tome "12"
- "Seuls 8" -> série "Seuls", tome "8"
- "One Piece 98" -> série "One Piece", tome "98"

Exemples où le nombre fait partie du titre, PAS un tome (est_serie=false) :
- "Fahrenheit 451" (titre de science-fiction, 451 = degrés Fahrenheit)
- "1984" (titre du roman de George Orwell)
- "Ocean's Eleven" (si jamais un nombre écrit en toutes lettres apparaissait, ce n'est de toute façon pas ce cas ici)
- Tout titre où le nombre a un sens narratif propre (une date, une quantité, un code) plutôt qu'un rang dans une série

Réponds UNIQUEMENT par un objet JSON valide, sans aucun texte avant ou après :
{{"est_serie": true ou false, "serie": "nom de la série sans le numéro" ou null, "tome": "le numéro" ou null, "confiance": "haute" ou "moyenne" ou "basse", "raison": "justification en une courte phrase"}}"""


def etape1_identifier():
    """Identifie les candidats par motif, sans appel IA. Écrit le CSV."""
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT identifiant, titre, categorie
        FROM notice
        WHERE type_document = 'LIVRE' AND serie IS NULL AND tome IS NULL
        ORDER BY identifiant
    """)
    lignes = cur.fetchall()
    conn.close()

    candidats = []
    for identifiant, titre, categorie in lignes:
        if categorie not in CATEGORIES_CIBLEES:
            continue
        if not titre:
            continue
        m = MOTIF_NOMBRE_NU.match(titre.strip())
        if m:
            candidats.append({
                'identifiant': identifiant,
                'titre': titre,
                'categorie': categorie,
                'serie_devinee': m.group('serie').strip(' .,-–—:'),
                'tome_devine': m.group('tome'),
                'est_serie': '', 'serie_ia': '', 'tome_ia': '',
                'confiance': '', 'raison': '',
            })

    print(f"Notices LIVRE sans serie/tome, dans les catégories ciblées {sorted(CATEGORIES_CIBLEES)} : "
          f"{sum(1 for l in lignes if l[2] in CATEGORIES_CIBLEES)}")
    print(f"Candidats détectés (titre se terminant par un nombre nu) : {len(candidats)}")

    with open(CSV_CANDIDATS, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(candidats[0].keys()) if candidats else
                                 ['identifiant', 'titre', 'categorie', 'serie_devinee', 'tome_devine',
                                  'est_serie', 'serie_ia', 'tome_ia', 'confiance', 'raison'])
        writer.writeheader()
        writer.writerows(candidats)

    print(f"\nExemples (10 premiers) :")
    for c in candidats[:10]:
        print(f"  [{c['identifiant']}] \"{c['titre']}\" ({c['categorie']}) "
              f"-> hypothèse : serie=\"{c['serie_devinee']}\" tome=\"{c['tome_devine']}\"")

    print(f"\nCandidats écrits dans {CSV_CANDIDATS} -- aucun appel IA, aucune écriture en base.")
    print("Pour vérifier avec l'IA (quelques centimes à ~3$ selon le volume) :")
    print(f"  python3 identifier_series_ambigues.py --verifier-ia 30   # test sur 30 d'abord")
    return candidats


def etape2_verifier_ia(limite):
    """Envoie les N premiers candidats du CSV à Claude, met à jour le CSV."""
    if not os.path.exists(CSV_CANDIDATS):
        print(f"✗ {CSV_CANDIDATS} introuvable -- lance d'abord sans option pour générer les candidats.")
        sys.exit(1)

    cle = os.environ.get('ANTHROPIC_API_KEY')
    if not cle:
        print("✗ ANTHROPIC_API_KEY absent de .env -- copie-le depuis les secrets Streamlit.")
        sys.exit(1)

    import anthropic
    client = anthropic.Anthropic(api_key=cle)

    with open(CSV_CANDIDATS, encoding='utf-8') as f:
        candidats = list(csv.DictReader(f))

    a_traiter = [c for c in candidats if not c.get('confiance')][:limite]
    print(f"Vérification IA sur {len(a_traiter)} candidats (sur {len(candidats)} au total)...\n")

    compteurs = {'haute': 0, 'moyenne': 0, 'basse': 0, 'pas_serie': 0, 'erreur': 0}

    for i, c in enumerate(a_traiter, 1):
        prompt = PROMPT_TEMPLATE.format(titre=c['titre'], categorie=c['categorie'])
        try:
            reponse = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            texte = "".join(b.text for b in reponse.content if b.type == "text").strip()
            texte = re.sub(r'^```(?:json)?|```$', '', texte.strip(), flags=re.MULTILINE).strip()
            verdict = json.loads(texte)

            c['est_serie'] = str(verdict.get('est_serie', False))
            c['serie_ia'] = verdict.get('serie') or ''
            c['tome_ia'] = verdict.get('tome') or ''
            c['confiance'] = verdict.get('confiance', 'basse') if verdict.get('est_serie') else 'non-serie'
            c['raison'] = verdict.get('raison', '')

            if not verdict.get('est_serie'):
                compteurs['pas_serie'] += 1
            else:
                compteurs[verdict.get('confiance', 'basse')] += 1

            print(f"  [{i}/{len(a_traiter)}] \"{c['titre']}\" -> "
                  f"{'série' if verdict.get('est_serie') else 'PAS série'} "
                  f"({c['confiance']}) : {c['raison'][:60]}")

        except Exception as e:
            c['confiance'] = 'erreur'
            c['raison'] = str(e)[:100]
            compteurs['erreur'] += 1
            print(f"  [{i}/{len(a_traiter)}] \"{c['titre']}\" -> ERREUR : {e}")

        time.sleep(0.2)

    # Réécrire le CSV complet (candidats traités + non encore traités)
    with open(CSV_CANDIDATS, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(candidats[0].keys()))
        writer.writeheader()
        writer.writerows(candidats)

    print(f"\nRésumé : haute={compteurs['haute']}  moyenne={compteurs['moyenne']}  "
          f"basse={compteurs['basse']}  pas-une-série={compteurs['pas_serie']}  erreurs={compteurs['erreur']}")
    print(f"CSV mis à jour : {CSV_CANDIDATS}")
    if compteurs['haute'] > 0:
        print(f"\n{compteurs['haute']} candidats en confiance haute -- prêts pour --appliquer.")


def etape3_appliquer():
    """Écrit en base les lignes confiance=haute du CSV, en revérifiant NULL au moment d'écrire."""
    if not os.path.exists(CSV_CANDIDATS):
        print(f"✗ {CSV_CANDIDATS} introuvable.")
        sys.exit(1)

    jeton = os.environ.get('TURSO_AUTH_TOKEN_ECRITURE')
    if not jeton:
        print("✗ TURSO_AUTH_TOKEN_ECRITURE absent de .env -- impossible d'écrire.")
        sys.exit(1)

    with open(CSV_CANDIDATS, encoding='utf-8') as f:
        candidats = list(csv.DictReader(f))

    a_ecrire = [c for c in candidats if c.get('confiance') == 'haute' and c.get('serie_ia')]
    if not a_ecrire:
        print("Aucun candidat en confiance haute à écrire. Lance --verifier-ia d'abord.")
        return

    conn = db.connect_avec_jeton(db.TURSO_URL, jeton)
    cur = conn.cursor()
    n_ok = 0
    for c in a_ecrire:
        cur.execute(
            "UPDATE notice SET serie = ?, tome = ? WHERE identifiant = ? AND serie IS NULL AND tome IS NULL",
            (c['serie_ia'], c['tome_ia'], c['identifiant']),
        )
        n_ok += 1
    conn.commit()
    conn.close()

    n_a_revoir = sum(1 for c in candidats if c.get('confiance') in ('moyenne', 'basse'))
    print(f"✓ {n_ok} notices corrigées en base (confiance haute).")
    if n_a_revoir:
        print(f"  {n_a_revoir} candidats en confiance moyenne/basse laissés de côté -- "
              f"à revoir à la main dans {CSV_CANDIDATS} si tu veux les traiter.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--verifier-ia', type=int, metavar='N',
                         help="Vérifie les N premiers candidats non encore traités avec Claude")
    parser.add_argument('--appliquer', action='store_true',
                         help="Écrit en base les candidats en confiance haute (nécessite --verifier-ia au préalable)")
    args = parser.parse_args()

    if args.appliquer:
        etape3_appliquer()
    elif args.verifier_ia:
        if not os.path.exists(CSV_CANDIDATS):
            etape1_identifier()
        etape2_verifier_ia(args.verifier_ia)
    else:
        etape1_identifier()


if __name__ == '__main__':
    main()
