#!/usr/bin/env python3
"""
generer_ecrans_maat.py — Régénère les 2 écrans numériques (mosaïque tactile
du hall + diaporama jeunesse) et les envoie automatiquement sur OVH par SFTP.

Réécrit le 2026-07-22 pour reproduire fidèlement la logique manuelle qui
fonctionnait bien dans l'autre conversation Claude ("écrans maat"), au lieu
de s'appuyer sur la colonne image_url de notre base (mal couverte pour les
publics hors jeunesse). Seule différence : au lieu d'un export Decalog
dédié envoyé à la main chaque mois, ce script lit directement le .mrc
COMPLET déposé chaque semaine (le même que celui traité par
import_hebdomadaire.sh) et applique EXACTEMENT le même filtrage que
Decalog appliquait à son export -- l'automatisation ne change que la
source du fichier, pas la logique de sélection ni de couverture.

Sélection (identique à la procédure manuelle, voir
"ecrans maat/resume-projet-kiosque-mediatheque.md") :
  - Exemplaires du fonds Arcachon uniquement (zone MARC 995 $a).
  - "Mise à l'inventaire" (995 $1) dans les FENETRE_MOIS derniers mois.
  - Mosaïque  : type Livre / BD / Manga / Imprimé -- exclut DVD, Jeux
    vidéo, Jeux de société ET Revues (comme le script d'origine).
  - Diaporama : même base, restreinte au public Jeunesse/Adolescent/Tout
    public (995 $l).
  - Couverture : zone 856 $u (lien direct Decalog/ORB) en premier, repli
    Open Library si absente ou invalide -- chaque URL est vérifiée
    accessible avant d'être retenue (voir _image_accessible).

Les 2 fichiers HTML sont réécrits EN PLACE (même nom de fichier à chaque
fois, puisque les écrans OVH pointent vers une URL fixe).

Upload SFTP automatique si OVH_SFTP_HOST / OVH_SFTP_USER / OVH_SFTP_PASSWORD
sont définies dans .env -- sinon les fichiers sont simplement régénérés en
local et un message l'indique (à pousser soi-même via Cyberduck).

Usage :
    python3 generer_ecrans_maat.py                 (génère + envoie sur OVH)
    python3 generer_ecrans_maat.py --sans-upload    (génère seulement, pour tester)
    python3 generer_ecrans_maat.py --mrc "Liste des notices - 2026-07-19.mrc"
                                                     (force un fichier précis)
"""
import os
import re
import sys
import glob
import datetime
import concurrent.futures
import urllib.request
import urllib.error

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DOSSIER_ECRANS = os.path.join(DOSSIER, "ecrans maat")
FICHIER_MOSAIQUE = os.path.join(DOSSIER_ECRANS, "mediatheque-cobas-mosaique.html")
FICHIER_DIAPORAMA = os.path.join(DOSSIER_ECRANS, "mediatheque-diaporama-jeunesse.html")


def _charger_dotenv():
    """Ce script n'importe plus db.py (plus besoin de la base), donc il
    doit charger .env lui-même -- sinon OVH_SFTP_* reste invisible même
    quand .env est bien rempli."""
    chemin = os.path.join(DOSSIER, ".env")
    if not os.path.exists(chemin):
        return
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


_charger_dotenv()

FENETRE_MOIS = 4
PUBLICS_JEUNESSE = ("Jeune", "Jeunesse", "Ado (12+)", "Adolescent", "Tout public")

sys.path.insert(0, DOSSIER)
from iso2709 import parse_records, get_subfields  # noqa: E402


def _log(message):
    horodatage = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"[{horodatage}] {message}", flush=True)


def _date_limite():
    """AAAA-MM-JJ correspondant à 'aujourd'hui moins FENETRE_MOIS mois'."""
    aujourd_hui = datetime.date.today()
    mois_total = aujourd_hui.month - 1 - FENETRE_MOIS
    annee = aujourd_hui.year + mois_total // 12
    mois = mois_total % 12 + 1
    jour = min(aujourd_hui.day, 28)
    return datetime.date(annee, mois, jour).isoformat()


def trouver_dernier_mrc():
    """Même détection que import_hebdomadaire.sh : le .mrc hebdo le plus
    récent déposé dans le dossier (motif avec le tiret pour ne pas
    confondre avec un éventuel export 'Liste des notices mosaique - ...')."""
    candidats = sorted(glob.glob(os.path.join(DOSSIER, "Liste des notices - *.mrc")))
    return candidats[-1] if candidats else None


def _echapper_js(valeur):
    if valeur is None:
        valeur = ""
    valeur = str(valeur)
    valeur = valeur.replace("\\", "\\\\").replace('"', '\\"')
    valeur = valeur.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return '"' + valeur + '"'


def _annee_nettoyee(brut):
    """Le champ 210/214 $d contient parfois 'DL 2026' (dépôt légal) au lieu
    d'une année seule -- on ne garde que les 4 chiffres, comme affiché
    avant (l'affichage brut a fait croire à un nouveau champ inconnu)."""
    if not brut:
        return None
    m = re.search(r"(19|20)\d{2}", brut)
    return m.group(0) if m else brut


def _date_inventaire_normalisee(brut):
    """995 $1 est en AAAAMMJJ (comme date_acquisition en base) -- on la
    ramène en AAAA-MM-JJ pour une comparaison lexicographique fiable."""
    if not brut or len(brut) < 8 or not brut[:8].isdigit():
        return None
    return f"{brut[0:4]}-{brut[4:6]}-{brut[6:8]}"


def parser_notice(rec):
    """Extrait d'un enregistrement MARC les champs utiles aux écrans, en
    reprenant le même mappage de zones que actualiser_catalogue.py."""
    titre = editeur = date_pub = resume_parts = None
    resume_parts = []
    contributeurs = []
    image_856 = None
    type_support_hint = None
    ean_073 = isbn_010 = None
    date_461 = None
    exemplaires_locaux = []

    for tag, raw in rec['fields']:
        ind, subs = get_subfields(raw)
        if tag == '073':
            for code, val in subs:
                if code == 'a':
                    ean_073 = val
        elif tag == '010':
            for code, val in subs:
                if code == 'a':
                    isbn_010 = val
        elif tag == '200':
            for code, val in subs:
                if code == 'a':
                    titre = val
        elif tag in ('700', '701', '702'):
            d = dict(subs)
            nom = d.get('a')
            if nom:
                prenom = d.get('b')
                nom_complet = f"{nom} {prenom}".strip() if prenom else nom
                contributeurs.append((d.get('4'), nom_complet))
        elif tag in ('210', '214'):
            for code, val in subs:
                if code == 'c' and not editeur:
                    editeur = val
                elif code == 'd' and not date_pub:
                    date_pub = val
        elif tag == '330':
            for code, val in subs:
                if code == 'a':
                    resume_parts.append(val)
        elif tag == '856':
            if any(c == '2' and v == 'Image' for c, v in subs):
                for code, val in subs:
                    if code == 'u':
                        image_856 = val
        elif tag == '461':
            for code, val in subs:
                if code == 'd':
                    date_461 = val
        elif tag == '995':
            d = dict(subs)
            if d.get('a') != "Médiathèque d'Arcachon":
                continue
            if type_support_hint is None:
                type_support_hint = d.get('w')
            exemplaires_locaux.append({
                'cote': d.get('k'), 'public_vise': d.get('l'),
                'support': d.get('w'), 'date_inventaire': d.get('1'),
            })

    if not exemplaires_locaux:
        return None  # aucun exemplaire Arcachon sur cette notice

    auteur = None
    for role, nom in contributeurs:
        if role == '070':
            auteur = nom
            break
    if auteur is None and contributeurs:
        auteur = contributeurs[0][1]

    if date_461:
        type_document = 'REVUE'
    elif type_support_hint in ('CD', 'Livre-CD', 'Disque vinyle', 'Cassette'):
        type_document = 'CD'
    elif type_support_hint in ('DVD', 'Livre-DVD', 'Blu-ray'):
        type_document = 'DVD'
    elif type_support_hint == 'Jeu':
        type_document = 'JEU'
    elif type_support_hint in ('Imprimé', 'Livre tactile', 'Support électronique'):
        type_document = 'LIVRE'
    else:
        type_document = 'AUTRE'

    isbn = ean_073 or isbn_010
    # Exemplaire Arcachon le plus récemment inventorié -- c'est cette date
    # qui détermine si le titre est une "nouveauté" pour les écrans.
    meilleur = max(
        exemplaires_locaux,
        key=lambda e: _date_inventaire_normalisee(e.get('date_inventaire')) or ''
    )

    return {
        'isbn': isbn,
        'titre': titre,
        'auteur': auteur,
        'annee': _annee_nettoyee(date_pub),
        'editeur': editeur,
        'resume': ' '.join(resume_parts) if resume_parts else None,
        'cote': meilleur.get('cote'),
        'public_vise': meilleur.get('public_vise'),
        'support': meilleur.get('support'),
        'date_inventaire': _date_inventaire_normalisee(meilleur.get('date_inventaire')),
        'type_document': type_document,
        'image_856': image_856,
    }


def charger_notices(chemin_mrc):
    _log(f"Lecture de {os.path.basename(chemin_mrc)}...")
    with open(chemin_mrc, "rb") as f:
        data = f.read()
    notices = []
    for rec in parse_records(data):
        try:
            notice = parser_notice(rec)
        except Exception:
            continue
        if notice and notice['isbn']:
            notices.append(notice)
    _log(f"{len(notices)} notices avec au moins un exemplaire Arcachon.")
    return notices


TIMEOUT_VALIDATION_SECONDES = 6
EN_TETES_VALIDATION = {"User-Agent": "Mozilla/5.0 (compatible; MediathequeArcachonEcrans/1.0)"}


def _image_accessible(url):
    """Vérifie que l'URL répond bien avec une vraie image (voir
    generer_ecrans_maat.py historique : certaines sources renvoient une
    404/403 malgré une URL a priori correcte)."""
    if not url:
        return False
    for methode in ("HEAD", "GET"):
        requete = urllib.request.Request(url, headers=EN_TETES_VALIDATION, method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=TIMEOUT_VALIDATION_SECONDES) as reponse:
                type_contenu = reponse.headers.get("Content-Type", "")
                taille = reponse.headers.get("Content-Length")
                if not type_contenu.startswith("image/"):
                    return False
                # Open Library renvoie une image "introuvable" grise minuscule
                # (~800 octets) au lieu d'une 404 -- on l'écarte explicitement.
                if taille and int(taille) < 1000:
                    return False
                return True
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                if methode == "HEAD":
                    continue
                return False
            return True
        except Exception:
            if methode == "HEAD":
                continue
            return True
    return True


def resoudre_couvertures(notices):
    """Détermine, pour chaque notice, la meilleure URL de couverture
    valide : zone 856 (Decalog/ORB) en priorité, repli Open Library.
    Teste tout en parallèle pour rester rapide malgré le volume."""
    candidats = {}
    for n in notices:
        liste = []
        if n['image_856']:
            liste.append(n['image_856'])
        liste.append(f"https://covers.openlibrary.org/b/isbn/{n['isbn']}-M.jpg")
        candidats[n['isbn']] = liste

    toutes_urls = sorted({u for liste in candidats.values() for u in liste})
    resultats = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=24) as executeur:
        futurs = {executeur.submit(_image_accessible, u): u for u in toutes_urls}
        for futur in concurrent.futures.as_completed(futurs):
            resultats[futurs[futur]] = futur.result()

    couvertures = {}
    for isbn, liste in candidats.items():
        for u in liste:
            if resultats.get(u):
                couvertures[isbn] = u
                break
    return couvertures


def _ligne_objet(notice, url_image, champ_image):
    return "  {t:%s,a:%s,y:%s,ed:%s,cote:%s,pub:%s,sup:%s,d:%s,isbn:%s,%s:%s}," % (
        _echapper_js(notice['titre']),
        _echapper_js(notice['auteur']),
        _echapper_js(notice['annee']),
        _echapper_js(notice['editeur']),
        _echapper_js(notice['cote']),
        _echapper_js(notice['public_vise']),
        _echapper_js(notice['support']),
        _echapper_js(notice['resume']),
        _echapper_js(notice['isbn']),
        champ_image,
        _echapper_js(url_image),
    )


NO_CACHE_META = (
    '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n'
    '<meta http-equiv="Pragma" content="no-cache">\n'
    '<meta http-equiv="Expires" content="0">\n'
)


def _empecher_cache_navigateur(contenu):
    if "Cache-Control" in contenu:
        return contenu
    return contenu.replace("<head>", "<head>\n" + NO_CACHE_META, 1)


def regenerer_fichier(chemin, variable, objets):
    with open(chemin, encoding="utf-8") as f:
        contenu = f.read()
    motif = re.compile(r"const %s\s*=\s*\[.*?\];" % re.escape(variable), re.S)
    nouveau_bloc = "const %s=[\n%s\n];" % (variable, "\n".join(objets))
    contenu_nouveau, nb = motif.subn(nouveau_bloc, contenu, count=1)
    if nb != 1:
        raise RuntimeError(
            f"Bloc 'const {variable}=[...]' introuvable dans {chemin} -- "
            "fichier laissé intact pour ne pas le casser."
        )
    contenu_nouveau = _empecher_cache_navigateur(contenu_nouveau)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu_nouveau)


def televerser_sftp(fichiers):
    hote = os.environ.get("OVH_SFTP_HOST")
    port = int(os.environ.get("OVH_SFTP_PORT", "22"))
    utilisateur = os.environ.get("OVH_SFTP_USER")
    mot_de_passe = os.environ.get("OVH_SFTP_PASSWORD")
    dossier_distant = os.environ.get("OVH_SFTP_DOSSIER", "www")

    if not (hote and utilisateur and mot_de_passe):
        _log("Identifiants OVH_SFTP_* absents du .env -- fichiers générés "
             "en local uniquement, à pousser toi-même via Cyberduck.")
        return

    try:
        import paramiko
    except ImportError:
        _log("Module 'paramiko' non installé (pip install paramiko --break-system-packages) "
             "-- envoi SFTP ignoré, fichiers générés en local uniquement.")
        return

    _log(f"Connexion SFTP à {hote}:{port}...")
    transport = paramiko.Transport((hote, port))
    try:
        transport.connect(username=utilisateur, password=mot_de_passe)
        sftp = paramiko.SFTPClient.from_transport(transport)
        try:
            for chemin_local in fichiers:
                nom = os.path.basename(chemin_local)
                chemin_distant = dossier_distant.rstrip("/") + "/" + nom
                sftp.put(chemin_local, chemin_distant)
                _log(f"Envoyé sur OVH : {chemin_distant}")
        finally:
            sftp.close()
    finally:
        transport.close()


def main():
    sans_upload = "--sans-upload" in sys.argv
    chemin_mrc = None
    if "--mrc" in sys.argv:
        chemin_mrc = sys.argv[sys.argv.index("--mrc") + 1]
    else:
        chemin_mrc = trouver_dernier_mrc()

    if not chemin_mrc or not os.path.exists(chemin_mrc):
        _log("Aucun fichier .mrc trouvé -- écrans MAAT non régénérés cette semaine.")
        return

    date_limite = _date_limite()
    _log(f"Nouveautés depuis le {date_limite} (fenêtre de {FENETRE_MOIS} mois glissants).")

    toutes_notices = charger_notices(chemin_mrc)
    recentes = [n for n in toutes_notices if n['date_inventaire'] and n['date_inventaire'] >= date_limite]
    _log(f"{len(recentes)} notices Arcachon mises à l'inventaire depuis le {date_limite}.")

    base_mosaique = [n for n in recentes if n['type_document'] == 'LIVRE']
    couvertures = resoudre_couvertures(base_mosaique)
    nouveautes_mosaique = [n for n in base_mosaique if n['isbn'] in couvertures]
    regenerer_fichier(
        FICHIER_MOSAIQUE, "BOOKS",
        [_ligne_objet(n, couvertures[n['isbn']], "extraUrl") for n in nouveautes_mosaique],
    )
    _log(f"Mosaïque régénérée : {len(nouveautes_mosaique)} titres "
         f"(sur {len(base_mosaique)} éligibles, {len(base_mosaique) - len(nouveautes_mosaique)} sans couverture accessible).")

    base_diaporama = [n for n in base_mosaique if n['public_vise'] in PUBLICS_JEUNESSE]
    couvertures_diaporama = {isbn: url for isbn, url in couvertures.items()
                              if isbn in {n['isbn'] for n in base_diaporama}}
    manquantes = [n for n in base_diaporama if n['isbn'] not in couvertures_diaporama]
    if manquantes:
        couvertures_diaporama.update(resoudre_couvertures(manquantes))
    nouveautes_diaporama = [n for n in base_diaporama if n['isbn'] in couvertures_diaporama]
    regenerer_fichier(
        FICHIER_DIAPORAMA, "SLIDES",
        [_ligne_objet(n, couvertures_diaporama[n['isbn']], "img") for n in nouveautes_diaporama],
    )
    _log(f"Diaporama jeunesse régénéré : {len(nouveautes_diaporama)} titres.")

    if sans_upload:
        _log("--sans-upload : envoi OVH ignoré.")
        return
    televerser_sftp([FICHIER_MOSAIQUE, FICHIER_DIAPORAMA])
    _log("Terminé.")


if __name__ == "__main__":
    main()
