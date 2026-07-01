#!/usr/bin/env python3
"""
Actualisation du catalogue depuis un export Decalog (.mrc, UNIMARC,
"Exporter les exemplaires également" coché, encodage UTF-8).

Usage :
    python3 actualiser_catalogue.py "Liste des notices - AAAA-MM-JJ.mrc"

Ce que ce script fait, en un seul passage :
  1. Lit le .mrc (notices + exemplaires)
  2. Met à jour titre / série / tome / éditeur / date_publication / résumé /
     image pour les notices déjà connues -- Decalog reste la référence sur
     ces champs, comme décidé.
  3. Insère les notices nouvelles (categorie / genre / public / pegi restent
     vides : c'est le rôle de lancer_enrichissement.py, pas de ce script).
  4. Met à jour les exemplaires (cote, site, statut, support, public) SANS
     jamais toucher prix / nb_prets_total / annee_dernier_pret -- ces trois
     champs viennent du fichier statistiques, alimenté par un autre script.
  5. Renormalise les noms de série sur l'ENSEMBLE de la base (existant +
     nouveau), par vote majoritaire pondéré par le nombre réel de notices
     concernées -- une nouvelle variante minoritaire ne peut jamais déloger
     une forme déjà bien établie.
  6. Réharmonise public_vise / categorie / genre au sein de chaque série
     (toujours par vote majoritaire), pour que les nouveaux tomes héritent
     automatiquement du consensus déjà établi sur leur série.

Ne fait jamais : remplir categorie/genre/public_vise pour une notice qui n'a
jamais été vue -- ça reste le travail du moteur de recherche multi-sources.
"""

import sys
import os
import re
import csv
import argparse
import sqlite3
import db
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from iso2709 import parse_records, get_subfields  # noqa: E402

FICHIER_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventaire.db")


# ----------------------------------------------------------------------------
# Mappage "Centre d'intérêt COBAS" (champ 686) -> categorie / genre.
# Conservateur par construction : on ne mappe que ce dont on est sûr, le
# reste tombe dans la liste pour lancer_enrichissement.py plutôt que d'être
# deviné. Vocabulaire aligné sur celui déjà utilisé dans la base.
# ----------------------------------------------------------------------------
COBAS_VERS_CATEGORIE = {
    'Bandes dessinées': 'BD', 'Comics': 'BD', 'Romans graphiques': 'BD',
    'Mangas': 'Manga',
    'Albums': 'Album', 'Albums tout petits': 'Album', 'Albums sans texte': 'Album',
    'Premières lectures': 'Première lecture',
    'Contes': 'Conte / Poésie', 'Poésie': 'Conte / Poésie', 'Comptines': 'Conte / Poésie',
    'Histoire': 'Documentaire', 'Géographie': 'Documentaire',
    'Biographies et autobiographies': 'Documentaire', 'Arts': 'Documentaire',
    'Sciences de la nature': 'Documentaire', 'Sciences sociales': 'Documentaire',
    'Philosophie, Psychologie': 'Documentaire', 'Sciences et mathématiques': 'Documentaire',
    'Santé': 'Documentaire', 'Sports et loisirs': 'Documentaire', 'Religion': 'Documentaire',
    'Politique': 'Documentaire', 'Economie': 'Documentaire',
    'Informatique, Information': 'Documentaire', 'Langues': 'Documentaire',
    'Droit': 'Documentaire', 'Jardinage, Bricolage': 'Documentaire', 'Cuisine': 'Documentaire',
    'Développement durable': 'Documentaire', 'Formation, Orientation': 'Documentaire',
    'Transports': 'Documentaire', 'Guides touristiques': 'Documentaire',
    'Récits de voyage': 'Documentaire', 'Éducation': 'Documentaire',
}
# 'Romans' n'est pas dans ce dict : ado vs jeunesse dépend du public, géré à part.

COBAS_VERS_GENRE = {
    'Policier': 'Policier', 'Polar': 'Policier', 'Thriller': 'Policier', 'Romans noirs': 'Policier',
    'Science-fiction': 'Science-fiction',
    'Fantastique': 'Fantastique', 'Fantasy': 'Fantastique',
    'Historique': 'Historique',
    'Comédie': 'Humour', 'Humour': 'Humour',
    'Sentimental': 'Amour',
    'Action, Aventure': 'Aventure',
    'Epouvante': 'Frissons',
    'Cuisine': 'Activités', 'Jardinage, Bricolage': 'Activités', 'Loisirs créatifs': 'Activités',
    'Sports et loisirs': 'Sport',
    'Sciences de la nature': 'Nature', 'Sciences et mathématiques': 'Sciences',
    'Philosophie, Psychologie': 'Philo', 'Sciences sociales': 'Société',
    'Géographie': 'Géographie', 'Récits de voyage': 'Géographie', 'Guides touristiques': 'Géographie',
    'Arts': 'Arts',
}


def deriver_categorie_genre(cobas_valeurs, public_vise):
    """A partir des valeurs 686 'Centre d'intérêt COBAS' d'une notice, déduit
    categorie et genre (max 2 termes) quand c'est possible sans ambiguïté."""
    categorie = None
    if 'Romans' in cobas_valeurs:
        if public_vise == 'Adulte':
            categorie = None  # Romans adultes : pas de catégorie jeunesse
        elif public_vise in ('Ado (12+)', 'Adolescent'):
            categorie = 'Roman ado / YA'
        else:
            categorie = 'Roman jeunesse'
    else:
        for v in cobas_valeurs:
            if v in COBAS_VERS_CATEGORIE:
                categorie = COBAS_VERS_CATEGORIE[v]
                break

    termes_genre = []
    for v in cobas_valeurs:
        g = COBAS_VERS_GENRE.get(v)
        if g and g not in termes_genre:
            termes_genre.append(g)
        if len(termes_genre) == 2:
            break
    genre = ' / '.join(termes_genre) if termes_genre else None
    return categorie, genre


# ----------------------------------------------------------------------------
# Extraction (même logique que les sessions précédentes, consolidée ici)
# ----------------------------------------------------------------------------
def clean_ean(s):
    return re.sub(r'[^0-9Xx]', '', s or '')


def isbn10_vers_ean13(isbn10):
    isbn10 = isbn10.strip().upper()
    coeur = isbn10[:9]
    base12 = "978" + coeur
    total = sum(int(ch) * (1 if i % 2 == 0 else 3) for i, ch in enumerate(base12))
    cle = (10 - (total % 10)) % 10
    return base12 + str(cle)


def determiner_identifiant(champs_073, champs_010):
    ean = clean_ean(champs_073) if champs_073 else None
    isbn = clean_ean(champs_010) if champs_010 else None
    if ean and len(ean) == 13 and ean.isdigit():
        return ean
    if isbn:
        if len(isbn) == 13 and isbn.isdigit():
            return isbn
        if len(isbn) == 10 and isbn[:9].isdigit():
            try:
                return isbn10_vers_ean13(isbn)
            except Exception:
                pass
    return ean or None


def nettoyer_nom_serie(brut):
    if not brut:
        return None
    nom = brut.split('/')[0].split('[')[0].strip()
    return nom or None


def parser_mrc(chemin):
    with open(chemin, "rb") as f:
        data = f.read()

    notices, exemplaires = [], []
    for rec in parse_records(data):
        titre = sous_titre = numero_partie = titre_partie = None
        auteur = editeur = date_pub = None
        illustrateur = traducteur = None
        contributeurs = []
        resume_parts = []
        image_url = None
        type_support_hint = None
        ean_073 = isbn_010 = None
        serie_461 = tome_461 = date_461 = None
        cobas_valeurs = []
        mots_cles = []
        dewey = dewey_libelle = None
        description_physique = None
        age_recommande = None
        exemplaires_locaux = []

        for tag, raw in rec['fields']:
            ind, subs = get_subfields(raw)
            if tag == '073':
                for code, val in subs:
                    if code == 'a':
                        ean_073 = val
            elif tag == '010':
                for code, val in subs:
                    if code == 'a':
                        isbn_010 = val
            elif tag == '200':
                for code, val in subs:
                    if code == 'a':
                        titre = val
                    elif code == 'e':
                        sous_titre = val
                    elif code == 'h':
                        numero_partie = val
                    elif code == 'i':
                        titre_partie = val
            elif tag in ('700', '701', '702'):
                d = dict(subs)
                nom = d.get('a')
                if nom:
                    contributeurs.append((d.get('4'), nom))
            elif tag in ('210', '214'):
                for code, val in subs:
                    if code == 'c' and not editeur:
                        editeur = val
                    elif code == 'd' and not date_pub:
                        date_pub = val
            elif tag == '330':
                for code, val in subs:
                    if code == 'a':
                        resume_parts.append(val)
            elif tag == '215':
                for code, val in subs:
                    if code == 'a' and not description_physique:
                        description_physique = val
            elif tag == '333':
                for code, val in subs:
                    if code == 'a' and not age_recommande:
                        age_recommande = val
            elif tag == '676':
                d = dict(subs)
                if d.get('a') and not dewey:
                    dewey = d.get('a')
                    dewey_libelle = d.get('l')
            elif tag == '606':
                for code, val in subs:
                    if code == 'a':
                        mots_cles.append(val)
            elif tag == '856':
                if any(c == '2' and v == 'Image' for c, v in subs):
                    for code, val in subs:
                        if code == 'u':
                            image_url = val
            elif tag == '461':
                for code, val in subs:
                    if code == 't':
                        serie_461 = val
                    elif code == 'v':
                        tome_461 = val
                    elif code == 'd':
                        date_461 = val
            elif tag == '686':
                lib = scheme = None
                for code, val in subs:
                    if code == 'l':
                        lib = val
                    elif code == '2':
                        scheme = val
                if scheme == "Centre d'intérêt COBAS" and lib:
                    cobas_valeurs.append(lib)
            elif tag == '995':
                d = dict(subs)
                if d.get('a') != "Médiathèque d'Arcachon":
                    continue  # le fonds géré ici est celui d'Arcachon -- les
                              # exemplaires des autres sites du réseau COBAS
                              # (visibles sur une notice partagée) sont ignorés
                if type_support_hint is None:
                    type_support_hint = d.get('w')
                exemplaires_locaux.append({
                    'site': d.get('a'), 'code_barres': d.get('f'), 'cote': d.get('k'),
                    'public_vise': d.get('l'), 'statut': d.get('v'),
                    'support': d.get('w'), 'date_inventaire': d.get('1'),
                })

        # Décision des rôles APRÈS avoir tout collecté (et non au fil de la
        # lecture) : les codes fonction explicites (070/440/730) priment
        # toujours, quel que soit leur ordre d'apparition dans le fichier.
        for role, nom in contributeurs:
            if role == '070' and auteur is None:
                auteur = nom
            elif role == '440' and illustrateur is None:
                illustrateur = nom
            elif role == '730' and traducteur is None:
                traducteur = nom
        if auteur is None:
            # repli : aucun code 070 trouvé -- on prend le premier contributeur
            # sans code de rôle du tout (cas de notices plus anciennes/sommaires)
            sans_role = [nom for role, nom in contributeurs if role is None]
            if sans_role:
                auteur = sans_role[0]

        if numero_partie:
            serie_brute, tome = titre, numero_partie
        elif serie_461 and tome_461:
            serie_brute, tome = nettoyer_nom_serie(serie_461), tome_461
        else:
            serie_brute, tome = None, None

        if date_461:
            type_document = 'REVUE'
        elif type_support_hint in ('CD', 'Livre-CD', 'Disque vinyle', 'Cassette'):
            type_document = 'CD'
        elif type_support_hint in ('DVD', 'Livre-DVD', 'Blu-ray'):
            type_document = 'DVD'
        elif type_support_hint == 'Jeu':
            type_document = 'JEU'
        elif type_support_hint in ('Imprimé', 'Livre tactile', 'Support électronique'):
            type_document = 'LIVRE'
        else:
            type_document = 'AUTRE'

        identifiant = determiner_identifiant(ean_073, isbn_010)

        # Notices sans EAN/ISBN : utiliser le code-barres du premier exemplaire
        # Arcachon comme identifiant de substitution, préfixé pour l'identifier
        # clairement. Ces notices sont ainsi visibles dans le chat, avec un
        # marquage explicite "sans EAN -- à corriger dans Decalog".
        if not identifiant and exemplaires_locaux:
            cb_substitut = next((e.get('code_barres') for e in exemplaires_locaux if e.get('code_barres')), None)
            if cb_substitut:
                identifiant = f"CB:{cb_substitut}"
        titre_final = titre_partie or titre
        public_hint = next((e['public_vise'] for e in exemplaires_locaux if e.get('public_vise')), None)
        categorie_decalog, genre_decalog = deriver_categorie_genre(cobas_valeurs, public_hint)

        notices.append({
            'identifiant': identifiant, 'type_document': type_document,
            'titre': titre_final, 'serie_brute': serie_brute, 'tome': tome,
            'auteur': auteur, 'illustrateur': illustrateur, 'traducteur': traducteur,
            'editeur': editeur, 'date_publication': date_pub,
            'resume': ' '.join(resume_parts) if resume_parts else None,
            'image_url': image_url, 'public_hint': public_hint,
            'categorie_decalog': categorie_decalog, 'genre_decalog': genre_decalog,
            'dewey': dewey, 'dewey_libelle': dewey_libelle,
            'mots_cles': ' | '.join(mots_cles) if mots_cles else None,
            'description_physique': description_physique,
            'age_recommande': age_recommande,
        })
        for ex in exemplaires_locaux:
            ex['identifiant'] = identifiant
            exemplaires.append(ex)

    return notices, exemplaires


# ----------------------------------------------------------------------------
# Normalisation des séries -- pondérée par l'ensemble base + nouveau fichier
# ----------------------------------------------------------------------------
def construire_normalisation(cur, notices_nouvelles):
    formes = defaultdict(Counter)

    cur.execute("SELECT serie, COUNT(*) FROM notice WHERE serie IS NOT NULL GROUP BY serie")
    for serie, n in cur.fetchall():
        formes[serie.lower().strip(' .')][serie] += n

    for n in notices_nouvelles:
        if n['serie_brute']:
            formes[n['serie_brute'].lower().strip(' .')][n['serie_brute']] += 1

    return {forme: compteur.most_common(1)[0][0] for forme, compteur in formes.items()}


def construire_normalisation_editeur(cur, notices_nouvelles):
    formes = defaultdict(Counter)
    cur.execute("SELECT editeur, COUNT(*) FROM notice WHERE editeur IS NOT NULL GROUP BY editeur")
    for editeur, n in cur.fetchall():
        formes[editeur.lower().strip(' .')][editeur] += n
    for n in notices_nouvelles:
        if n['editeur']:
            formes[n['editeur'].lower().strip(' .')][n['editeur']] += 1
    return {forme: compteur.most_common(1)[0][0] for forme, compteur in formes.items()}


def reharmoniser_par_serie(cur, champ):
    cur.execute(f"SELECT identifiant, serie, {champ} FROM notice WHERE serie IS NOT NULL AND {champ} IS NOT NULL AND {champ} != ''")
    lignes = cur.fetchall()
    par_serie = defaultdict(Counter)
    for identifiant, serie, valeur in lignes:
        par_serie[serie][valeur] += 1
    gagnants = {s: c.most_common(1)[0][0] for s, c in par_serie.items()}
    n = 0
    for identifiant, serie, valeur in lignes:
        gagnant = gagnants[serie]
        if valeur != gagnant:
            cur.execute(f"UPDATE notice SET {champ} = ? WHERE identifiant = ?", (gagnant, identifiant))
            n += 1
    return n


# ----------------------------------------------------------------------------
# Date du fichier -- les exports Decalog portent la date du jour dans leur
# nom ("Liste des notices - 2026-06-27.mrc"). On s'en sert pour savoir de
# quand date le catalogue en base, et pour repérer un import fait par erreur
# avec un fichier plus ancien que celui déjà traité.
# ----------------------------------------------------------------------------
def extraire_date_fichier(chemin):
    nom = os.path.basename(chemin)
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', nom)
    if m:
        return m.group(0)
    return None


def verifier_et_enregistrer_date(cur, date_fichier, cle="date_dernier_catalogue"):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS etat_imports (
            cle TEXT PRIMARY KEY,
            valeur TEXT,
            date_maj TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    if not date_fichier:
        print("  (date non détectée dans le nom du fichier -- pas de vérification de fraîcheur)")
        return
    cur.execute("SELECT valeur FROM etat_imports WHERE cle = ?", (cle,))
    row = cur.fetchone()
    date_precedente = row[0] if row else None
    if date_precedente and date_fichier < date_precedente:
        print(f"  ⚠ ATTENTION : ce fichier est daté du {date_fichier}, "
              f"plus ancien que le dernier catalogue importé ({date_precedente}). "
              f"Tu importes peut-être le mauvais fichier par erreur.")
    elif date_precedente == date_fichier:
        print(f"  (même date que le dernier import : {date_fichier} -- ré-import, pas un souci)")
    else:
        print(f"  Catalogue daté du {date_fichier}"
              + (f" (précédent : {date_precedente})" if date_precedente else "") + ".")
    cur.execute("""
        INSERT INTO etat_imports (cle, valeur, date_maj) VALUES (?, ?, datetime('now'))
        ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur, date_maj = excluded.date_maj
    """, (cle, date_fichier))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fichier_mrc")
    args = parser.parse_args()

    print(f"Lecture de {args.fichier_mrc}...")
    notices, exemplaires = parser_mrc(args.fichier_mrc)
    print(f"  {len(notices)} notices, {len(exemplaires)} exemplaires lus")

    conn = db.connect(FICHIER_DB)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    date_fichier = extraire_date_fichier(args.fichier_mrc)
    verifier_et_enregistrer_date(cur, date_fichier)
    conn.commit()

    normalisation = construire_normalisation(cur, notices)
    normalisation_editeur = construire_normalisation_editeur(cur, notices)

    cur.execute("SELECT identifiant FROM notice")
    identifiants_existants = {r[0] for r in cur.fetchall()}

    inseres, mis_a_jour, ignores = 0, 0, 0
    deja_vus_ce_fichier = set()

    for n in notices:
        ident = n['identifiant']
        if not ident or ident in deja_vus_ce_fichier:
            ignores += 1
            continue
        deja_vus_ce_fichier.add(ident)

        serie_finale = None
        if n['serie_brute']:
            forme = n['serie_brute'].lower().strip(' .')
            serie_finale = normalisation.get(forme, n['serie_brute'])

        editeur_final = n['editeur']
        if editeur_final:
            forme_ed = editeur_final.lower().strip(' .')
            editeur_final = normalisation_editeur.get(forme_ed, editeur_final)

        if ident in identifiants_existants:
            cur.execute("""
                UPDATE notice SET titre = COALESCE(?, titre), serie = COALESCE(?, serie),
                    tome = COALESCE(?, tome), editeur = COALESCE(?, editeur),
                    date_publication = COALESCE(?, date_publication),
                    resume = COALESCE(resume, ?), image_url = COALESCE(image_url, ?),
                    categorie = COALESCE(categorie, ?), genre = COALESCE(genre, ?),
                    public_vise = COALESCE(public_vise, ?),
                    createurs_secondaires = COALESCE(createurs_secondaires, ?),
                    traducteur = COALESCE(traducteur, ?),
                    dewey = COALESCE(dewey, ?), dewey_libelle = COALESCE(dewey_libelle, ?),
                    mots_cles = COALESCE(mots_cles, ?),
                    description_physique = COALESCE(description_physique, ?),
                    age_recommande = COALESCE(age_recommande, ?)
                WHERE identifiant = ?
            """, (n['titre'], serie_finale, n['tome'], editeur_final, n['date_publication'],
                  n['resume'], n['image_url'], n['categorie_decalog'], n['genre_decalog'],
                  n['public_hint'], n['illustrateur'], n['traducteur'], n['dewey'],
                  n['dewey_libelle'], n['mots_cles'], n['description_physique'],
                  n['age_recommande'], ident))
            mis_a_jour += 1
        else:
            cur.execute("""
                INSERT INTO notice (identifiant, type_document, titre, serie, tome,
                                     createurs, createurs_secondaires, traducteur, editeur,
                                     date_publication, resume, image_url, categorie, genre,
                                     public_vise, dewey, dewey_libelle, mots_cles,
                                     description_physique, age_recommande)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ident, n['type_document'], n['titre'], serie_finale, n['tome'],
                  n['auteur'], n['illustrateur'], n['traducteur'], editeur_final,
                  n['date_publication'], n['resume'], n['image_url'], n['categorie_decalog'],
                  n['genre_decalog'], n['public_hint'], n['dewey'], n['dewey_libelle'],
                  n['mots_cles'], n['description_physique'], n['age_recommande']))
            identifiants_existants.add(ident)
            inseres += 1
            if ident.startswith('CB:'):
                print(f"  ⚠ Notice sans EAN acceptée (id substitut {ident}) : {n['titre']!r} — à corriger dans Decalog")

    conn.commit()
    # Compter les notices entrées sans EAN cette session
    n_sans_ean = sum(1 for n in notices if (n.get('identifiant') or '').startswith('CB:'))
    print(f"\nNotices : {inseres} nouvelles, {mis_a_jour} mises à jour, {ignores} ignorées (sans identifiant/doublon)")
    if n_sans_ean:
        print(f"  dont {n_sans_ean} sans EAN Decalog (identifiant CB: substitut) — liste ci-dessus")

    # --- Exemplaires : upsert par code-barres, sans jamais toucher prix/prêts ---
    inseres_ex, maj_ex, ignores_ex = 0, 0, 0
    for ex in exemplaires:
        ident = ex['identifiant']
        cb = (ex.get('code_barres') or '').strip() or None
        if not ident or not cb or ident not in identifiants_existants:
            ignores_ex += 1
            continue
        cur.execute("""
            INSERT INTO exemplaire (identifiant, cote, code_barre_exemplaire, date_acquisition,
                                     statut, site, public_vise, support)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code_barre_exemplaire) DO UPDATE SET
                identifiant = excluded.identifiant, cote = excluded.cote,
                date_acquisition = excluded.date_acquisition, statut = excluded.statut,
                site = excluded.site, public_vise = excluded.public_vise,
                support = excluded.support
        """, (ident, ex.get('cote'), cb, ex.get('date_inventaire'), ex.get('statut'),
              ex.get('site'), ex.get('public_vise'), ex.get('support')))
        if cur.rowcount:
            inseres_ex += 1

    conn.commit()
    print(f"Exemplaires : {inseres_ex} insérés/mis à jour, {ignores_ex} ignorés (sans code-barres/notice)")

    # --- Réharmonisation finale ---
    n_pv = reharmoniser_par_serie(cur, 'public_vise')
    n_cat = reharmoniser_par_serie(cur, 'categorie')
    n_genre = reharmoniser_par_serie(cur, 'genre')
    conn.commit()
    print(f"\nRéharmonisation par série : public={n_pv}, type={n_cat}, genre={n_genre}")

    n_ed = 0
    cur.execute("SELECT identifiant, editeur FROM notice WHERE editeur IS NOT NULL")
    for identifiant, editeur in cur.fetchall():
        forme = editeur.lower().strip(' .')
        gagnant = normalisation_editeur.get(forme, editeur)
        if gagnant != editeur:
            cur.execute("UPDATE notice SET editeur = ? WHERE identifiant = ?", (gagnant, identifiant))
            n_ed += 1
    conn.commit()
    print(f"Éditeurs renormalisés sur l'existant : {n_ed}")

    cur.execute("SELECT COUNT(*) FROM notice")
    print(f"\nTotal notices en base : {cur.fetchone()[0]}")
    conn.close()


if __name__ == "__main__":
    main()
