#!/usr/bin/env python3
"""
_diag_rayons.py — Trouve les pages de RAYON de Place des Libraires (format
/xxx/ssh-NNNN) et les sélections (/list-NNNN/slug/) qu'elles contiennent.
Les sélections n'apparaissent pas sur /liste_selections.php mais sur les
pages de rayon.
"""
import sys
sys.path.insert(0, ".")
import db  # noqa: F401
import re
import time

import requests
from bs4 import BeautifulSoup

BASE = "https://www.placedeslibraires.fr"
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
        return r if r.status_code == 200 else None
    except Exception:
        return None


print("=" * 70)
print("1. QUE CONTIENT /liste_selections.php ?")
print("=" * 70)
r = get(f"{BASE}/liste_selections.php")
if r:
    soup = BeautifulSoup(r.text, "html.parser")
    t = soup.find("title")
    print(f"  HTTP 200 | {len(r.text)} o | <title>={t.get_text(strip=True)[:60]!r}" if t else "")
    listes = {a['href'] for a in soup.find_all('a', href=True) if re.search(r"/list-\d+/", a['href'])}
    print(f"  liens /list-NNNN/ : {len(listes)}")
    for h in list(listes)[:10]:
        print(f"     {h[:70]}")
    ssh = {a['href'] for a in soup.find_all('a', href=True) if re.search(r"/ssh-\d+", a['href'])}
    print(f"  liens rayon /ssh-NNNN : {len(ssh)}")
else:
    print("  inaccessible")

print()
print("=" * 70)
print("2. PAGES DE RAYON TROUVÉES DEPUIS L'ACCUEIL")
print("=" * 70)
rayons = {}
r = get(BASE + "/")
if r:
    soup = BeautifulSoup(r.text, "html.parser")
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if re.search(r"/ssh-\d+", h):
            url = h if h.startswith("http") else BASE + h
            nom = re.sub(r"\s+", " ", a.get_text(strip=True))[:40] or url.split("/")[-2]
            rayons.setdefault(url, nom)
print(f"  {len(rayons)} rayon(s) détecté(s)")
for url, nom in list(rayons.items())[:25]:
    print(f"     {nom[:38]:38} {url[len(BASE):][:45]}")

print()
print("=" * 70)
print("3. SÉLECTIONS PRÉSENTES SUR CHAQUE RAYON")
print("=" * 70)
toutes = {}
for url, nom in list(rayons.items())[:12]:
    rr = get(url)
    if not rr:
        print(f"  {nom[:30]:30} inaccessible")
        continue
    s = BeautifulSoup(rr.text, "html.parser")
    trouvees = []
    for a in s.find_all("a", href=True):
        if re.search(r"/list-\d+/", a["href"]):
            u = a["href"] if a["href"].startswith("http") else BASE + a["href"]
            lib = re.sub(r"\s+", " ", a.get_text(strip=True))[:45]
            if u not in toutes:
                toutes[u] = lib or nom
                trouvees.append((lib, u))
    print(f"  {nom[:30]:30} {len(trouvees)} sélection(s)")
    for lib, u in trouvees[:4]:
        print(f"       {lib[:42]:42} {u[len(BASE):][:40]}")
    time.sleep(0.4)

print(f"\n  TOTAL sélections distinctes trouvées : {len(toutes)}")
print("\n✓ Diagnostic terminé.")
