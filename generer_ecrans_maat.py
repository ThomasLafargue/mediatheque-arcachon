#!/usr/bin/env python3
"""
generer_ecrans_maat.py — Régénère les 2 écrans numériques (mosaïque tactile
du hall + diaporama jeunesse) à partir des acquisitions récentes en base, et
les envoie automatiquement sur OVH par SFTP.

Remplace la procédure manuelle mensuelle décrite dans
"ecrans maat/resume-projet-kiosque-mediatheque.md" (export UNIMARC séparé
envoyé à une autre conversation Claude, upload à la main via Cyberduck) :
ce script réutilise directement la base déjà enrichie (couvertures, résumés,
cotes...) au lieu de reparser un fichier MARC à part, et tourne chaque
semaine via import_hebdomadaire.sh, juste après le traitement du .mrc.

Sélection : tout exemplaire du fonds Arcachon acquis dans les 3 derniers
mois glissants (date_acquisition), avec une image de couverture connue ET
vérifiée accessible (voir filtrer_images_valides -- certaines sources
bloquent l'affichage direct depuis un autre site, ce qui donnait des
tuiles/diapositives vides malgré une URL enregistrée en base).
  - Mosaïque  : tout type_document SAUF DVD, JEU (jeux vidéo + jeux de
    société), CD et AUTRE (catégorie fourre-tout non fiable -- exclue par
    prudence le 2026-07-22 après le signalement d'un jeu de société affiché
    malgré le filtre : probablement un exemplaire classé AUTRE plutôt que
    JEU côté Decalog) -- inclut donc Livre/BD/Manga/Album/Documentaire/Revue.
  - Diaporama : même base, restreinte au public Jeunesse/Ado/Tout public.

Équilibrage jeunesse/adulte (2026-07-22) : la jeunesse (BD/mangas) est très
majoritaire dans les couvertures disponibles, ce qui rendait la mosaïque
quasi exclusivement jeunesse à l'affichage. plafonner_jeunesse() limite
désormais la part de jeunesse à PLAFOND_RATIO_JEUNESSE fois le nombre de
titres non-jeunesse disponibles, plutôt que d'attendre que le backfill
rattrape l'écart sur plusieurs jours/semaines.

Les 2 fichiers HTML sont réécrits EN PLACE (même nom de fichier à chaque
fois, puisque les écrans OVH pointent vers une URL fixe) : pas de fichiers
datés à nettoyer ici, contrairement aux imports hebdo classiques.

Upload SFTP automatique si OVH_SFTP_HOST / OVH_SFTP_USER / OVH_SFTP_PASSWORD
sont définies dans .env -- sinon les fichiers sont simplement régénérés en
local et un message l'indique (à pousser soi-même via Cyberduck).

Usage :
    python3 generer_ecrans_maat.py                 (génère + envoie sur OVH)
    python3 generer_ecrans_maat.py --sans-upload    (génère seulement, pour tester)
"""
import os
import re
import sys
import datetime
import concurrent.futures
import urllib.request
import urllib.error

DOSSIER = os.path.dirname(os.path.abspath(__file__))
DOSSIER_ECRANS = os.path.join(DOSSIER, "ecrans maat")
FICHIER_MOSAIQUE = os.path.join(DOSSIER_ECRANS, "mediatheque-cobas-mosaique.html")
FICHIER_DIAPORAMA = os.path.join(DOSSIER_ECRANS, "mediatheque-diaporama-jeunesse.html")

FENETRE_MOIS = 3
PUBLICS_JEUNESSE = ("Jeune", "Jeunesse", "Ado (12+)", "Adolescent", "Tout public")

sys.path.insert(0, DOSSIER)
import db


def _log(message):
    horodatage = datetime.datetime.now().isoformat(timespec="seconds")
    print(f"[{horodatage}] {message}", flush=True)


def _date_limite():
    """AAAA-MM-JJ correspondant à 'aujourd'hui moins FENETRE_MOIS mois'."""
    aujourd_hui = datetime.date.today()
    mois_total = aujourd_hui.month - 1 - FENETRE_MOIS
    annee = aujourd_hui.year + mois_total // 12
    mois = mois_total % 12 + 1
    jour = min(aujourd_hui.day, 28)  # évite les débordements de fin de mois
    return datetime.date(annee, mois, jour).isoformat()


def _echapper_js(valeur):
    """Chaîne JS entre guillemets doubles, même format que celui déjà
    utilisé dans les 2 fichiers HTML existants (const BOOKS=[{t:"...",...})."""
    if valeur is None:
        valeur = ""
    valeur = str(valeur)
    valeur = valeur.replace("\\", "\\\\").replace('"', '\\"')
    valeur = valeur.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return '"' + valeur + '"'


COLONNES = ["identifiant", "titre", "createurs", "date_publication", "editeur",
            "resume", "image_url", "cote", "public_vise", "support", "date_acquisition"]


def recuperer_nouveautes(conn, date_limite, filtre_jeunesse):
    condition_public = ""
    parametres = [date_limite]
    if filtre_jeunesse:
        placeholders = ",".join("?" for _ in PUBLICS_JEUNESSE)
        condition_public = f" AND e.public_vise IN ({placeholders})"
        parametres += list(PUBLICS_JEUNESSE)
    sql = f"""
        SELECT n.identifiant, n.titre, n.createurs, n.date_publication, n.editeur,
               n.resume, n.image_url, e.cote, e.public_vise, e.support, e.date_acquisition
        FROM notice n
        JOIN exemplaire e ON e.identifiant = n.identifiant
        WHERE n.type_document NOT IN ('DVD', 'JEU', 'CD', 'AUTRE')
          AND e.date_acquisition >= ?
          AND n.image_url IS NOT NULL AND n.image_url != ''
          {condition_public}
        GROUP BY n.identifiant
        ORDER BY e.date_acquisition DESC
    """
    lignes = conn.execute(sql, parametres).fetchall()
    return [dict(zip(COLONNES, ligne)) for ligne in lignes]


TIMEOUT_VALIDATION_SECONDES = 6
EN_TETES_VALIDATION = {"User-Agent": "Mozilla/5.0 (compatible; MediathequeArcachonEcrans/1.0)"}


def _image_accessible(url):
    """Vérifie que l'URL de couverture répond bien avec une vraie image,
    pour éviter des tuiles/diapositives vides sur les écrans (certaines
    sources -- pages communautaires notamment -- refusent l'affichage
    direct depuis un autre site : 403/404 à l'appel). En cas de doute
    (timeout, erreur réseau passagère lors de la génération) on GARDE le
    titre plutôt que de l'exclure à tort -- seul un refus explicite du
    serveur (403/404/410) fait tomber l'image."""
    if not url:
        return False
    for methode in ("HEAD", "GET"):
        requete = urllib.request.Request(url, headers=EN_TETES_VALIDATION, method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=TIMEOUT_VALIDATION_SECONDES) as reponse:
                type_contenu = reponse.headers.get("Content-Type", "")
                return type_contenu.startswith("image/")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                if methode == "HEAD":
                    continue  # certains serveurs bloquent HEAD mais acceptent GET
                return False
            return True  # code HTTP inattendu (500, 429...) : incident probable, on garde
        except Exception:
            if methode == "HEAD":
                continue
            return True  # échec réseau après les 2 tentatives : on garde par prudence
    return True


def filtrer_images_valides(lignes):
    """Teste en parallèle toutes les URLs de couverture d'un lot et retire
    les titres dont l'image est explicitement refusée par son serveur."""
    urls = sorted({ligne["image_url"] for ligne in lignes if ligne["image_url"]})
    if not urls:
        return lignes
    resultats = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executeur:
        futurs = {executeur.submit(_image_accessible, url): url for url in urls}
        for futur in concurrent.futures.as_completed(futurs):
            resultats[futurs[futur]] = futur.result()
    retenues = [l for l in lignes if resultats.get(l["image_url"], True)]
    nb_retirees = len(lignes) - len(retenues)
    if nb_retirees:
        _log(f"{nb_retirees} couverture(s) inaccessible(s) (403/404) écartée(s) sur {len(urls)} URL testées.")
    return retenues


PLAFOND_RATIO_JEUNESSE = 2


def plafonner_jeunesse(lignes):
    """Limite la part de titres jeunesse dans la mosaïque à
    PLAFOND_RATIO_JEUNESSE fois le nombre de titres non-jeunesse
    disponibles, pour éviter qu'elle soit quasi exclusivement jeunesse
    tant que le backfill des couvertures n'a pas rattrapé son retard sur
    les autres publics. Garde toujours TOUS les titres non-jeunesse."""
    non_jeunesse = [l for l in lignes if l["public_vise"] not in PUBLICS_JEUNESSE]
    jeunesse = [l for l in lignes if l["public_vise"] in PUBLICS_JEUNESSE]
    plafond = max(len(non_jeunesse) * PLAFOND_RATIO_JEUNESSE, 40)
    if len(jeunesse) > plafond:
        _log(f"Part jeunesse plafonnée : {len(jeunesse)} -> {plafond} titres "
             f"(pour {len(non_jeunesse)} non-jeunesse disponibles).")
        jeunesse = jeunesse[:plafond]
    return non_jeunesse + jeunesse


NO_CACHE_META = (
    '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">\n'
    '<meta http-equiv="Pragma" content="no-cache">\n'
    '<meta http-equiv="Expires" content="0">\n'
)


def _empecher_cache_navigateur(contenu):
    """Ajoute des balises anti-cache dans le <head> si absentes, pour que
    l'écran affiche toujours la dernière version générée au lieu d'une
    version mise en cache par le navigateur (source de confusion : on
    croit voir un bug de contenu alors que c'est juste une vieille page)."""
    if "Cache-Control" in contenu:
        return contenu
    return contenu.replace("<head>", "<head>\n" + NO_CACHE_META, 1)


def _ligne_objet(ligne, champ_image):
    return "  {t:%s,a:%s,y:%s,ed:%s,cote:%s,pub:%s,sup:%s,d:%s,isbn:%s,%s:%s}," % (
        _echapper_js(ligne["titre"]),
        _echapper_js(ligne["createurs"]),
        _echapper_js(ligne["date_publication"]),
        _echapper_js(ligne["editeur"]),
        _echapper_js(ligne["cote"]),
        _echapper_js(ligne["public_vise"]),
        _echapper_js(ligne["support"]),
        _echapper_js(ligne["resume"]),
        _echapper_js(ligne["identifiant"]),
        champ_image,
        _echapper_js(ligne["image_url"]),
    )


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
    conn = db.connect()
    try:
        date_limite = _date_limite()
        _log(f"Nouveautés depuis le {date_limite} (fenêtre de {FENETRE_MOIS} mois glissants).")

        nouveautes_mosaique = recuperer_nouveautes(conn, date_limite, filtre_jeunesse=False)
        nouveautes_mosaique = filtrer_images_valides(nouveautes_mosaique)
        nouveautes_mosaique = plafonner_jeunesse(nouveautes_mosaique)
        regenerer_fichier(
            FICHIER_MOSAIQUE, "BOOKS",
            [_ligne_objet(r, "extraUrl") for r in nouveautes_mosaique],
        )
        _log(f"Mosaïque régénérée : {len(nouveautes_mosaique)} titres.")

        nouveautes_diaporama = recuperer_nouveautes(conn, date_limite, filtre_jeunesse=True)
        nouveautes_diaporama = filtrer_images_valides(nouveautes_diaporama)
        regenerer_fichier(
            FICHIER_DIAPORAMA, "SLIDES",
            [_ligne_objet(r, "img") for r in nouveautes_diaporama],
        )
        _log(f"Diaporama jeunesse régénéré : {len(nouveautes_diaporama)} titres.")
    finally:
        conn.close()

    if sans_upload:
        _log("--sans-upload : envoi OVH ignoré.")
        return
    televerser_sftp([FICHIER_MOSAIQUE, FICHIER_DIAPORAMA])
    _log("Terminé.")


if __name__ == "__main__":
    main()
