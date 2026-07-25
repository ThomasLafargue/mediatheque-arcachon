#!/usr/bin/env python3
"""
_carte_placedeslibraires.py — Dresse la carte du site placedeslibraires.fr.

Le site n'expose pas de plan public ; ce script en construit un en explorant
les liens internes depuis l'accueil, puis en classant ce qu'il trouve :

  • SÉLECTIONS   /list-NNNN/slug/     ← listes thématiques de libraires
                                       (prix littéraires, rentrée, pépites...)
  • RAYONS       /xxx/ssh-NNNN        ← grands rayons (jeunesse, BD, polar...)
  • RECHERCHES   /listeliv.php?...    ← listes filtrées (rayon, format, éditeur)
  • FICHES       /livre/ISBN/         ← fiches livres (non explorées : trop
                                       nombreuses, on les atteint par ISBN)
  • AUTRES       pages éditoriales, aide, etc.

Exploration polie : profondeur limitée, pause entre requêtes, pas de fiches
livres. Résultat écrit dans carte_placedeslibraires.md (lisible, versionnable).
"""
import sys
sys.path.insert(0, ".")
import db  # noqa: F401 — correctif SSL
import re
import time
from collections import defaultdict
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.placedeslibraires.fr"
UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}
PROFONDEUR_MAX = 2      # accueil -> rayons -> sélections
PAUSE = 0.5
MAX_PAGES = 60          # garde-fou : on reste courtois
SORTIE = "carte_placedeslibraires.md"


def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=20, allow_redirects=True)
        return r if r.status_code == 200 else None
    except Exception:
        return None


def classer(url):
    if re.search(r"/list-\d+/", url):
        return "SELECTIONS"
    if re.search(r"/ssh-\d+", url):
        return "RAYONS"
    if "/livre/" in url:
        return "FICHES"
    if "listeliv.php" in url:
        return "RECHERCHES"
    if "coups-de-coeur" in url:
        return "SELECTIONS"
    return "AUTRES"


trouve = defaultdict(dict)     # categorie -> {url: libelle}
visitees = set()
a_visiter = [(BASE + "/", 0)]
pages_lues = 0

print("Exploration de placedeslibraires.fr ...\n")
while a_visiter and pages_lues < MAX_PAGES:
    url, prof = a_visiter.pop(0)
    if url in visitees or prof > PROFONDEUR_MAX:
        continue
    visitees.add(url)
    r = get(url)
    pages_lues += 1
    if not r:
        continue
    print(f"  [{prof}] {url[len(BASE):][:70] or '/'}")
    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "javascript:", "#")):
            continue
        lien = urljoin(url, href)
        if urlparse(lien).netloc not in ("www.placedeslibraires.fr", "placedeslibraires.fr"):
            continue
        lien = lien.split("#")[0]
        libelle = re.sub(r"\s+", " ", a.get_text(strip=True))[:70]
        cat = classer(lien)
        if cat == "FICHES":
            continue  # on n'explore pas les fiches livres
        if lien not in trouve[cat]:
            trouve[cat][lien] = libelle
        # on ne descend que vers rayons et sélections
        if prof < PROFONDEUR_MAX and cat in ("RAYONS", "SELECTIONS") and lien not in visitees:
            a_visiter.append((lien, prof + 1))
    time.sleep(PAUSE)

# ── Écriture de la carte ──────────────────────────────────────────────
ordre = ["SELECTIONS", "RAYONS", "RECHERCHES", "AUTRES"]
titres = {
    "SELECTIONS": "Sélections de libraires  (/list-NNNN/ et coups de cœur)",
    "RAYONS": "Rayons  (/xxx/ssh-NNNN)",
    "RECHERCHES": "Listes filtrées  (/listeliv.php?...)",
    "AUTRES": "Autres pages",
}

lignes = [
    "# Carte du site placedeslibraires.fr",
    "",
    f"> Relevé automatique — {time.strftime('%Y-%m-%d')} — {pages_lues} pages explorées.",
    "> Le site n'a pas de plan public ; cette carte est reconstruite par exploration",
    "> des liens internes depuis l'accueil (profondeur 2, fiches livres exclues).",
    "",
    "Intérêt pour la médiathèque : les **sélections** sont des listes thématiques",
    "faites par des libraires (prix littéraires, rentrée, pépites jeunesse...) —",
    "c'est la matière première de la veille d'acquisition. Les **rayons** servent",
    "à cibler un domaine (jeunesse, BD, polar...) pour chaque agent.",
    "",
]
for cat in ordre:
    items = trouve.get(cat, {})
    if not items:
        continue
    lignes.append(f"## {titres[cat]}  ({len(items)})")
    lignes.append("")
    for url, lib in sorted(items.items(), key=lambda x: x[1] or x[0]):
        chemin = url[len(BASE):] or "/"
        lignes.append(f"- **{lib or '(sans libellé)'}** — `{chemin}`")
    lignes.append("")

with open(SORTIE, "w", encoding="utf-8") as f:
    f.write("\n".join(lignes))

print(f"\n✓ Carte écrite dans {SORTIE}")
for cat in ordre:
    print(f"   {titres[cat][:45]:45} {len(trouve.get(cat, {}))}")
