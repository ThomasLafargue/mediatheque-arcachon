import db

conn = db.connect()
cur = conn.cursor()

print("=== Toutes les notices dont la série contient 'aruto' (table notice) ===")
for r in cur.execute("""
    SELECT identifiant, titre, serie, tome, type_document
    FROM notice WHERE serie LIKE '%aruto%'
    ORDER BY CAST(tome AS INTEGER)
""").fetchall():
    print(" ", r)

print("\n=== Présence d'exemplaire pour chaque tome (LEFT JOIN, comme vue_inventaire) ===")
for r in cur.execute("""
    SELECT n.tome, n.identifiant, e.code_barre_exemplaire, e.cote, e.statut
    FROM notice n LEFT JOIN exemplaire e ON e.identifiant = n.identifiant
    WHERE n.serie LIKE '%aruto%'
    ORDER BY CAST(n.tome AS INTEGER)
""").fetchall():
    print(" ", r)

print("\n=== Spécifiquement tome 61 et 68 ===")
for r in cur.execute("SELECT * FROM notice WHERE serie LIKE '%aruto%' AND tome IN ('61', '68')").fetchall():
    print(" ", r)

conn.close()
