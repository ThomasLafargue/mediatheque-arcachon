#!/usr/bin/env python3
"""
Test de toutes les connexions/API du projet MAAT en une seule commande.
À lancer depuis le Mac local (le sandbox Claude ne peut pas atteindre
ces domaines -- réseau restreint) :

    cd ~/Desktop/inventaire_isbn
    python3 test_connexions.py

N'affiche jamais les jetons/clés, seulement OK/FAIL + détail.
"""
import os, sys, time, json
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []

def test(name, fn):
    t0 = time.time()
    try:
        detail = fn()
        results.append((name, "OK", f"{time.time()-t0:.2f}s", detail))
    except Exception as e:
        results.append((name, "FAIL", f"{time.time()-t0:.2f}s", str(e)[:200]))

def t_turso():
    import db
    conn = db.connect()
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM notice")
    n = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM exemplaire")
    n2 = cur.fetchone()[0]
    conn.close()
    return f"notice={n}, exemplaire={n2}, mode_en_ligne={db.MODE_EN_LIGNE}"
test("Turso (lecture, db.py)", t_turso)

def t_turso_ecriture():
    import db
    jeton = os.environ.get("TURSO_AUTH_TOKEN_ECRITURE")
    if not jeton:
        raise RuntimeError("TURSO_AUTH_TOKEN_ECRITURE absent de .env")
    conn = db.connect_avec_jeton(db.TURSO_URL, jeton)
    conn.execute("SELECT 1")
    conn.close()
    return "jeton d'écriture valide"
test("Turso (écriture)", t_turso_ecriture)

def t_google():
    key = os.environ.get("GOOGLE_BOOKS_API_KEY", "")
    if not key:
        raise RuntimeError("clé absente de .env")
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:9782070612758&key={key}"
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.loads(r.read())
    return f"totalItems={d.get('totalItems')}"
test("Google Books API", t_google)

def t_bnf():
    url = "https://catalogue.bnf.fr/api/SRU?version=1.2&operation=searchRetrieve&query=bib.isbn%3D9782070612758&maximumRecords=1"
    with urllib.request.urlopen(url, timeout=15) as r:
        d = r.read()
    return f"{len(d)} octets reçus"
test("BnF SRU", t_bnf)

def t_meteo():
    url = ("https://archive-api.open-meteo.com/v1/archive?latitude=44.65&longitude=-1.17"
           "&start_date=2026-07-01&end_date=2026-07-02&daily=precipitation_sum&timezone=Europe%2FParis")
    with urllib.request.urlopen(url, timeout=15) as r:
        d = json.loads(r.read())
    return f"daily keys={list(d.get('daily', {}).keys())}"
test("Open-Meteo archive", t_meteo)

def t_openlib():
    url = "https://covers.openlibrary.org/b/isbn/9782070612758-M.jpg"
    req = urllib.request.Request(url, method="HEAD")
    with urllib.request.urlopen(req, timeout=15) as r:
        return f"status={r.status}, content-type={r.headers.get('Content-Type')}"
test("Open Library covers", t_openlib)

def t_geobib():
    url = "https://couverture.geobib.fr/"
    with urllib.request.urlopen(url, timeout=10) as r:
        return f"status={r.status}"
test("Geobib (couvertures, connu abandonné)", t_geobib)

print()
print(f"{'API':35} {'Statut':6} {'Durée':8} Détail")
print("-" * 100)
for name, statut, duree, detail in results:
    icone = "✅" if statut == "OK" else "❌"
    print(f"{icone} {name:33} {statut:6} {duree:8} {detail}")
print()
