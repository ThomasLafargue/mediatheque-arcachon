#!/usr/bin/env python3
"""
Initialise la table horaires_ouverture avec les horaires de la médiathèque.

Deux périodes :
  - Juillet-Août    : lundi au samedi, 10h-19h
  - Reste de l'année : mardi au samedi, 10h-18h
  (Le lundi hors été = fermé au public, agents présents en interne)

Usage : python3 initialiser_horaires.py
"""
import db

conn = db.connect()
conn.execute("""
    CREATE TABLE IF NOT EXISTS horaires_ouverture (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        periode         TEXT NOT NULL,  -- 'annee' ou 'ete'
        mois_debut      INTEGER NOT NULL,
        mois_fin        INTEGER NOT NULL,
        jour_semaine    INTEGER NOT NULL,  -- 0=lundi ... 6=dimanche
        heure_ouverture TEXT NOT NULL,     -- ex. '10:00'
        heure_fermeture TEXT NOT NULL,     -- ex. '18:00'
        ouvert_public   INTEGER NOT NULL DEFAULT 1,  -- 0 si agents seulement
        note            TEXT
    )
""")

# Vider et réinsérer pour éviter les doublons
conn.execute("DELETE FROM horaires_ouverture")

horaires = [
    # Période estivale : juillet (7) - août (8), lundi au samedi
    ("ete", 7, 8, 0, "10:00", "19:00", 1, "Lundi été — ouvert au public"),
    ("ete", 7, 8, 1, "10:00", "19:00", 1, "Mardi été"),
    ("ete", 7, 8, 2, "10:00", "19:00", 1, "Mercredi été"),
    ("ete", 7, 8, 3, "10:00", "19:00", 1, "Jeudi été"),
    ("ete", 7, 8, 4, "10:00", "19:00", 1, "Vendredi été"),
    ("ete", 7, 8, 5, "10:00", "19:00", 1, "Samedi été"),

    # Reste de l'année : mardi au samedi, 10h-18h
    ("annee", 1, 6,  1, "10:00", "18:00", 1, "Mardi"),
    ("annee", 1, 6,  2, "10:00", "18:00", 1, "Mercredi"),
    ("annee", 1, 6,  3, "10:00", "18:00", 1, "Jeudi"),
    ("annee", 1, 6,  4, "10:00", "18:00", 1, "Vendredi"),
    ("annee", 1, 6,  5, "10:00", "18:00", 1, "Samedi"),
    ("annee", 9, 12, 1, "10:00", "18:00", 1, "Mardi"),
    ("annee", 9, 12, 2, "10:00", "18:00", 1, "Mercredi"),
    ("annee", 9, 12, 3, "10:00", "18:00", 1, "Jeudi"),
    ("annee", 9, 12, 4, "10:00", "18:00", 1, "Vendredi"),
    ("annee", 9, 12, 5, "10:00", "18:00", 1, "Samedi"),

    # Lundi hors été : fermé au public, agents présents
    ("annee", 1, 6,  0, "10:00", "18:00", 0, "Lundi — agents uniquement, fermé au public"),
    ("annee", 9, 12, 0, "10:00", "18:00", 0, "Lundi — agents uniquement, fermé au public"),
]

for h in horaires:
    conn.execute("""
        INSERT INTO horaires_ouverture
        (periode, mois_debut, mois_fin, jour_semaine, heure_ouverture, heure_fermeture, ouvert_public, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, h)
conn.commit()

print(f"Table horaires_ouverture créée avec {len(horaires)} règles.")
print()
print("Résumé :")
for r in conn.execute("SELECT periode, mois_debut, mois_fin, jour_semaine, heure_ouverture, heure_fermeture, ouvert_public FROM horaires_ouverture ORDER BY mois_debut, jour_semaine").fetchall():
    jours = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    public = "public" if r[6] else "agents seulement"
    print(f"  Mois {r[1]:02d}-{r[2]:02d} | {jours[r[3]]} | {r[4]}-{r[5]} | {public}")
conn.close()
