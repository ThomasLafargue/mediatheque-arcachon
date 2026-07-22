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
mois glissants (date_acquisition), avec une image de couverture connue.
  - Mosaïque  : type_document = 'LIVRE' (Livre/BD/Manga/Album/Documentaire —
    exclut nativement DVD/JEU/CD/REVUE, comme dans la version manuelle).
  - Diaporama : même base, restreinte au public Jeunesse/Ado/Tout public.

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
        WHERE n.type_document = 'LIVRE'
          AND e.date_acquisition >= ?
          AND n.image_url IS NOT NULL AND n.image_url != ''
          {condition_public}
        GROUP BY n.identifiant
        ORDER BY e.date_acquisition DESC
    """
    lignes = conn.execute(sql, parametres).fetchall()
    return [dict(zip(COLONNES, ligne)) for ligne in lignes]


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
        regenerer_fichier(
            FICHIER_MOSAIQUE, "BOOKS",
            [_ligne_objet(r, "extraUrl") for r in nouveautes_mosaique],
        )
        _log(f"Mosaïque régénérée : {len(nouveautes_mosaique)} titres.")

        nouveautes_diaporama = recuperer_nouveautes(conn, date_limite, filtre_jeunesse=True)
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
