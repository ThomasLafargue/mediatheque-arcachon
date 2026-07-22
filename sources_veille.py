"""
sources_veille.py — Sources de veille pour suggestions d'acquisition

Interroge :
- Ricochet-jeunes.org : nouveautés jeunesse francophones (RSS + scraping)
- BeDeTh-que.com     : nouveautés BD, manga, comics (scraping)
- Booknode           : thèmes, séries, meilleures ventes françaises (scraping)
- Croqulivre.fr      : chroniques jeunesse qualifiées (API REST WordPress)

Usage dans app_conversationnel.py :
    from sources_veille import chercher_nouveautes
    resultats = chercher_nouveautes(categorie='BD', nb=10)
"""

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import re
import time

TIMEOUT = (5, 10)
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
    ),
    'Accept-Language': 'fr-FR,fr;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. RICOCHET-JEUNES.ORG — Référence jeunesse francophone
# ─────────────────────────────────────────────────────────────────────────────
def _ricochet_rss():
    """Tente de lire le flux RSS de Ricochet."""
    urls_rss = [
        'https://www.ricochet-jeunes.org/rss.xml',
        'https://www.ricochet-jeunes.org/livres/rss',
        'https://www.ricochet-jeunes.org/feed',
        'https://www.ricochet-jeunes.org/articles/rss',
    ]
    for url in urls_rss:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200 and '<item>' in r.text:
                return r.text
        except Exception:
            continue
    return None


def _ricochet_scraping(nb=20):
    """Scrape les dernières notices de Ricochet si le RSS n'est pas disponible."""
    url = 'https://www.ricochet-jeunes.org/livres'
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        resultats = []
        # Les livres sont dans des éléments avec classe contenant 'livre' ou 'book'
        for item in soup.find_all(class_=re.compile(r'(livre|book|node|views-row)', re.I))[:nb]:
            titre_el = item.find(['h2', 'h3', 'h4', 'a'])
            if not titre_el:
                continue
            titre = titre_el.get_text(strip=True)
            if not titre or len(titre) < 3:
                continue
            lien = titre_el.get('href', '') if titre_el.name == 'a' else ''
            if lien and not lien.startswith('http'):
                lien = 'https://www.ricochet-jeunes.org' + lien

            # Auteur
            auteur_el = item.find(class_=re.compile(r'auteur|author', re.I))
            auteur = auteur_el.get_text(strip=True) if auteur_el else None

            # Éditeur
            editeur_el = item.find(class_=re.compile(r'editeur|publisher', re.I))
            editeur = editeur_el.get_text(strip=True) if editeur_el else None

            # Âge conseillé
            age_el = item.find(class_=re.compile(r'age|ans', re.I))
            age = age_el.get_text(strip=True) if age_el else None

            resultats.append({
                'titre': titre,
                'auteur': auteur,
                'editeur': editeur,
                'age_conseille': age,
                'url': lien,
                'source': 'Ricochet-jeunes.org',
            })

        return resultats
    except Exception:
        return []


def chercher_ricochet(nb=15, theme=None):
    """
    Retourne les dernières nouveautés jeunesse de Ricochet.
    Si theme est fourni, filtre par thème (ex: 'BD', 'Roman', 'Album').
    """
    # Essai RSS d'abord
    rss_content = _ricochet_rss()
    if rss_content:
        try:
            root = ET.fromstring(rss_content)
            items = root.findall('.//item')
            resultats = []
            for item in items[:nb]:
                titre = (item.findtext('title') or '').strip()
                lien = (item.findtext('link') or '').strip()
                desc = (item.findtext('description') or '').strip()
                # Nettoyer HTML dans description
                desc_propre = BeautifulSoup(desc, 'html.parser').get_text()[:200]
                if titre:
                    resultats.append({
                        'titre': titre,
                        'resume': desc_propre,
                        'url': lien,
                        'source': 'Ricochet-jeunes.org',
                    })
            if resultats:
                return resultats
        except ET.ParseError:
            pass

    # Fallback : scraping
    return _ricochet_scraping(nb=nb)


# ─────────────────────────────────────────────────────────────────────────────
# 2. BEDETHEQUE.COM — Nouveautés BD, Manga, Comics
# ─────────────────────────────────────────────────────────────────────────────
def chercher_bedetheque(nb=20, type_bd=None):
    """
    Récupère les nouveautés BD/Manga/Comics de BeDeTh-que.com.
    type_bd : None (tout), 'BD', 'Manga', 'Comics'
    """
    url = 'https://www.bedetheque.com/nouveautes'
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        resultats = []

        # BeDeTh-que liste les nouveautés par album avec titre, série, auteur, éditeur
        for item in soup.find_all(class_=re.compile(r'(album|nouveaute|item|ligne)', re.I))[:nb * 2]:
            titre_el = item.find(['h2', 'h3', 'h4', 'a'])
            if not titre_el:
                continue
            titre = titre_el.get_text(strip=True)
            if not titre or len(titre) < 2:
                continue

            lien = titre_el.get('href', '') if titre_el.name == 'a' else ''
            if lien and not lien.startswith('http'):
                lien = 'https://www.bedetheque.com' + lien

            # Série
            serie_el = item.find(class_=re.compile(r'serie', re.I))
            serie = serie_el.get_text(strip=True) if serie_el else None

            # Auteur/dessinateur
            auteur_el = item.find(class_=re.compile(r'auteur|scenar|dessin', re.I))
            auteur = auteur_el.get_text(strip=True) if auteur_el else None

            # Éditeur
            editeur_el = item.find(class_=re.compile(r'editeur|publisher', re.I))
            editeur = editeur_el.get_text(strip=True) if editeur_el else None

            # Type (BD/Manga/Comics) depuis la classe ou le texte
            texte = item.get_text().lower()
            type_detecte = 'BD'
            if 'manga' in texte:
                type_detecte = 'Manga'
            elif 'comics' in texte or 'comic' in texte:
                type_detecte = 'Comics'

            # Filtre optionnel
            if type_bd and type_detecte.lower() != type_bd.lower():
                continue

            resultats.append({
                'titre': titre,
                'serie': serie,
                'auteur': auteur,
                'editeur': editeur,
                'type': type_detecte,
                'url': lien,
                'source': 'BeDeTh-que.com',
            })

            if len(resultats) >= nb:
                break

        # Si pas de résultats via classes, essayer une approche plus directe
        if not resultats:
            for link in soup.find_all('a', href=re.compile(r'/bande-dessinee-|/manga-|/comics-'))[:nb]:
                titre = link.get_text(strip=True)
                if titre and len(titre) > 2:
                    lien = 'https://www.bedetheque.com' + link['href']
                    resultats.append({
                        'titre': titre,
                        'url': lien,
                        'source': 'BeDeTh-que.com',
                    })

        return resultats

    except Exception as e:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 3. BOOKNODE — Thèmes, Séries, Meilleures Ventes
# ─────────────────────────────────────────────────────────────────────────────
def chercher_booknode_sorties(nb=15):
    """
    Récupère les prochaines sorties et nouvelles parutions de Booknode.
    Utile pour anticiper les acquisitions de romans.
    """
    url = 'https://booknode.com/dates_de_sortie'
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        resultats = []
        for item in soup.find_all(class_=re.compile(r'(book|livre|sortie|item)', re.I))[:nb * 2]:
            titre_el = item.find(['h2', 'h3', 'a'])
            if not titre_el:
                continue
            titre = titre_el.get_text(strip=True)
            if not titre or len(titre) < 3:
                continue

            lien = titre_el.get('href', '') if titre_el.name == 'a' else ''
            if lien and not lien.startswith('http'):
                lien = 'https://booknode.com' + lien

            # Éditeur
            editeur_el = item.find(class_=re.compile(r'editeur|publisher', re.I))
            editeur = editeur_el.get_text(strip=True) if editeur_el else None

            # Date de sortie
            date_el = item.find(class_=re.compile(r'date|sortie', re.I))
            date = date_el.get_text(strip=True) if date_el else None

            resultats.append({
                'titre': titre,
                'editeur': editeur,
                'date_sortie': date,
                'url': lien,
                'source': 'Booknode',
            })

            if len(resultats) >= nb:
                break

        return resultats

    except Exception:
        return []


def chercher_booknode_ventes():
    """Récupère le classement des meilleures ventes françaises de Booknode."""
    url = 'https://booknode.com/meilleures_ventes_france'
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        resultats = []
        for i, item in enumerate(soup.find_all('a', href=re.compile(r'/[a-z_]+_\d+'))[:20], 1):
            titre = item.get_text(strip=True)
            if titre and len(titre) > 3 and not titre.startswith('#'):
                resultats.append({
                    'rang': i,
                    'titre': titre,
                    'url': 'https://booknode.com' + item['href'],
                    'source': 'Booknode — Meilleures ventes',
                })

        return resultats

    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 4. CROQULIVRE.FR — Chroniques jeunesse qualifiées (association spécialisée,
#    7000+ références). Contrairement aux autres sources, le site expose une
#    API REST WordPress standard (wp-json) : plus fiable qu'un scraping HTML.
# ─────────────────────────────────────────────────────────────────────────────
_CROQULIVRE_CATEGORIES = {
    'Album': 'albums',
    'Roman': 'romans',
    'BD': 'bd',
    'Documentaire': 'documentaires',
    'Livre pratique': 'livre-pratique',
}
_croqulivre_cache_ids = {}  # slug -> id WordPress, mis en cache pour la session


def _croqulivre_id_categorie(slug):
    """Résout un slug de catégorie Croqulivre en id WordPress (mis en cache)."""
    if slug in _croqulivre_cache_ids:
        return _croqulivre_cache_ids[slug]
    try:
        url = f'https://croqulivre.fr/wp-json/wp/v2/categories?slug={slug}'
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
        if data:
            _croqulivre_cache_ids[slug] = data[0]['id']
            return data[0]['id']
    except Exception:
        pass
    return None


def chercher_croqulivre(categorie=None, nb=15):
    """
    Récupère les dernières chroniques de Croqulivre.fr via son API REST WordPress.

    categorie : 'Album' / 'Roman' / 'BD' / 'Documentaire' / 'Livre pratique' / None (tout)
    nb        : nombre de résultats

    Retourne une liste de dicts {titre, resume, date, url, source}.
    """
    params = f'per_page={min(nb, 50)}&_fields=title,link,date,excerpt'
    if categorie:
        slug = _CROQULIVRE_CATEGORIES.get(categorie)
        if not slug:
            return []
        id_cat = _croqulivre_id_categorie(slug)
        if id_cat is None:
            return []
        params += f'&categories={id_cat}'

    try:
        url = f'https://croqulivre.fr/wp-json/wp/v2/posts?{params}'
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        posts = r.json()

        resultats = []
        for post in posts[:nb]:
            titre = BeautifulSoup(post.get('title', {}).get('rendered', ''), 'html.parser').get_text(strip=True)
            if not titre:
                continue
            resume_html = post.get('excerpt', {}).get('rendered', '')
            resume = BeautifulSoup(resume_html, 'html.parser').get_text(' ', strip=True)
            resume = re.sub(r'\s+', ' ', resume).strip()
            if len(resume) > 250:
                resume = resume[:250].rsplit(' ', 1)[0] + '…'

            resultats.append({
                'titre': titre,
                'resume': resume,
                'date': post.get('date', '')[:10],
                'url': post.get('link', ''),
                'source': 'Croqulivre.fr',
            })
        return resultats
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 5. BABELIO — NOTES ET AVIS SUR NOTRE FONDS
# ─────────────────────────────────────────────────────────────────────────────
def chercher_note_babelio(isbn):
    """
    Récupère la note Babelio d'un titre par ISBN.
    Utile pour distinguer les titres délaissés (mauvais) de ceux sous-mis en avant (bons).
    Retourne la note (/5) ou None si non trouvé.
    """
    try:
        url = f"https://www.babelio.com/recherche/?Recherche={isbn}&type=isbn"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')

        # Note sur la page de résultats
        note_el = soup.find(class_=re.compile(r'(note_global|rating|score)', re.I))
        if note_el:
            m = re.search(r'(\d+[.,]\d+)', note_el.get_text())
            if m:
                return float(m.group(1).replace(',', '.'))

        # Chercher le lien vers la fiche livre
        lien = soup.find('a', href=re.compile(r'/livres/'))
        if lien:
            url_fiche = 'https://www.babelio.com' + lien['href']
            r2 = requests.get(url_fiche, headers=HEADERS, timeout=TIMEOUT)
            if r2.status_code == 200:
                soup2 = BeautifulSoup(r2.text, 'html.parser')
                note_el2 = soup2.find(class_=re.compile(r'(note_global|rating)', re.I))
                if note_el2:
                    m = re.search(r'(\d+[.,]\d+)', note_el2.get_text())
                    if m:
                        return float(m.group(1).replace(',', '.'))
        return None
    except Exception:
        return None


def enrichir_fonds_avec_babelio(isbns, nb_max=50):
    """
    Pour une liste d'ISBNs (typiquement les moins empruntés), récupère les notes Babelio.
    Retourne dict {isbn: note} — None si non trouvé.
    nb_max : limite pour éviter de surcharger Babelio.
    """
    resultats = {}
    for isbn in isbns[:nb_max]:
        note = chercher_note_babelio(isbn)
        resultats[isbn] = note
        time.sleep(1)  # Respecter les serveurs
    return resultats


# ─────────────────────────────────────────────────────────────────────────────
def chercher_nouveautes(categorie=None, nb=15):
    """
    Agrège les nouveautés de toutes les sources selon la catégorie demandée.

    categorie : 'BD' / 'Manga' / 'Roman' / 'Album' / 'Documentaire' / None (tout)
    nb        : nombre de résultats par source

    Retourne une liste de dicts {titre, auteur, editeur, url, source, ...}
    """
    resultats = []

    if categorie in (None, 'BD', 'Manga', 'Comics'):
        # BeDeTh-que pour la BD et le manga
        type_bd = categorie if categorie in ('BD', 'Manga', 'Comics') else None
        bd = chercher_bedetheque(nb=nb, type_bd=type_bd)
        resultats.extend(bd)
        time.sleep(0.5)

    if categorie in (None, 'Roman', 'Album', 'Documentaire'):
        # Ricochet pour la littérature jeunesse
        jeunesse = chercher_ricochet(nb=nb)
        resultats.extend(jeunesse)
        time.sleep(0.5)

    if categorie in (None, 'Roman'):
        # Booknode pour les sorties de romans
        sorties = chercher_booknode_sorties(nb=nb)
        resultats.extend(sorties)

    if categorie in (None, 'BD', 'Roman', 'Album', 'Documentaire', 'Livre pratique'):
        # Croqulivre pour des chroniques qualifiées (association spécialisée)
        croq_categorie = categorie if categorie in _CROQULIVRE_CATEGORIES else None
        croq = chercher_croqulivre(categorie=croq_categorie, nb=nb)
        resultats.extend(croq)
        time.sleep(0.5)

    return resultats


# ─────────────────────────────────────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    print("=== TEST BeDeTh-que ===")
    bd = chercher_bedetheque(nb=5)
    for r in bd[:5]:
        print(f"  {r.get('titre', '?')} — {r.get('editeur', '?')} [{r.get('type', '?')}]")

    print("\n=== TEST Ricochet ===")
    rich = chercher_ricochet(nb=5)
    for r in rich[:5]:
        print(f"  {r.get('titre', '?')} — {r.get('auteur', '?')}")

    print("\n=== TEST Booknode sorties ===")
    bn = chercher_booknode_sorties(nb=5)
    for r in bn[:5]:
        print(f"  {r.get('titre', '?')} — {r.get('editeur', '?')}")

    print("\n=== TEST Booknode ventes ===")
    bv = chercher_booknode_ventes()
    for r in bv[:5]:
        print(f"  #{r.get('rang')} {r.get('titre', '?')}")

    print("\n=== TEST Croqulivre (BD) ===")
    cq = chercher_croqulivre(categorie='BD', nb=5)
    for r in cq[:5]:
        print(f"  {r.get('titre', '?')} ({r.get('date', '?')})")
