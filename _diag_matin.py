#!/usr/bin/env python3
"""
_diag_matin.py — 1) point d'avancement de l'enrichissement des séries,
                 2) structure de la page « coups de cœur » de Place des
                    Libraires, pour écrire un parseur correct.
Lecture seule sur la base. Ponctuel.
"""
import sys
sys.path.insert(0, ".")
import db
import re

import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

print("=" * 70)
print("1. AVANCEMENT DE L'ENRICHISSEMENT DES SÉRIES")
print("=" * 70)
conn = db.connect()
try:
    total_livre = conn.execute(
        "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE'").fetchall()[0][0]
    sans_serie = conn.execute(
        "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' AND serie IS NULL "
        "AND identifiant NOT LIKE 'CB:%'").fetchall()[0][0]
    avec_serie = conn.execute(
        "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' AND serie IS NOT NULL "
        "AND serie != ''").fetchall()[0][0]
    avec_tome = conn.execute(
        "SELECT COUNT(*) FROM notice WHERE type_document='LIVRE' AND tome IS NOT NULL "
        "AND tome != ''").fetchall()[0][0]
    nb_series = conn.execute(
        "SELECT COUNT(*) FROM (SELECT serie FROM notice WHERE serie IS NOT NULL "
        "AND serie != '' GROUP BY serie)").fetchall()[0][0]
    print(f"  Total notices LIVRE            : {total_livre}")
    print(f"  Avec série renseignée          : {avec_serie}")
    print(f"  Avec tome renseigné            : {avec_tome}")
    print(f"  Séries distinctes              : {nb_series}")
    print(f"  ENCORE SANS SÉRIE              : {sans_serie}")
    print()
    print("  (rappel : 17 970 sans série au lancement de l'enrichissement)")
finally:
    conn.close()

print()
print("=" * 70)
print("2. STRUCTURE DE LA PAGE « COUPS DE CŒUR » (Place des Libraires)")
print("=" * 70)
for url in ["https://www.placedeslibraires.fr/coups-de-coeur/",
            "https://www.placedeslibraires.fr/nouveautes/"]:
    print(f"\n-- {url}")
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
        print(f"   HTTP {r.status_code} | {len(r.text)} octets")
        if r.status_code != 200:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        liens = soup.select("a[href*='/livre/']")
        print(f"   liens vers des fiches livres : {len(liens)}")
        vus = set()
        for a in liens[:12]:
            href = a.get("href", "")
            txt = re.sub(r"\s+", " ", a.get_text(strip=True))[:60]
            m = re.search(r"/livre/(\d{9,13})", href)
            isbn = m.group(1) if m else "?"
            if href in vus:
                continue
            vus.add(href)
            print(f"     isbn={isbn:14} texte={txt!r}")
        # classes utiles pour cibler les blocs
        blocs = soup.select("[class*='product'], [class*='book'], [class*='item']")
        classes = {}
        for b in blocs[:200]:
            for c in (b.get("class") or []):
                classes[c] = classes.get(c, 0) + 1
        top = sorted(classes.items(), key=lambda x: -x[1])[:10]
        print(f"   classes fréquentes : {top}")
    except Exception as e:
        print(f"   ✗ {type(e).__name__}: {str(e)[:60]}")

print("\n✓ Diagnostic terminé.")
