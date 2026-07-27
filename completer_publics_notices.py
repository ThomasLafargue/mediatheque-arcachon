#!/usr/bin/env python3
"""
completer_publics_notices.py — Comble les dernières notices SANS public visé
(22 constatées à l'audit du 2026-07-27). Demande de Thomas : tous les
documents doivent avoir un public.

Deux sources, dans l'ordre de fiabilité :
  1. le public de leurs EXEMPLAIRES (zone 995 Decalog) — donnée de terrain ;
  2. à défaut, « Tout public » — l'aveu honnête qu'on ne sait pas, plutôt
     qu'un « Adulte » deviné.

Idempotent : ne touche que les notices dont le public est vide.

Usage :
    python3 completer_publics_notices.py               (simulation)
    python3 completer_publics_notices.py --appliquer
"""
import sys

sys.path.insert(0, ".")
import db  # noqa: E402
from public_vise import normaliser  # noqa: E402


def main():
    appliquer = "--appliquer" in sys.argv
    conn = db.connect()
    lignes = conn.execute(
        "SELECT n.identifiant, n.titre, "
        "       (SELECT e.public_vise FROM exemplaire e "
        "        WHERE e.identifiant = n.identifiant "
        "        AND e.public_vise IS NOT NULL AND e.public_vise != '' "
        "        LIMIT 1) "
        "FROM notice n "
        "WHERE n.public_vise IS NULL OR n.public_vise = ''").fetchall()

    print(f"{len(lignes)} notice(s) sans public visé."
          + ("" if appliquer else "  [SIMULATION]"))
    via_ex = via_defaut = 0
    for ident, titre, pub_ex in lignes:
        public = normaliser(pub_ex) if pub_ex else "Tout public"
        if pub_ex:
            via_ex += 1
        else:
            via_defaut += 1
        print(f"  {str(titre or ident)[:52]:54} -> {public}"
              f"{'  (exemplaire)' if pub_ex else '  (défaut)'}")
        if appliquer:
            conn.execute(
                "UPDATE notice SET public_vise = ? WHERE identifiant = ?",
                (public, ident))
    if appliquer:
        conn.commit()
    conn.close()
    print(f"\n{via_ex} via exemplaire, {via_defaut} en « Tout public ».")
    if not appliquer:
        print("Pour appliquer :  python3 completer_publics_notices.py --appliquer")


if __name__ == "__main__":
    main()
