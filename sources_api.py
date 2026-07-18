"""
sources_api.py — Sources bibliographiques API pour enrichissement des notices

Hiérarchie :
1. BnF SRU         → notices professionnelles françaises, sans authentification
2. Google Books    → résumés, couvertures, catégories (nécessite clé API gratuite)
3. Sudoc           → fallback notices difficiles / fonds patrimoniaux
4. COBAS portail   → disponibilité temps réel (scraping OPAC public Decalog)
5. [12 sources web existantes dans moteur_recherche.py comme backup]

Pour Google Books : obtenir une clé gratuite sur https://console.cloud.google.com/
puis ajouter GOOGLE_BOOKS_API_KEY=votre_clé dans le fichier .env
"""

import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import os
import time

TIMEOUT = (5, 10)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; Mediatheque-Arcachon-Bot/1.0)',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.5',
}

# Clé Google Books (optionnelle — améliore le quota)
GOOGLE_API_KEY = os.environ.get('GOOGLE_BOOKS_API_KEY', '')


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _tag(elem):
    """Retourne le nom du tag sans namespace."""
    return elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag


def _get_sf(root, tag_num, code):
    """Récupère la valeur d'un sous-champ dans un record MarcXchange."""
    for elem in root.iter():
        if _tag(elem) == 'datafield' and elem.attrib.get('tag') == tag_num:
            for sf in elem:
                if _tag(sf) == 'subfield' and sf.attrib.get('code') == code:
                    return (sf.text or '').strip()
    return None


def _get_all_sf(root, tag_num, code):
    """Récupère toutes les valeurs d'un sous-champ (peut être répété)."""
    results = []
    for elem in root.iter():
        if _tag(elem) == 'datafield' and elem.attrib.get('tag') == tag_num:
            for sf in elem:
                if _tag(sf) == 'subfield' and sf.attrib.get('code') == code:
                    if sf.text and sf.text.strip():
                        results.append(sf.text.strip())
    return results


def _normaliser_public(texte):
    if not texte:
        return None
    t = texte.lower()
    if any(k in t for k in ['jeun', 'enfant', 'junior', 'kid', 'young', 'child']):
        return 'Jeune'
    if any(k in t for k in ['ado', 'teen', 'adolescent']):
        return 'Adolescent'
    if any(k in t for k in ['adult', 'mature']):
        return 'Adulte'
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. BNF SRU
# ─────────────────────────────────────────────────────────────────────────────
def chercher_bnf(isbn):
    """
    Interroge le catalogue BnF via SRU par ISBN.
    Gratuit, sans authentification, notices professionnelles françaises.
    """
    url = (
        f"https://catalogue.bnf.fr/api/SRU"
        f"?version=1.2&operation=searchRetrieve"
        f'&query=bib.isbn+adj+"{isbn}"'
        f"&recordSchema=unimarcxchange&maximumRecords=1"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        # Trouver le premier record
        record = None
        for elem in root.iter():
            if _tag(elem) == 'record':
                record = elem
                break
        if record is None:
            return None

        # Titre (zone 200$a + $e)
        titre_a = _get_sf(record, '200', 'a')
        titre_e = _get_sf(record, '200', 'e')
        titre = titre_a
        if titre and titre_e:
            titre = f"{titre} : {titre_e}"

        # Auteur (zone 200$f en premier lieu, sinon 700$a+$b)
        auteur = _get_sf(record, '200', 'f')
        if not auteur:
            nom = _get_sf(record, '700', 'a')
            prenom = _get_sf(record, '700', 'b')
            if prenom and nom:
                auteur = f"{prenom} {nom}"
            elif nom:
                auteur = nom

        # Éditeur (zone 210$c ou 214$c)
        editeur = _get_sf(record, '210', 'c') or _get_sf(record, '214', 'c')

        # Date (zone 210$d ou 214$d)
        date_brut = _get_sf(record, '210', 'd') or _get_sf(record, '214', 'd')
        date_pub = None
        if date_brut:
            m = re.search(r'(19|20)\d{2}', date_brut)
            if m:
                date_pub = m.group(0)

        # Résumé (zone 330$a)
        resume = _get_sf(record, '330', 'a')
        if resume and len(resume) > 1000:
            resume = resume[:1000] + '...'

        # Sujets Rameau (zones 6xx$a)
        sujets = []
        for tag_num in ['600', '601', '602', '604', '606', '607', '608', '610']:
            sujets.extend(_get_all_sf(record, tag_num, 'a'))
        mots_cles = ', '.join(sujets[:8]) if sujets else None

        # Dewey (zone 676$a)
        dewey = _get_sf(record, '676', 'a')

        # Public visé (zone 521$a)
        public_brut = _get_sf(record, '521', 'a')
        public_vise = _normaliser_public(public_brut)

        # Couverture via Geobib (spécialisé bibliothèques françaises)
        image_url = f"https://couverture.geobib.fr/api/v1/{isbn}/M"

        resultat = {
            'source': 'BnF SRU',
            'titre': titre,
            'auteur': auteur,
            'editeur': editeur,
            'date_publication': date_pub,
            'resume': resume,
            'mots_cles': mots_cles,
            'dewey': dewey,
            'public_vise': public_vise,
            'image_url': image_url,
        }
        return {k: v for k, v in resultat.items() if v}

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 2. GOOGLE BOOKS
# ─────────────────────────────────────────────────────────────────────────────
def chercher_google_books(isbn):
    """
    Interroge Google Books par ISBN.
    Nécessite une clé API gratuite pour un usage intensif.
    Obtenir une clé : https://console.cloud.google.com/ → API & Services → Books API
    Ajouter dans .env : GOOGLE_BOOKS_API_KEY=votre_clé
    """
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
    if GOOGLE_API_KEY:
        url += f"&key={GOOGLE_API_KEY}"

    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)

        if r.status_code == 429:
            # Quota dépassé — clé API nécessaire
            return None
        r.raise_for_status()

        data = r.json()
        items = data.get('items', [])
        if not items:
            return None

        info = items[0].get('volumeInfo', {})

        titre = info.get('title')
        subtitle = info.get('subtitle')
        if titre and subtitle:
            titre = f"{titre} : {subtitle}"

        auteurs = info.get('authors', [])
        auteur = ', '.join(auteurs[:2]) if auteurs else None

        editeur = info.get('publisher')

        date_brut = info.get('publishedDate', '')
        date_pub = None
        if date_brut:
            m = re.search(r'(19|20)\d{2}', date_brut)
            if m:
                date_pub = m.group(0)

        resume = info.get('description')
        if resume and len(resume) > 1000:
            resume = resume[:1000] + '...'

        # Catégories → genre + public
        categories_raw = info.get('categories', [])
        genre = None
        public_vise = None
        if categories_raw:
            cats = [c.lower() for c in categories_raw]
            for cat in cats:
                if any(k in cat for k in ['juvenile', 'children', 'young adult', 'jeunesse']):
                    public_vise = 'Jeune'
                    break
            if not public_vise and info.get('maturityRating') == 'MATURE':
                public_vise = 'Adulte'

            genre_map = {
                'comics': 'BD', 'graphic novel': 'BD', 'manga': 'Manga',
                'fiction': 'Roman', 'roman': 'Roman',
                'poetry': 'Poésie', 'documentaire': 'Documentaire',
                'fantasy': 'Fantastique', 'science fiction': 'SF',
                'adventure': 'Aventure', 'humour': 'Humour',
                'biography': 'Biographie', 'history': 'Histoire',
            }
            for cat in cats:
                for key, val in genre_map.items():
                    if key in cat:
                        genre = val
                        break
                if genre:
                    break

        # Couverture
        image_links = info.get('imageLinks', {})
        image_url = (
            image_links.get('extraLarge') or image_links.get('large')
            or image_links.get('medium') or image_links.get('thumbnail')
        )
        if image_url:
            image_url = image_url.replace('&edge=curl', '').replace('http://', 'https://')

        resultat = {
            'source': 'Google Books',
            'titre': titre,
            'auteur': auteur,
            'editeur': editeur,
            'date_publication': date_pub,
            'resume': resume,
            'genre': genre,
            'public_vise': public_vise,
            'image_url': image_url,
        }
        return {k: v for k, v in resultat.items() if v}

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. SUDOC (ABES)
# ─────────────────────────────────────────────────────────────────────────────
def chercher_sudoc(isbn):
    """
    Sudoc : isbn2ppn → notice. Utile pour fonds patrimoniaux et cas difficiles.
    """
    try:
        r = requests.get(
            f"https://www.sudoc.fr/services/isbn2ppn/{isbn}",
            headers=HEADERS, timeout=TIMEOUT
        )
        r.raise_for_status()
        root = ET.fromstring(r.content)

        ppn = None
        for elem in root.iter():
            if 'ppn' in _tag(elem).lower() and elem.text and elem.text.strip().isdigit():
                ppn = elem.text.strip()
                break
        if not ppn:
            return None

        r2 = requests.get(
            f"https://www.sudoc.fr/services/sru/?operation=searchRetrieve"
            f"&version=1.1&query=ppn+%3D+{ppn}"
            f"&recordSchema=unimarc&maximumRecords=1",
            headers=HEADERS, timeout=TIMEOUT
        )
        r2.raise_for_status()
        root2 = ET.fromstring(r2.content)

        record = None
        for elem in root2.iter():
            if _tag(elem) == 'record':
                record = elem
                break
        if not record:
            return None

        titre = _get_sf(record, '200', 'a') or _get_sf(record, '200', 'f')
        nom = _get_sf(record, '700', 'a')
        prenom = _get_sf(record, '700', 'b')
        auteur = f"{prenom} {nom}".strip() if nom else None
        editeur = _get_sf(record, '210', 'c')
        date_brut = _get_sf(record, '210', 'd')
        date_pub = None
        if date_brut:
            m = re.search(r'(19|20)\d{2}', date_brut)
            if m:
                date_pub = m.group(0)
        resume = _get_sf(record, '330', 'a')

        resultat = {
            'source': 'Sudoc',
            'titre': titre, 'auteur': auteur,
            'editeur': editeur, 'date_publication': date_pub, 'resume': resume,
        }
        return {k: v for k, v in resultat.items() if v}

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. COBAS PORTAIL (OPAC PUBLIC DECALOG)
# ─────────────────────────────────────────────────────────────────────────────
BASE_COBAS = "https://mediatheques.agglo-cobas.fr"

def chercher_cobas_statut_isbn(isbn):
    """
    Scrape l'OPAC public COBAS pour vérifier la disponibilité en temps réel.
    Retourne dans_le_fonds (bool) + statuts détectés.
    Usage : app conversationnelle uniquement, pas pour enrichissement de masse.
    """
    try:
        url = f"{BASE_COBAS}/opac/catalog/search?isbn[]={isbn}"
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')
        texte = soup.get_text().lower()

        mots_cobas = ['arcachon', 'la teste', 'gujan', 'le teich', 'disponible',
                      'en prêt', 'réservé', 'cobas']
        dans_le_fonds = any(k in texte for k in mots_cobas)

        statuts = []
        for motcle, statut in [
            ('disponible', 'Disponible'),
            ('en prêt', 'En prêt'),
            ('réservé', 'Réservé'),
            ('en transit', 'En transit'),
        ]:
            if motcle in texte:
                statuts.append(statut)

        # Extraire les sites mentionnés
        sites = []
        for site in ['Arcachon', 'La Teste', 'Gujan', 'Le Teich']:
            if site.lower() in texte:
                sites.append(site)

        return {
            'source': 'COBAS portail',
            'isbn': isbn,
            'dans_le_fonds': dans_le_fonds,
            'statuts': statuts,
            'sites': sites,
            'url': url,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ─────────────────────────────────────────────────────────────────────────────
def enrichir_par_api(isbn, avec_cobas=False):
    """
    Interroge BnF SRU + Google Books + Sudoc et fusionne les résultats.
    Les 12 sources web de moteur_recherche.py restent en backup.
    """
    fusionne = {}
    sources = []

    # 1. BnF SRU
    bnf = chercher_bnf(isbn)
    if bnf:
        fusionne.update(bnf)
        sources.append('BnF SRU')

    # 2. Google Books — complète ce que BnF n'a pas
    google = chercher_google_books(isbn)
    if google:
        for cle, val in google.items():
            if not fusionne.get(cle):
                fusionne[cle] = val
            # Préférer résumé Google si plus long
            if cle == 'resume' and val and len(val) > len(fusionne.get('resume', '')):
                fusionne['resume'] = val
        sources.append('Google Books')

    # 3. Sudoc — si champs essentiels manquants
    manquants = sum(1 for c in ['titre', 'auteur', 'editeur'] if not fusionne.get(c))
    if manquants >= 2:
        sudoc = chercher_sudoc(isbn)
        if sudoc:
            for cle, val in sudoc.items():
                if not fusionne.get(cle):
                    fusionne[cle] = val
            sources.append('Sudoc')

    # 4. COBAS portail (optionnel)
    if avec_cobas:
        cobas = chercher_cobas_statut_isbn(isbn)
        if cobas:
            fusionne['cobas'] = cobas
            sources.append('COBAS portail')

    if not fusionne:
        return None

    fusionne['sources_api'] = ', '.join(sources)
    return fusionne


# ─────────────────────────────────────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    test_isbns = [
        ('9782070612758', 'Le Petit Prince — Gallimard'),
        ('9782818994436', 'Dans tes rêves ! — Bamboo'),
        ('9782344033593', 'One Piece t.90 — Glénat'),
    ]
    for isbn, label in test_isbns:
        print(f"\n{'='*60}\n{label} ({isbn})")
        res = enrichir_par_api(isbn)
        if res:
            for k, v in res.items():
                if v and k != 'cobas':
                    print(f"  {k:25s}: {str(v)[:80]}")
        else:
            print("  Aucun résultat")
        time.sleep(0.5)

    print(f"\n{'='*60}\nTest COBAS portail")
    cobas = chercher_cobas_statut_isbn('9782070612758')
    print(cobas)
