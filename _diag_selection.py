#!/usr/bin/env python3
"""
_diag_selection.py — Trouve l'URL de l'onglet « Sélection » (= coups de cœur)
par rayon sur Place des Libraires, à partir de la page rayon jeunesse.
Objectif : cibler la sélection JEUNESSE (et BD, romans...) plutôt que la page
générale, majoritairement adulte.
"""
import sys
sys.path.insert(0, ".")
import db  # noqa: F401 — correctif SSL
import re

import requests
from bs4 import BeautifulSoup

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

BASE = "https://www.placedeslibraires.fr"
PAGE_RAYON = f"{BASE}/jeunesse/ssh-1277"

print("=" * 70)
print("PAGE RAYON JEUNESSE — liens contenant 'selection' / 'coup'")
print("=" * 70)
try:
    r = requests.get(PAGE_RAYON, headers=UA, timeout=20, allow_redirects=True)
    print(f"  HTTP {r.status_code} | {len(r.text)} octets | URL finale : {r.url}")
    soup = BeautifulSoup(r.text, "html.parser")

    interessants = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        txt = re.sub(r"\s+", " ", a.get_text(strip=True))[:40]
        if re.search(r"select|coup|coeur|cœur", href + " " + txt, re.I):
            interessants.append((txt, href))
    vus = set()
    for txt, href in interessants:
        if href in vus:
            continue
        vus.add(href)
        print(f"    {txt!r:42} → {href[:70]}")
    if not interessants:
        print("    (aucun lien 'sélection' détecté sur cette page)")

    # combien de fiches livres sur la page rayon elle-même ?
    isbns = {m.group(1) for a in soup.select("a[href*='/livre/']")
             for m in [re.search(r"/livre/(\d{9,13})", a.get("href", ""))] if m}
    print(f"\n  fiches livres directement sur la page rayon : {len(isbns)}")
except Exception as e:
    print(f"  ✗ {type(e).__name__}: {str(e)[:70]}")

print()
print("=" * 70)
print("URL CANDIDATES POUR LA SÉLECTION JEUNESSE")
print("=" * 70)
CANDIDATES = [
    f"{BASE}/jeunesse/ssh-1277/selection",
    f"{BASE}/jeunesse/ssh-1277/selection/",
    f"{BASE}/selection/jeunesse/ssh-1277",
    f"{BASE}/coups-de-coeur/jeunesse/ssh-1277",
    f"{BASE}/jeunesse/ssh-1277?tab=selection",
]
for url in CANDIDATES:
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
        soup = BeautifulSoup(r.text, "html.parser")
        isbns = {m.group(1) for a in soup.select("a[href*='/livre/']")
                 for m in [re.search(r"/livre/(\d{9,13})", a.get("href", ""))] if m}
        t = soup.find("title")
        print(f"  HTTP {r.status_code} | {len(isbns):3} fiches | {url[:62]}")
        if t:
            print(f"       <title>={t.get_text(strip=True)[:70]!r}")
    except Exception as e:
        print(f"  ✗ {type(e).__name__} | {url[:62]}")

print("\n✓ Diagnostic terminé.")
