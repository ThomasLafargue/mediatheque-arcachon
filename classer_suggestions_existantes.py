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

    if any(m in texte for m in ("manga", "shonen", "shojo", "seinen")):
        categorie = "Manga"
    elif any(m in texte for m in ("bd", "bande dessinée", "comics", "roman graphique")):
        categorie = "BD"
    elif "album" in texte:
        categorie = "Album"
    elif any(m in texte for m in ("documentaire", "essai", "encyclopéd")):
        categorie = "Documentaire"
    elif "roman" in texte:
        categorie = "Roman"

    if any(m in texte for m in ("adolescent", "ado ", "ados", "young adult", " ya ")):
        public = "Adolescent"
    elif any(m in texte for m in ("jeunesse", "enfant", "tout-petit", "petits")):
        public = "Jeune"

    if "policier" in texte or "polar" in texte or "thriller" in texte:
        genre = "Policier"
    elif "fantasy" in texte or "fantastique" in texte:
        genre = "Fantastique"
    elif "science-fiction" in texte or " sf " in texte:
        genre = "Science-fiction"

    return categorie, public, genre


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

        lignes = conn.execute(
            "SELECT id, titre, isbn, motif FROM suggestion_acquisition "
            "WHERE (categorie IS NULL OR categorie = '') "
            "   OR (public_vise IS NULL OR public_vise = '')"
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

        classees_isbn = classees_texte = 0
        for sid, titre, isbn, motif in lignes:
            categorie = public = genre = None

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

            if not (categorie or public):
                categorie, public, genre = deduire_depuis_texte(titre, motif)
                if categorie or public:
                    classees_texte += 1

            if not (categorie or public or genre):
                continue

            conn.execute(
                "UPDATE suggestion_acquisition SET "
                "  categorie = COALESCE(NULLIF(categorie,''), ?), "
                "  public_vise = COALESCE(NULLIF(public_vise,''), ?), "
                "  genre = COALESCE(NULLIF(genre,''), ?) "
                "WHERE id = ?",
                (categorie, public, genre, sid),
            )
            print(f"  #{sid} {str(titre)[:42]:42} → "
                  f"{categorie or '—'} / {public or '—'} / {genre or '—'}")

        conn.commit()
        print(f"\n✓ Terminé : {classees_isbn} classée(s) via ISBN, "
              f"{classees_texte} via mots-clés.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
