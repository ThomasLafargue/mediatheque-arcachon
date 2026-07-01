"""
Normalisation des valeurs synonymes dans la base.

Ce script unifie les doublons de valeurs dans les champs public_vise
et categorie, pour que des requêtes simples donnent des résultats complets
sans avoir besoin de connaître les variantes de saisie.

AVANT de lancer :
  python3 normaliser_vocabulaire.py --dry-run  (aperçu sans modifier)
PUIS si le résultat te convient :
  python3 normaliser_vocabulaire.py             (normalisation réelle)
"""

import sys
import db

DRY_RUN = "--dry-run" in sys.argv

conn = db.connect()
total_modifie = 0


def normaliser(table, champ, avant, apres, commentaire=""):
    global total_modifie
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {champ} = ?", (avant,))
    n = cur.fetchone()[0]
    if n == 0:
        return
    print(f"  {avant!r:40} → {apres!r:25} ({n} lignes) {commentaire}")
    if not DRY_RUN:
        conn.execute(f"UPDATE {table} SET {champ} = ? WHERE {champ} = ?", (apres, avant))
        total_modifie += n


print("=" * 70)
print(f"NORMALISATION DU VOCABULAIRE {'(DRY-RUN — aucune modification)' if DRY_RUN else '(RÉELLE)'}")
print("=" * 70)

print("\n── PUBLIC ──────────────────────────────────────────────────────────")
# "Adolescent" → "Ado (12+)" : même public, deux saisies différentes
normaliser("notice", "public_vise", "Adolescent", "Ado (12+)", "→ unification ado")

# "Jeunesse" → "Jeune" : même public, deux saisies différentes
# Note : on garde "Jeunesse" telle quelle car elle vient souvent du catalogage BnF
# et "Jeune" vient de Decalog — les deux coexistent légitimement dans certains cas.
# On ne les fusionne PAS pour l'instant, le chat gère les deux via synonymes.
print("  'Jeunesse' et 'Jeune' : deux valeurs conservées (origines différentes)")
print("  Le chat les gère ensemble via synonymes — pas de fusion nécessaire.")

print("\n── CATÉGORIE ────────────────────────────────────────────────────────")
# BUG CORRIGÉ : Romans adultes qui ont reçu 'Roman jeunesse' par erreur
# (le mapping COBAS ne vérifiait pas public = Adulte)
cur = conn.cursor()
cur.execute("""
    SELECT COUNT(*) FROM notice
    WHERE categorie IN ('Roman jeunesse', 'Roman ado / YA')
    AND public_vise = 'Adulte'
""")
n_adultes_mal_classes = cur.fetchone()[0]
print(f"  Romans adultes mal classés en 'Roman jeunesse/ado' → NULL : {n_adultes_mal_classes} notices")
if not DRY_RUN and n_adultes_mal_classes > 0:
    conn.execute("""
        UPDATE notice SET categorie = NULL
        WHERE categorie IN ('Roman jeunesse', 'Roman ado / YA')
        AND public_vise = 'Adulte'
    """)
    total_modifie += n_adultes_mal_classes
# Les notices avec categorie='Roman jeunesse' ET public='Ado (12+)' méritent
# d'être reclassées en 'Roman ado / YA' pour permettre des requêtes précises
cur = conn.cursor()
cur.execute("""
    SELECT COUNT(*) FROM notice
    WHERE categorie = 'Roman jeunesse'
    AND public_vise IN ('Ado (12+)', 'Adolescent')
    AND type_document = 'LIVRE'
""")
n_reclasser = cur.fetchone()[0]
print(f"  Roman jeunesse + public Ado → 'Roman ado / YA' : {n_reclasser} notices")
if not DRY_RUN and n_reclasser > 0:
    conn.execute("""
        UPDATE notice SET categorie = 'Roman ado / YA'
        WHERE categorie = 'Roman jeunesse'
        AND public_vise IN ('Ado (12+)', 'Adolescent')
        AND type_document = 'LIVRE'
    """)
    total_modifie += n_reclasser

print("\n── GENRE ────────────────────────────────────────────────────────────")
# Quelques synonymes issus de l'enrichissement
normaliser("notice", "genre", "Horreur",          "Frissons",     "→ vocabulaire jeunesse")
normaliser("notice", "genre", "Thriller",          "Policier",     "→ vocabulaire jeunesse")
normaliser("notice", "genre", "Romance",           "Amour / Romance", "→ normalisation")
normaliser("notice", "genre", "Science Fiction",   "Science-fiction", "→ normalisation")
normaliser("notice", "genre", "Sci-fi",            "Science-fiction", "→ normalisation")

if not DRY_RUN:
    conn.commit()
    print(f"\n✓ Normalisation terminée — {total_modifie} notices modifiées.")
else:
    print(f"\nDry-run terminé — {total_modifie} notices seraient modifiées.")
    print("Pour appliquer : python3 normaliser_vocabulaire.py")

conn.close()
