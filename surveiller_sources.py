#!/usr/bin/env python3
"""
surveiller_sources.py — Contrôle de santé des sources d'enrichissement et de
veille. Alerte quand une source devient muette.

POURQUOI (audit du 2026-07-25) : le défaut structurel du système n'est pas le
manque de sources, c'est l'absence de surveillance. Cultura est restée cassée
plusieurs semaines sans que personne ne s'en aperçoive -- le moteur avale les
échecs en silence (chaque source est dans un try/except qui renvoie None).
Résultat : l'enrichissement continuait de tourner en produisant beaucoup moins,
sans le moindre signal.

Ce script teste chaque source sur des cas de référence connus, compare au
résultat attendu, et signale toute régression. À lancer chaque semaine
(intégré à veille_hebdomadaire.sh) ou à la demande.

CE QU'IL VÉRIFIE
  1. Sources d'ENRICHISSEMENT : chaque source répond-elle encore, et rend-elle
     bien la série/le tome quand elle est censée le faire ?
  2. Sources de VEILLE : les flux et pages sont-ils toujours lisibles ?
  3. Fraîcheur de la liste des prix littéraires (rafraîchie 2x/an : si elle
     vieillit trop, la tâche planifiée a probablement échoué).

SORTIE : un rapport lisible + une notification macOS si une source
CRITIQUE tombe (celles qui portent la série/le tome).

Usage :
    python3 surveiller_sources.py
    python3 surveiller_sources.py --silencieux   (pas de notification macOS)
"""

import datetime
import os
import re
import subprocess
import sys

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)
import db  # noqa: E402 — applique aussi le correctif SSL (certifi) sur macOS

import requests  # noqa: E402

EN_TETES = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# ── Cas de référence ──────────────────────────────────────────────────────
# Choisis parce qu'ils sont stables et bien documentés partout.
ISBN_MANGA = "9782871298168"     # Naruto t.19  -> série ET tome attendus
ISBN_ROMAN = "9782075105170"     # Harry Potter t.6 -> série attendue
# Cas de référence propre à la BnF : son catalogue SRU ne couvre ni les mangas
# japonais ni certaines éditions récentes de littérature étrangère (vérifié le
# 2026-07-25 : ni Naruto ni Harry Potter t.6 ne répondent). Le Club des Cinq,
# lui, est bien référencé -- c'est donc le bon témoin pour cette source.
ISBN_BNF = "9782014018134"       # Le Club des Cinq et le passage secret

# Sources CRITIQUES = celles qui portent l'information série/tome. Si l'une
# tombe, la qualité de l'enrichissement chute sans autre signal.
SOURCES_CRITIQUES = ("Place des Libraires", "Cultura")


def _log(msg=""):
    print(msg, flush=True)


def _notifier_macos(titre, message):
    """Notification système, best-effort (ne doit jamais faire échouer le
    contrôle lui-même)."""
    try:
        script = f'display notification {message!r} with title {titre!r} sound name "Basso"'
        subprocess.run(["osascript", "-e", script], timeout=5, check=False)
    except Exception:
        pass


# ── 1. Sources d'enrichissement ───────────────────────────────────────────
def controler_enrichissement():
    """Teste chaque source du moteur. Renvoie (rapport, sources_muettes)."""
    _log("═" * 66)
    _log("1. SOURCES D'ENRICHISSEMENT")
    _log("═" * 66)

    try:
        import moteur_recherche as m
    except Exception as e:
        _log(f"  ✗ moteur_recherche inutilisable : {e}")
        return ["moteur_recherche inutilisable"], list(SOURCES_CRITIQUES)

    muettes = []
    anomalies = []

    # Chaque source est testée sur le type de document qui la concerne : la
    # BnF ne référence pas les mangas japonais par ISBN français, la tester
    # sur Naruto produirait un faux négatif hebdomadaire (donc du bruit, donc
    # une alerte qu'on finirait par ignorer).
    isbn_par_source = {"BnF": ISBN_BNF}

    for nom, fn in m.SOURCES:
        isbn_test = isbn_par_source.get(nom, ISBN_MANGA)
        try:
            res = fn(isbn_test)
        except Exception as e:
            res = None
            _log(f"  ✗ {nom:22} ERREUR {type(e).__name__}")
            muettes.append(nom)
            continue

        if not res or not res.get("titre"):
            marque = "✗" if nom in SOURCES_CRITIQUES else "∅"
            _log(f"  {marque} {nom:22} muette")
            muettes.append(nom)
            continue

        serie = res.get("serie") or ""
        tome = res.get("tome") or ""
        detail = f"titre='{str(res.get('titre'))[:24]}'"
        if serie:
            detail += f" série='{serie[:16]}'"
        if tome:
            detail += f" tome={tome}"
        _log(f"  ✓ {nom:22} {detail}")

        # Une source critique qui répond mais ne rend plus la série est un
        # signal aussi important qu'une panne : c'est ce qui est arrivé à
        # Cultura (page devenue JavaScript, titre encore lisible mais vide).
        if nom in SOURCES_CRITIQUES and not serie:
            attendu = {ISBN_BNF: "Le club des Cinq",
                       ISBN_ROMAN: "Harry Potter"}.get(isbn_test, "Naruto")
            anomalies.append(f"{nom} répond mais ne rend plus la série")
            _log(f"    ⚠ {nom} ne rend plus la série (attendu : {attendu})")

    critiques_muettes = [n for n in muettes if n in SOURCES_CRITIQUES]
    _log("")
    _log(f"  → {len(m.SOURCES) - len(muettes)}/{len(m.SOURCES)} sources répondent")
    if critiques_muettes:
        _log(f"  → ⚠ SOURCE CRITIQUE MUETTE : {', '.join(critiques_muettes)}")
    return anomalies + [f"{n} muette" for n in critiques_muettes], critiques_muettes


# ── 2. Sources de veille ──────────────────────────────────────────────────
def controler_veille():
    """Vérifie que les flux et pages de veille répondent et contiennent bien
    des documents."""
    _log("")
    _log("═" * 66)
    _log("2. SOURCES DE VEILLE")
    _log("═" * 66)

    controles = [
        ("BnF Nouveautés Éditeurs",
         "https://nouveautes-editeurs.bnf.fr/neRss?jeunesse=true", "<item>"),
        ("Ricochet (catalogue livres)",
         "https://www.ricochet-jeunes.org/livres/rss.xml", "<item>"),
        ("Place des Libraires (coups de cœur)",
         "https://www.placedeslibraires.fr/coups-de-coeur/", "/livre/"),
        ("Place des Libraires (sélection jeunesse)",
         "https://www.placedeslibraires.fr/list-105447/notre-selection-jeunesse/", "/livre/"),
    ]

    problemes = []
    for nom, url, marqueur in controles:
        try:
            r = requests.get(url, headers=EN_TETES, timeout=20, allow_redirects=True)
            if r.status_code != 200:
                _log(f"  ✗ {nom:38} HTTP {r.status_code}")
                problemes.append(f"{nom} : HTTP {r.status_code}")
                continue
            texte = r.text or ""
            n = texte.count(marqueur)
            if n == 0:
                _log(f"  ✗ {nom:38} répond mais AUCUN document")
                problemes.append(f"{nom} : aucun document")
            else:
                _log(f"  ✓ {nom:38} {n} occurrence(s) de '{marqueur}'")
        except Exception as e:
            _log(f"  ✗ {nom:38} {type(e).__name__}")
            problemes.append(f"{nom} : {type(e).__name__}")
    return problemes


# ── 3. Fraîcheur de la liste des prix littéraires ─────────────────────────
def controler_prix_litteraires():
    """La liste Sorcières/Incorruptibles est figée et rafraîchie 2x/an par une
    tâche planifiée. Si son millésime devient trop ancien, la tâche a
    probablement échoué -- sans quoi personne ne s'en apercevrait."""
    _log("")
    _log("═" * 66)
    _log("3. LISTE DES PRIX LITTÉRAIRES (figée, rafraîchie 2x/an)")
    _log("═" * 66)

    chemin = os.path.join(DOSSIER, "veille_prix_litteraires.py")
    if not os.path.exists(chemin):
        _log("  ✗ veille_prix_litteraires.py introuvable")
        return ["veille_prix_litteraires.py introuvable"]

    contenu = open(chemin, encoding="utf-8").read()
    annees = [int(a) for a in re.findall(r'"prix": "[^"]*?(20\d{2})', contenu)]
    if not annees:
        _log("  ⚠ aucun millésime détecté dans la liste")
        return ["millésime des prix illisible"]

    plus_recent = max(annees)
    courante = datetime.date.today().year
    nb = contenu.count('"titre":')
    _log(f"  {nb} titres, millésime le plus récent : {plus_recent}")

    if plus_recent < courante:
        _log(f"  ⚠ la liste date de {plus_recent} alors qu'on est en {courante} :")
        _log("    la tâche de rafraîchissement (5 avril / 5 septembre) a-t-elle tourné ?")
        return [f"prix littéraires figés à {plus_recent}"]
    _log("  ✓ liste à jour")
    return []


def main():
    silencieux = "--silencieux" in sys.argv
    _log(f"CONTRÔLE DE SANTÉ DES SOURCES — {datetime.datetime.now():%Y-%m-%d %H:%M}")
    _log("")

    alertes_enr, critiques = controler_enrichissement()
    alertes_veille = controler_veille()
    alertes_prix = controler_prix_litteraires()

    toutes = alertes_enr + alertes_veille + alertes_prix

    _log("")
    _log("═" * 66)
    _log("SYNTHÈSE")
    _log("═" * 66)
    if not toutes:
        _log("  ✓ Toutes les sources répondent normalement.")
        return 0

    for a in toutes:
        _log(f"  ⚠ {a}")

    # On ne dérange l'utilisateur que si une source CRITIQUE est touchée :
    # une source secondaire muette n'a pas d'impact réel sur la qualité.
    if critiques or any("ne rend plus la série" in a for a in toutes):
        _log("")
        _log("  → Impact RÉEL sur la qualité de l'enrichissement (série/tome).")
        if not silencieux:
            _notifier_macos(
                "Veille MAAT — source critique en panne",
                "Une source qui fournit série/tome ne répond plus. "
                "Voir surveiller_sources.py.",
            )
    else:
        _log("")
        _log("  → Sources secondaires uniquement : pas d'impact sur série/tome.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
