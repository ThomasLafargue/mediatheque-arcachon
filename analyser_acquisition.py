"""
analyser_acquisition.py — Analyse des besoins d'acquisition

Trois sources d'analyse :
1. Signaux internes   → SQL sur notre base (auteurs manquants, genres, rotation)
2. Météo              → Open-Meteo archive (corrélation pluie/fréquentation)
3. Démographie locale → geo.api.gouv.fr + données INSEE Arcachon

Usage dans app_conversationnel.py :
    from analyser_acquisition import analyser_besoins
    rapport = analyser_besoins(conn)
"""

import requests
import json
import datetime
import statistics

TIMEOUT = (5, 10)
HEADERS = {'Accept': 'application/json', 'User-Agent': 'MediathequeArcachon/1.0'}

# Coordonnées d'Arcachon
LAT = 44.6608
LON = -1.1674
CODE_INSEE = '33009'


# ─────────────────────────────────────────────────────────────────────────────
# 1. SIGNAUX INTERNES — ANALYSE SQL
# ─────────────────────────────────────────────────────────────────────────────

REQUETES_SIGNAUX = {

    'auteurs_top_sans_tous_titres': """
        SELECT
            createurs,
            COUNT(DISTINCT identifiant) AS titres_presents,
            SUM(nb_prets_total)         AS total_prets,
            ROUND(CAST(SUM(nb_prets_total) AS FLOAT) / COUNT(DISTINCT identifiant), 1)
                                        AS prets_par_titre
        FROM notice
        WHERE createurs IS NOT NULL AND createurs != ''
          AND nb_prets_total > 0
        GROUP BY createurs
        HAVING total_prets >= 15
        ORDER BY total_prets DESC
        LIMIT 25
    """,

    'exemplaires_uniques_surempruntes': """
        SELECT
            n.titre, n.createurs, n.identifiant,
            n.genre, n.categorie, n.public_vise,
            COUNT(e.id)           AS nb_exemplaires,
            SUM(e.nb_prets_total) AS total_prets
        FROM notice n
        JOIN exemplaire e ON n.identifiant = e.identifiant
        GROUP BY n.identifiant
        HAVING nb_exemplaires = 1 AND total_prets >= 12
        ORDER BY total_prets DESC
        LIMIT 20
    """,

    'genres_rotation': """
        SELECT
            genre,
            public_vise,
            COUNT(DISTINCT identifiant) AS nb_titres,
            SUM(nb_prets_total)         AS total_prets,
            ROUND(CAST(SUM(nb_prets_total) AS FLOAT) / COUNT(DISTINCT identifiant), 1)
                                        AS rotation_par_titre
        FROM notice
        WHERE genre IS NOT NULL AND genre != '' AND nb_prets_total > 0
        GROUP BY genre, public_vise
        HAVING nb_titres >= 3
        ORDER BY rotation_par_titre DESC
        LIMIT 30
    """,

    'categories_rotation': """
        SELECT
            categorie,
            COUNT(DISTINCT identifiant) AS nb_titres,
            SUM(nb_prets_total)         AS total_prets,
            ROUND(CAST(SUM(nb_prets_total) AS FLOAT) / COUNT(DISTINCT identifiant), 1)
                                        AS rotation_par_titre
        FROM notice
        WHERE categorie IS NOT NULL
        GROUP BY categorie
        ORDER BY rotation_par_titre DESC
    """,

    'recents_peu_empruntes': """
        SELECT titre, createurs,
               SUBSTR(date_publication, 1, 4) AS annee,
               genre, categorie, nb_prets_total, identifiant
        FROM notice
        WHERE SUBSTR(date_publication, 1, 4) >= '2024'
          AND nb_prets_total < 3
          AND type_document = 'LIVRE'
        ORDER BY date_publication DESC, nb_prets_total ASC
        LIMIT 30
    """,

    'series_incompletes': """
        SELECT
            serie,
            COUNT(DISTINCT tome)       AS nb_tomes_presents,
            MAX(CAST(tome AS INTEGER)) AS tome_max,
            GROUP_CONCAT(DISTINCT tome) AS tomes,
            SUM(nb_prets_total)        AS total_prets_serie
        FROM notice
        WHERE serie IS NOT NULL AND serie != ''
          AND tome IS NOT NULL AND tome != ''
          AND tome GLOB '[0-9]*'
        GROUP BY serie
        HAVING nb_tomes_presents < tome_max
           AND tome_max > 1
           AND total_prets_serie >= 5
        ORDER BY total_prets_serie DESC
        LIMIT 25
    """,

    'public_sous_represente': """
        SELECT
            public_vise,
            COUNT(DISTINCT identifiant) AS nb_titres,
            SUM(nb_prets_total)         AS total_prets,
            ROUND(CAST(SUM(nb_prets_total) AS FLOAT) / COUNT(DISTINCT identifiant), 1)
                                        AS rotation
        FROM notice
        WHERE public_vise IS NOT NULL
        GROUP BY public_vise
        ORDER BY rotation DESC
    """,

    'annees_anciennete': """
        SELECT
            CASE
                WHEN SUBSTR(date_publication,1,4) >= '2023' THEN '2023-2026 (recent)'
                WHEN SUBSTR(date_publication,1,4) >= '2020' THEN '2020-2022'
                WHEN SUBSTR(date_publication,1,4) >= '2015' THEN '2015-2019'
                WHEN SUBSTR(date_publication,1,4) >= '2010' THEN '2010-2014'
                WHEN SUBSTR(date_publication,1,4) >= '2000' THEN '2000-2009'
                ELSE 'avant 2000'
            END AS periode,
            COUNT(*)            AS nb_titres,
            SUM(nb_prets_total) AS total_prets,
            ROUND(CAST(SUM(nb_prets_total) AS FLOAT) / COUNT(*), 1) AS rotation
        FROM notice
        WHERE date_publication IS NOT NULL AND date_publication != ''
        GROUP BY periode
        ORDER BY periode DESC
    """,

    'dewey_peu_representes': """
        SELECT
            SUBSTR(dewey, 1, 1) || '00' AS classe_dewey,
            COUNT(*)            AS nb_titres,
            SUM(nb_prets_total) AS total_prets
        FROM notice
        WHERE dewey IS NOT NULL AND dewey != ''
          AND type_document = 'LIVRE'
        GROUP BY classe_dewey
        ORDER BY nb_titres ASC
        LIMIT 10
    """,
}


def _colonnes_depuis_sql(sql):
    """Extrait les noms de colonnes/alias depuis une clause SELECT (compatible Turso)."""
    import re as _re
    m = _re.search(r'SELECT\s+(.*?)\s+FROM\b', sql.strip(), _re.DOTALL | _re.IGNORECASE)
    if not m:
        return []
    select_clause = m.group(1)
    # Découper par virgule en respectant les parenthèses
    parts, depth, current = [], 0, ''
    for ch in select_clause:
        if ch == '(': depth += 1; current += ch
        elif ch == ')': depth -= 1; current += ch
        elif ch == ',' and depth == 0: parts.append(current.strip()); current = ''
        else: current += ch
    if current.strip():
        parts.append(current.strip())
    cols = []
    for part in parts:
        alias = _re.search(r'\bAS\s+(\w+)\s*$', part, _re.IGNORECASE)
        if alias:
            cols.append(alias.group(1))
        else:
            words = _re.findall(r'\b(\w+)\b', part)
            cols.append(words[-1] if words else f'col{len(cols)}')
    return cols


def analyser_signaux_internes(conn):
    """
    Exécute les requêtes d'analyse et retourne un dict avec les résultats.
    conn : connexion db.py active (compatible Turso — pas de cursor.description)
    """
    resultats = {}
    for nom, sql in REQUETES_SIGNAUX.items():
        try:
            rows = conn.execute(sql.strip()).fetchall()
            cols = _colonnes_depuis_sql(sql)
            if cols and rows:
                lignes = [dict(zip(cols, row)) for row in rows]
            else:
                lignes = [list(row) for row in rows]
            resultats[nom] = {
                'colonnes': cols,
                'lignes': lignes,
                'nb': len(rows),
            }
        except Exception as e:
            resultats[nom] = {'erreur': str(e), 'nb': 0, 'lignes': []}
    return resultats


def resumer_signaux(signaux):
    """Produit un résumé lisible des signaux internes pour le chat."""
    lignes = ["## ANALYSE INTERNE DES BESOINS D'ACQUISITION\n"]

    # Genres à forte rotation
    genres = signaux.get('genres_rotation', {}).get('lignes', [])
    if genres:
        lignes.append("### Genres à forte demande (rotation élevée)")
        for g in genres[:8]:
            lignes.append(
                f"- **{g.get('genre', '?')}** ({g.get('public_vise', '?')}) : "
                f"{g.get('nb_titres', 0)} titres, {g.get('rotation_par_titre', 0):.1f} prêts/titre"
            )
        lignes.append("")

    # Exemplaires uniques surpopulaires
    uniques = signaux.get('exemplaires_uniques_surempruntes', {}).get('lignes', [])
    if uniques:
        lignes.append("### Doublons urgents (1 seul exemplaire, très emprunté)")
        for u in uniques[:10]:
            lignes.append(
                f"- **{u.get('titre', '?')}** — {u.get('total_prets', 0)} prêts"
                f" ({u.get('genre', '?')})"
            )
        lignes.append("")

    # Séries incomplètes
    series = signaux.get('series_incompletes', {}).get('lignes', [])
    if series:
        lignes.append("### Séries avec tomes manquants")
        for s in series[:10]:
            lignes.append(
                f"- **{s.get('serie', '?')}** : tomes présents [{s.get('tomes', '?')}], "
                f"tome max = {s.get('tome_max', '?')}, "
                f"{s.get('total_prets_serie', 0)} prêts au total"
            )
        lignes.append("")

    # Public visé
    publics = signaux.get('public_sous_represente', {}).get('lignes', [])
    if publics:
        lignes.append("### Rotation par public visé")
        for p in publics:
            lignes.append(
                f"- {p.get('public_vise', '?')} : {p.get('nb_titres', 0)} titres, "
                f"{p.get('rotation', 0):.1f} prêts/titre"
            )
        lignes.append("")

    return "\n".join(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# 2. MÉTÉO — CORRÉLATION PLUIE / FRÉQUENTATION
# ─────────────────────────────────────────────────────────────────────────────

def obtenir_meteo_archive(date_debut='2022-01-01', date_fin=None):
    """
    Récupère les données météo historiques d'Arcachon via Open-Meteo (gratuit).
    Retourne dict {date: {pluie_mm, temp_max, ensoleillement_h}}
    """
    if date_fin is None:
        date_fin = datetime.date.today().isoformat()

    url = (
        f"https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={LAT}&longitude={LON}"
        f"&start_date={date_debut}&end_date={date_fin}"
        f"&daily=precipitation_sum,temperature_2m_max,sunshine_duration"
        f"&timezone=Europe%2FParis"
    )
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()['daily']
        meteo = {}
        for i, date in enumerate(data['time']):
            meteo[date] = {
                'pluie_mm': data['precipitation_sum'][i] or 0,
                'temp_max': data['temperature_2m_max'][i] or 0,
                'ensoleillement_h': round((data['sunshine_duration'][i] or 0) / 3600, 1),
            }
        return meteo
    except Exception as e:
        return {'erreur': str(e)}


def correlate_meteo_frequentation(conn, meteo=None):
    """
    Croise les données de fréquentation avec la météo pour identifier
    quels jours (type météo) génèrent le plus de visites.

    Retourne un dict avec :
    - correlation pluie → fréquentation
    - corrélation chaleur → fréquentation
    - genres préférés par temps de pluie vs beau temps
    """
    if meteo is None or 'erreur' in meteo:
        return {'erreur': 'Données météo non disponibles'}

    # Récupérer la fréquentation journalière
    try:
        rows = conn.execute(
            "SELECT date, nb_entrees FROM frequentation ORDER BY date"
        ).fetchall()
    except Exception:
        return {'erreur': 'Table fréquentation non accessible'}

    # Croiser avec météo
    jours_pluie = []
    jours_sec = []
    jours_chaud = []  # > 25°C
    jours_frais = []  # < 15°C

    for date_str, entrees in rows:
        if not date_str or entrees is None:
            continue
        date_iso = str(date_str)[:10]
        if date_iso not in meteo:
            continue
        m = meteo[date_iso]
        entrees = int(entrees)

        if m['pluie_mm'] >= 5:
            jours_pluie.append(entrees)
        else:
            jours_sec.append(entrees)

        if m['temp_max'] >= 25:
            jours_chaud.append(entrees)
        elif m['temp_max'] <= 15:
            jours_frais.append(entrees)

    resultats = {}

    if jours_pluie and jours_sec:
        moy_pluie = statistics.mean(jours_pluie)
        moy_sec = statistics.mean(jours_sec)
        resultats['frequentation_pluie_vs_sec'] = {
            'moy_jours_pluie': round(moy_pluie, 1),
            'moy_jours_sec': round(moy_sec, 1),
            'nb_jours_pluie': len(jours_pluie),
            'nb_jours_sec': len(jours_sec),
            'impact': round((moy_pluie - moy_sec) / moy_sec * 100, 1),
            'interpretation': (
                f"Les jours de pluie attirent {round(moy_pluie)} entrées en moyenne "
                f"vs {round(moy_sec)} par temps sec "
                f"({'plus' if moy_pluie > moy_sec else 'moins'} de fréquentation "
                f"de {abs(round((moy_pluie-moy_sec)/moy_sec*100))}%)"
            )
        }

    if jours_chaud and jours_frais:
        resultats['frequentation_chaud_vs_frais'] = {
            'moy_jours_chauds': round(statistics.mean(jours_chaud), 1),
            'moy_jours_frais': round(statistics.mean(jours_frais), 1),
        }

    return resultats


def resumer_meteo(correlation):
    """Résumé lisible de la corrélation météo/fréquentation."""
    if 'erreur' in correlation:
        return f"Météo : {correlation['erreur']}"

    lignes = ["## CORRÉLATION MÉTÉO / FRÉQUENTATION\n"]
    pv = correlation.get('frequentation_pluie_vs_sec', {})
    if pv:
        lignes.append(f"**{pv.get('interpretation', '')}**")
        lignes.append(
            f"Basé sur {pv.get('nb_jours_pluie', 0)} jours de pluie "
            f"et {pv.get('nb_jours_sec', 0)} jours secs analysés."
        )
        if pv.get('moy_jours_pluie', 0) > pv.get('moy_jours_sec', 0):
            lignes.append(
                "→ **La pluie fait venir les lecteurs.** Renforcer le fonds "
                "intérieur (lecture plaisir, BD, romans) pour ces périodes."
            )
        else:
            lignes.append(
                "→ Le beau temps n'empêche pas les visites. "
                "Anticiper la demande estivale avec des thèmes mer/vacances/aventure."
            )

    cv = correlation.get('frequentation_chaud_vs_frais', {})
    if cv:
        lignes.append(
            f"\nJours chauds (>25°C) : {cv.get('moy_jours_chauds', 0):.0f} entrées/j | "
            f"Jours frais (<15°C) : {cv.get('moy_jours_frais', 0):.0f} entrées/j"
        )

    return "\n".join(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# 3. DÉMOGRAPHIE ARCACHON
# ─────────────────────────────────────────────────────────────────────────────

# Données INSEE officielles — Dossier complet Arcachon (33009)
# Source : INSEE RP2022, exploitations principales, géographie au 01/01/2025
# Paru le 05/05/2026 — https://www.insee.fr/fr/statistiques/2011101?geo=COM-33009
PROFIL_ARCACHON = {
    'commune': 'Arcachon',
    'code_insee': '33009',
    'source': 'INSEE RP2022 — dossier complet commune (05/05/2026)',
    'url_source': 'https://www.insee.fr/fr/statistiques/2011101?geo=COM-33009',

    # Population (INSEE RP2022)
    'population_2022': 10895,
    'population_2016': 11121,
    'population_2011': 10776,
    'population_estivale_pic': 55000,  # estimé — ville touristique ×5 en août

    # Pyramide des âges 2022 (% de la population totale) — POP T0
    'tranches_age_2022': {
        '0-14 ans':      {'nb': 720,  'pct': 6.6},   # très peu d'enfants
        '15-29 ans':     {'nb': 950,  'pct': 8.7},   # peu de jeunes adultes
        '30-44 ans':     {'nb': 859,  'pct': 7.9},
        '45-59 ans':     {'nb': 1780, 'pct': 16.3},
        '60-74 ans':     {'nb': 3320, 'pct': 30.5},  # très forte proportion
        '75 ans et +':   {'nb': 3266, 'pct': 30.0},  # très forte proportion
    },
    'seniors_60_plus_pct': 60.5,  # = 30.5 + 30.0 — remarquable

    # Sexe (POP T3) — 57.5% de femmes
    'hommes': 4626,
    'femmes': 6269,
    'pct_femmes': 57.5,

    # Structure socioprofessionnelle 2022 (POP T5 — 15 ans ou plus)
    'csp_2022': {
        'retraites':         {'nb': 5769, 'pct': 56.8},  # dominance absolue
        'cadres_sup':        {'nb': 743,  'pct': 7.3},   # en hausse (+2 pts vs 2011)
        'employes':          {'nb': 1039, 'pct': 10.2},
        'prof_intermediaire':{'nb': 665,  'pct': 6.5},
        'ouvriers':          {'nb': 444,  'pct': 4.4},
        'artisans_com':      {'nb': 429,  'pct': 4.2},
        'autres_inactifs':   {'nb': 1066, 'pct': 10.5},
    },

    # Logement (LOG T1bis 2022)
    'logements_2022': {
        'total': 17717,
        'residences_principales': {'nb': 6453, 'pct': 36.4},
        'residences_secondaires':  {'nb': 11017, 'pct': 62.2},  # très élevé
        'logements_vacants':       {'nb': 247,   'pct': 1.4},
    },
    'pct_residences_secondaires': 62.2,  # ville de villégiature

    # Ménages (FAM T1 2022)
    'menages_2022': {
        'total': 6479,
        'personnes_seules': {'nb': 3488, 'pct': 53.8},  # majorité de ménages solo
        'couples_sans_enfant': {'nb': 1991, 'pct': 30.7},
        'couples_avec_enfant': {'nb': 516, 'pct': 8.0},  # très peu
        'monoparentales': {'nb': 436, 'pct': 6.7},
    },
    'taille_moyenne_menage': 1.63,  # très faible (seniors seuls)

    # Diplômes (FOR T3 2022 — population non scolarisée 15 ans+)
    'diplomes_2022': {
        'superieur_bac_plus': 39.1,   # en forte hausse (26.3% en 2011)
        'bac':               17.5,
        'cap_bep':           20.5,
        'bepc_brevet':       7.3,
        'sans_diplome':      15.6,
    },
    'pct_diplome_superieur': 39.1,

    # Revenus (REV T1 2023 — Filosofi)
    'niveau_vie_median_2023': 31420,  # euros/an — nettement supérieur à la moyenne nationale (~23 000)
    'taux_pauvrete_2023': 12.0,       # %

    # Salaires (SAL G1 2023)
    'salaire_mensuel_moyen_net_2023': 2233,  # euros EQTP (salariés privé)

    # Démographie vitale (RFD G1 2024)
    'naissances_2024': 37,   # très peu — ville vieillissante
    'deces_2024': 285,       # beaucoup — solde naturel très négatif

    # Zone de chalandise réelle — bien au-delà des résidents d'Arcachon
    'zone_chalandise': {
        'description': (
            "Arcachon est le pôle économique et culturel du sud Bassin d'Arcachon. "
            "La médiathèque (MAAT) attire une population bien supérieure aux seuls "
            "10 895 résidents de la commune."
        ),
        'population_cobas_4_communes': 68185,
        'attracteurs': [
            "Pôle économique du sud Bassin : commerces, services, administrations",
            "Gare SNCF Arcachon — porte d'entrée du réseau ferré vers Bordeaux",
            "Plusieurs lycées et collèges à Arcachon ou à proximité immédiate",
            "Centre-ville piéton avec fort flux de passage",
            "Hôpital, administrations, commerces : zone de chalandise élargie",
            "MAAT situé en centre-ville, accessible depuis toute la COBAS",
        ],
        'residences_secondaires_habitues': {
            'description': (
                "Les 62.2% de résidences secondaires ne sont PAS des touristes anonymes. "
                "Ce sont majoritairement des Bordelais et Parisiens qui viennent "
                "4 à 8 fois par an (week-ends, vacances scolaires, été). "
                "Ils deviennent des HABITUÉS réguliers du MAAT avec une carte et "
                "des goûts littéraires affirmés."
            ),
            'profil': [
                "CSP+ urbaine (Bordeaux, Paris) — niveau culturel élevé",
                "Revenus confortables (peuvent s'offrir une résidence secondaire sur le Bassin)",
                "Lecteurs assidus : littérature contemporaine, prix littéraires, essais",
                "Viennent en famille → demande jeunesse lors des vacances scolaires",
                "Habitués fidèles : ils reviennent, connaissent le fonds, font des demandes",
                "Sensibles à la qualité et au renouvellement du fonds",
                "Attente forte sur la rentrée littéraire, les prix Goncourt/Renaudot etc.",
            ],
        },
        'conclusion': (
            "⚠ NE PAS raisonner uniquement sur les 10 895 résidents permanents. "
            "Le public réel cumule : résidents permanents + COBAS (~68 000) + "
            "résidents secondaires habitués (Bordeaux/Paris) + touristes ponctuels. "
            "La fréquentation réelle (données en base) est le vrai signal."
        ),
    },

    # ─────────────────────────────────────────────────────────
    # PRINCIPE FONDAMENTAL : utiliser nos données, pas la démographie
    # ─────────────────────────────────────────────────────────
    'principe_analyse': (
        "Les données INSEE décrivent les RÉSIDENTS PERMANENTS d'Arcachon. "
        "Elles ne reflètent pas qui fréquente réellement le MAAT. "
        "Le vrai signal pour les acquisitions est dans NOTRE BASE : "
        "prêts réels par genre/catégorie, rotation, fréquentation journalière. "
        "La démographie est un contexte de fond, pas le signal principal."
    ),

    # Implications pour les acquisitions
    'implications_acquisitions': {
        'jeunesse': [
            "⚠ Seulement 720 enfants résidents permanents (6.6%) — MAIS...",
            "✓ Les grands-parents retraités (56.8%) emmènent leurs petits-enfants",
            "  au MAAT les week-ends, mercredis et vacances scolaires",
            "✓ La médiathèque est LA sortie famille quand les grands-parents",
            "  ne savent pas quoi faire faire aux petits-enfants",
            "→ La demande jeunesse est PLUS FORTE que le seul profil démographique",
            "  des résidents permanents ne le suggère",
            "Albums 0-6 ans : forte demande grands-parents + touristes été",
            "Romans 7-12 ans : public scolaire + mercredis + vacances",
            "BD jeunesse et manga : adolescents en visite chez grands-parents",
            "Documentaires nature/mer/animaux : thématiques locales très portantes",
            "Livres bilingues et imagiers : familles internationales en été",
        ],
        'adulte': [
            "Retraités = 56.8% de la population résidente → PRIORITÉ ABSOLUE",
            "Romans populaires, policiers, thrillers : demande très forte seniors",
            "Biographies et mémoires : public âgé avec temps libre et culture",
            "Grands caractères (Loupe, Libra Diffusio) : 30% ont 75 ans et +",
            "Documentaires mer, nature, patrimoine local : cohérent territoire",
            "Essais, histoire : CSP+ en hausse (cadres sup 7.3%, revenus médian 31 420€/an)",
            "BD adulte et romans graphiques : segment en croissance",
            "Romans graphiques / manga adulte : moins développé mais à considérer",
            "Livres pratiques (cuisine, jardin, santé) : population aisée installée",
        ],
        'saisonnier': {
            'ete': [
                "Pic ×5 de population (résidences secondaires 62.2%)",
                "Romans de plage et lectures légères pour touristes",
                "Guides touristiques Bassin d'Arcachon et Landes",
                "Livres jeunesse pour enfants de touristes (surtout 0-8 ans)",
                "Documentaires faune/flore marine et dune du Pilat",
            ],
            'automne_hiver': [
                "Rentrée littéraire septembre (prix Goncourt, Renaudot...)",
                "Romans du terroir et histoires régionales",
                "Documentaires et essais pour résidents seniors permanent",
                "Beaux livres et photographie (clientèle aisée)",
            ],
        },
        'alertes_specifiques': [
            "⚠ Population en déclin (-0.3%/an depuis 2016) et vieillissante",
            "⚠ Solde naturel très négatif : 37 naissances vs 285 décès en 2024",
            "⚠ Très peu de familles avec enfants : 516 couples avec enfants en 2022",
            "✓ Revenus médians élevés (31 420€/an) → qualité > quantité",
            "✓ Niveau d'études en hausse (39.1% diplômés supérieur) → littérature exigeante",
            "✓ 62.2% de résidences secondaires → fort potentiel touristique été",
        ]
    }
}


def obtenir_donnees_demographiques():
    """
    Retourne les données démographiques d'Arcachon.
    Priorité : données locales statiques (toujours disponibles).
    Complétées si possible par l'API geo.api.gouv.fr.
    """
    profil = PROFIL_ARCACHON.copy()

    # Tentative d'enrichissement via API
    try:
        r = requests.get(
            f"https://geo.api.gouv.fr/communes/{CODE_INSEE}"
            f"?fields=nom,code,codesPostaux,population,surface",
            headers=HEADERS, timeout=TIMEOUT
        )
        if r.status_code == 200:
            data = r.json()
            if 'population' in data:
                profil['population_permanente_api'] = data['population']
    except Exception:
        pass

    return profil


def resumer_demographie():
    """Résumé du profil démographique pour les recommandations d'acquisition."""
    p = PROFIL_ARCACHON
    ages = p['tranches_age_2022']
    lignes = [
        f"## PROFIL DÉMOGRAPHIQUE ARCACHON — Source : {p['source']}\n",
        f"Population 2022 : **{p['population_2022']:,}** résidents permanents",
        f"(pic estival estimé ~{p['population_estivale_pic']:,} en août — {p['pct_residences_secondaires']}% de résidences secondaires)",
        "",
        "**Pyramide des âges (INSEE RP2022) :**",
        f"- 0-14 ans : {ages['0-14 ans']['pct']}% ({ages['0-14 ans']['nb']} enfants) — TRÈS PEU",
        f"- 15-29 ans : {ages['15-29 ans']['pct']}%",
        f"- 30-44 ans : {ages['30-44 ans']['pct']}%",
        f"- 45-59 ans : {ages['45-59 ans']['pct']}%",
        f"- 60-74 ans : {ages['60-74 ans']['pct']}% ({ages['60-74 ans']['nb']} personnes)",
        f"- 75 ans+ : {ages['75 ans et +']['pct']}% ({ages['75 ans et +']['nb']} personnes)",
        f"→ **Seniors 60+ = {p['seniors_60_plus_pct']}% de la population** — dominance absolue",
        "",
        "**Structure socioprofessionnelle 2022 :**",
        f"- Retraités : **{p['csp_2022']['retraites']['pct']}%** ({p['csp_2022']['retraites']['nb']} personnes)",
        f"- Cadres/prof. sup. : {p['csp_2022']['cadres_sup']['pct']}% (en hausse)",
        f"- Employés : {p['csp_2022']['employes']['pct']}%",
        "",
        f"**Revenus :** niveau de vie médian {p['niveau_vie_median_2023']:,}€/an (2023)",
        f"— nettement au-dessus de la moyenne nationale (~23 000€)",
        f"**Diplômes :** {p['pct_diplome_superieur']}% avec diplôme supérieur (en forte hausse)",
        "",
        "**Alertes spécifiques :**",
    ]
    for alerte in p['implications_acquisitions']['alertes_specifiques']:
        lignes.append(f"- {alerte}")
    return "\n".join(lignes)


# ─────────────────────────────────────────────────────────────────────────────
# RAPPORT COMPLET
# ─────────────────────────────────────────────────────────────────────────────

def analyser_besoins(conn, avec_meteo=True):
    """
    Rapport complet d'analyse des besoins d'acquisition.
    Combine signaux internes, météo et démographie.
    """
    rapport = []

    # 1. Profil démographique
    rapport.append(resumer_demographie())
    rapport.append("\n---\n")

    # 2. Signaux internes
    signaux = analyser_signaux_internes(conn)
    rapport.append(resumer_signaux(signaux))
    rapport.append("\n---\n")

    # 3. Météo (optionnel)
    if avec_meteo:
        try:
            date_debut = '2022-01-01'
            date_fin = datetime.date.today().isoformat()
            meteo = obtenir_meteo_archive(date_debut, date_fin)
            if 'erreur' not in meteo:
                correlation = correlate_meteo_frequentation(conn, meteo)
                rapport.append(resumer_meteo(correlation))
            else:
                rapport.append(f"Météo non disponible : {meteo.get('erreur', '')}")
        except Exception as e:
            rapport.append(f"Météo : erreur ({e})")

    return "\n".join(rapport)


# ─────────────────────────────────────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import db
    conn = db.connect()
    print(analyser_besoins(conn, avec_meteo=True))
