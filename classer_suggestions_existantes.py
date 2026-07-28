#!/usr/bin/env python3
"""
classer_suggestions_existantes.py — Complète rétroactivement le classement
(catégorie / public / genre) des suggestions d'acquisition déjà en base.

Contexte (2026-07-25) : les colonnes categorie/public_vise/genre ont été
ajoutées à suggestion_acquisition pour permettre de filtrer les suggestions
par segment dans l'interface (BD jeunesse, manga adulte, romans ado...).
Les suggestions enregistrées AVANT cet ajout n'ont pas ces informations et
apparaissent en « — ». Ce script les complète.

Deux méthodes, dans cet ordre :
  1. si la suggestion a un ISBN -> interrogation du moteur de recherche
     (Place des Libraires en tête), qui déduit type/public/genre ;
  2. sinon -> déduction depuis le motif et le titre (mots-clés), moins
     précise mais suffisante pour filtrer.

N'écrase jamais une valeur déjà renseignée. Idempotent : relançable sans
risque, il ne traite que ce qui manque.

Usage :
    python3 classer_suggestions_existantes.py
    python3 classer_suggestions_existantes.py --max 20
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db


def _connexion_ecriture():
    jeton = os.environ.get("TURSO_AUTH_TOKEN_ECRITURE")
    if not jeton or not db.MODE_EN_LIGNE:
        return None
    return db.connect_avec_jeton(db.TURSO_URL, jeton)


def deduire_depuis_texte(titre, motif):
    """Repli sans ISBN : déduit un classement grossier depuis les mots du
    titre et de la sélection d'origine."""
    texte = f"{titre or ''} {motif or ''}".lower()
    categorie = public = genre = None

    if any(m in texte for m in ("manga", "shonen", "shôlen", "shojo", "shôjo",
                                "seinen", "webtoon")):
        categorie = "Manga"
    elif any(m in texte for m in ("bd", "bande dessinée", "bandes dessinées",
                                  "comics", "roman graphique")):
        categorie = "BD"
    elif any(m in texte for m in ("album", "tout-carton", "imagier",
                                  "livre illustré")):
        categorie = "Album"
    elif any(m in texte for m in ("documentaire", "essai", "encyclopéd",
                                  "atlas", "guide")):
        categorie = "Documentaire"
    elif any(m in texte for m in ("conte", "comptine", "poésie", "poèmes")):
        categorie = "Conte / Poésie"
    elif any(m in texte for m in ("première lecture", "premières lectures",
                                  "lecteur débutant")):
        categorie = "Première lecture"
    elif "roman" in texte:
        categorie = "Roman"

    if any(m in texte for m in ("adolescent", "ado ", "ados", "young adult", " ya ")):
        public = "Adolescent"
    elif any(m in texte for m in ("jeunesse", "enfant", "tout-petit", "petits")):
        public = "Jeunesse"  # valeur canonique (normalisation 2026-07-27)

    if "policier" in texte or "polar" in texte or "thriller" in texte:
        genre = "Policier"
    elif "fantasy" in texte or "fantastique" in texte:
        genre = "Fantastique"
    elif "science-fiction" in texte or " sf " in texte:
        genre = "Science-fiction"

    return categorie, public, genre


def deduire_depuis_source(source):
    """Étage 3 (2026-07-27) : la SOURCE de veille détermine le public quand
    ni l'ISBN ni le texte n'ont parlé. Une critique Ricochet ou un prix
    jeunesse concernent la jeunesse par construction — c'est la nature de la
    source, pas une déduction."""
    s = (source or "").lower()
    if "ricochet" in s or "jeunesse" in s:
        return "Jeunesse"
    return None


# Étage 4, le filet : demandé par Thomas les 2026-07-27 et 28 — TOUTES les
# suggestions doivent avoir un public, une catégorie ET un genre ; le
# panneau de tri ne doit plus afficher de « — ». Les valeurs par défaut
# sont des aveux honnêtes qu'on ne sait pas trancher : mieux vaut ça qu'une
# valeur devinée à tort, et la suggestion reste visible dans les filtres.
PUBLIC_PAR_DEFAUT = "Tout public"
# « Livre » avait été choisi le 2026-07-28 et aussitôt retoqué par Thomas :
# tout est un livre, ça n'aide personne. « À classer » dit ce que c'est —
# une catégorie à trancher par un humain — sans polluer Roman/BD/Manga.
CATEGORIE_PAR_DEFAUT = "À classer"
GENRE_PAR_DEFAUT = "À préciser"       # à affiner par le bibliothécaire


def main():
    maxi = None
    if "--max" in sys.argv:
        try:
            maxi = int(sys.argv[sys.argv.index("--max") + 1])
        except (IndexError, ValueError):
            pass

    conn = _connexion_ecriture()
    if conn is None:
        print("TURSO_AUTH_TOKEN_ECRITURE absent ou base locale -- rien à faire.")
        return

    try:
        # migration de sécurité si les colonnes n'existent pas encore
        for colonne in ("categorie", "public_vise", "genre"):
            try:
                conn.execute(f"ALTER TABLE suggestion_acquisition ADD COLUMN {colonne} TEXT")
                conn.commit()
            except Exception:
                pass

        # Rattrapage du faux pas « Livre » (2026-07-28) : on remet ces
        # catégories à zéro pour que la vraie détermination (ISBN, puis
        # mots-clés) soit retentée. Sans effet dès la seconde exécution.
        conn.execute("UPDATE suggestion_acquisition SET categorie = NULL "
                     "WHERE categorie IN ('Livre', 'À classer')")
        conn.commit()

        lignes = conn.execute(
            "SELECT id, titre, isbn, motif, source FROM suggestion_acquisition "
            "WHERE (categorie IS NULL OR categorie = '') "
            "   OR (public_vise IS NULL OR public_vise = '') "
            "   OR (genre IS NULL OR genre = '')"
        ).fetchall()

        if not lignes:
            print("Toutes les suggestions sont déjà classées.")
            return

        print(f"{len(lignes)} suggestion(s) à classer.\n")
        if maxi:
            lignes = lignes[:maxi]

        try:
            import moteur_recherche as m
        except Exception:
            m = None

        try:
            from retrouver_ean_manquants import chercher_ean
        except Exception:
            chercher_ean = None

        classees_isbn = classees_titre = classees_texte = 0
        classees_source = par_defaut = 0
        for sid, titre, isbn, motif, source in lignes:
            categorie = public = genre = None
            isbn_trouve = None

            # Étage 1 : l'ISBN mène directement à la fiche
            if isbn and m:
                try:
                    res = m.placedeslibraires_lookup(str(isbn).replace("-", "").strip())
                except Exception:
                    res = None
                if res:
                    categorie = res.get("type") or None
                    public = res.get("public") or None
                    genre = res.get("genre") or None
                    if categorie or public:
                        classees_isbn += 1
                time.sleep(0.4)

            # Étage 2 (2026-07-28, exigence de Thomas : « c'est facile de
            # savoir ce que c'est ») : sans ISBN — ou fiche muette — on
            # RETROUVE la fiche par titre + auteur, comme pour les EAN
            # manquants. La fiche donne catégorie/public/genre, et on
            # garde l'ISBN au passage : la suggestion en sort complète.
            if not categorie and titre and m and chercher_ean:
                try:
                    isbn_trouve, _, _ = chercher_ean(titre, None)
                    if isbn_trouve:
                        res = m.placedeslibraires_lookup(isbn_trouve)
                        if res:
                            categorie = categorie or res.get("type") or None
                            public = public or res.get("public") or None
                            genre = genre or res.get("genre") or None
                            if categorie:
                                classees_titre += 1
                except Exception:
                    pass
                time.sleep(0.4)

            # Étage 3 : mots-clés du titre et du motif
            if not (categorie or public):
                categorie, public, genre = deduire_depuis_texte(titre, motif)
                if categorie or public:
                    classees_texte += 1

            if not public:
                public = deduire_depuis_source(source)
                if public:
                    classees_source += 1
            if not public:
                public = PUBLIC_PAR_DEFAUT
                par_defaut += 1
            if not categorie:
                categorie = CATEGORIE_PAR_DEFAUT
            if not genre:
                genre = GENRE_PAR_DEFAUT

            # normalisation systématique (les sources web renvoient parfois
            # « Jeune », « Ado (12+) », « Romance » seul...)
            from public_vise import normaliser as _norm
            from proposer_fusion_genres import proposer as _canon
            public = _norm(public)
            genre = _canon(genre)[0] if genre != GENRE_PAR_DEFAUT else genre

            conn.execute(
                "UPDATE suggestion_acquisition SET "
                "  categorie = COALESCE(NULLIF(categorie,''), ?), "
                "  public_vise = COALESCE(NULLIF(public_vise,''), ?), "
                "  genre = COALESCE(NULLIF(genre,''), ?), "
                "  isbn = COALESCE(NULLIF(isbn,''), ?) "
                "WHERE id = ?",
                (categorie, public, genre, isbn_trouve, sid),
            )
            print(f"  #{sid} {str(titre)[:42]:42} → "
                  f"{categorie or '—'} / {public or '—'} / {genre or '—'}"
                  + (f"  [ISBN retrouvé : {isbn_trouve}]" if isbn_trouve else ""))

        conn.commit()
        print(f"\n✓ Terminé : {classees_isbn} via ISBN, "
              f"{classees_titre} via recherche titre+auteur, "
              f"{classees_texte} via mots-clés, {classees_source} via la "
              f"source. Restent indéterminées : celles marquées "
              f"« {CATEGORIE_PAR_DEFAUT} ».")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
