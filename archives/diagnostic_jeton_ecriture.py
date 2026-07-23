import sys
import db

if len(sys.argv) < 2:
    print("Usage : python3 diagnostic_jeton_ecriture.py <jeton>")
    sys.exit(1)

JETON = sys.argv[1]

print("URL utilisée :", db.TURSO_URL)
print("Connexion avec le jeton fourni...")
conn = db.connect_avec_jeton(db.TURSO_URL, JETON)
print("Connexion établie. Insertion...")
conn.execute("INSERT INTO suggestion_acquisition (titre, demandeur) VALUES (?, ?)",
             ("Test connect_avec_jeton", "Thomas"))
conn.commit()
print("OK :", conn.execute("SELECT COUNT(*) FROM suggestion_acquisition").fetchone())
conn.close()
