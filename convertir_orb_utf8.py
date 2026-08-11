#!/usr/bin/env python3
"""
convertir_orb_utf8.py — Convertit un export UNIMARC d'ORB (encodage ISO 5426,
leur réglage par défaut) en UTF-8 propre pour l'import Decalog.

CONTEXTE (2026-08-07) : les notices des bons de commande ORB arrivaient avec
les accents cassés dans Decalog (« imprim?e », « d?etails »). Cause : ORB
exporte par défaut en ISO 5426 (accents codés AVANT la lettre) alors que
Decalog attend de l'UTF-8. La vraie solution est de faire passer le compte
ORB en `unimarc_encoding: utf8` (demande faite à Decitre) ; ce script est
le remède local en attendant.

Il reconstruit chaque notice ISO 2709 (répertoire et longueurs recalculés)
et met à jour la zone 100 (jeu de caractères → 50 = Unicode).

Usage :
    python3 convertir_orb_utf8.py "ORB_bon_de_commande_....not"
    → écrit le même fichier suffixé " (utf8).not"
"""
import os
import sys
import unicodedata

COMB = {0xC0: '̉', 0xC1: '̀', 0xC2: '́', 0xC3: '̂',
        0xC4: '̃', 0xC5: '̄', 0xC6: '̆', 0xC7: '̇',
        0xC8: '̈', 0xC9: '̈', 0xCA: '̊', 0xCB: '̧',
        0xCC: '̲', 0xCD: '̋', 0xCE: '̛', 0xCF: '̧',
        0xD0: '̧'}
SIMPLES = {0xA1: '¡', 0xA3: '£', 0xA6: '†', 0xA7: '§', 0xA8: "'",
           0xA9: "'", 0xAB: '«', 0xAD: '©', 0xAE: '®', 0xB0: 'ʿ',
           0xB1: 'ʾ', 0xBB: '»', 0xE1: 'Æ', 0xE8: 'Ł', 0xE9: 'Ø',
           0xEA: 'Œ', 0xEC: 'Þ', 0xF1: 'æ', 0xF3: 'ð', 0xF5: 'ı',
           0xF8: 'ł', 0xF9: 'ø', 0xFA: 'œ', 0xFB: 'ß', 0xFC: 'þ'}


def iso5426_vers_utf8(octets):
    sortie, attente = [], []
    for b in octets:
        if b in COMB:
            attente.append(COMB[b])
        elif b < 0x80:
            sortie.append(chr(b))
            sortie.extend(attente)
            attente = []
        elif b in SIMPLES:
            sortie.append(SIMPLES[b])
            sortie.extend(attente)
            attente = []
        else:
            sortie.append('?')
            attente = []
    return unicodedata.normalize("NFC", "".join(sortie)).encode("utf-8")


def convertir_notice(notice):
    entete = notice[:24].decode("ascii", "replace")
    base = int(entete[12:17])
    repertoire = notice[24:base - 1].decode("ascii", "replace")
    corps = notice[base:]
    zones = []
    for i in range(0, len(repertoire) // 12 * 12, 12):
        tag = repertoire[i:i + 3]
        lg = int(repertoire[i + 3:i + 7])
        pos = int(repertoire[i + 7:i + 12])
        contenu = corps[pos:pos + lg].rstrip(b"\x1e")
        contenu = iso5426_vers_utf8(contenu)
        if tag == "100":
            # jeu de caractères (pos 26-29 du $a) : 0103 (ISO 5426) → 50 (Unicode)
            contenu = contenu.replace(b"0103", b"50  ", 1)
        zones.append((tag, contenu))

    nouveau_rep, nouveau_corps, pos = [], [], 0
    for tag, contenu in zones:
        champ = contenu + b"\x1e"
        nouveau_rep.append(f"{tag}{len(champ):04d}{pos:05d}")
        nouveau_corps.append(champ)
        pos += len(champ)
    rep = "".join(nouveau_rep).encode("ascii") + b"\x1e"
    corps = b"".join(nouveau_corps)
    base = 24 + len(rep)
    total = base + len(corps) + 1
    entete = (f"{total:05d}" + entete[5:12] + f"{base:05d}" + entete[17:24]
              ).encode("ascii")
    return entete + rep + corps + b"\x1d"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    chemin = sys.argv[1]
    data = open(chemin, "rb").read()
    notices = [n for n in data.split(b"\x1d") if len(n) > 30]
    sortie = b"".join(convertir_notice(n) for n in notices)
    racine, ext = os.path.splitext(chemin)
    chemin_sortie = f"{racine} (utf8){ext or '.not'}"
    open(chemin_sortie, "wb").write(sortie)
    print(f"✓ {len(notices)} notices converties → {os.path.basename(chemin_sortie)}")


if __name__ == "__main__":
    main()
