# Déployer l'outil conversationnel — accessible de n'importe où

Maintenant que la base vit chez Turso, c'est plus simple qu'avant : **le
fichier `inventaire.db` n'a même plus besoin d'être envoyé sur GitHub.**
L'outil interroge directement la base en ligne, toujours à jour, sans
synchronisation manuelle.

## Ce dont tu as besoin une seule fois

1. **Une clé API Anthropic** : https://console.anthropic.com → "API Keys" → créer une clé (`sk-ant-...`). Quelques centimes par question posée.
2. **Un compte GitHub** (tu en as déjà un).
3. **Un compte Streamlit Community Cloud** (gratuit) : https://share.streamlit.io — connexion avec ton compte GitHub.
4. **Le jeton Turso en lecture seule** que tu as déjà généré (`TOKEN_LECTURE` lors de la création de la base) — pas le jeton complet, celui-là reste réservé à tes scripts locaux.

## Étape 1 — Mettre le code sur GitHub

Dans le dossier `inventaire_isbn`, seuls le code et les dépendances vont sur GitHub — **pas** `inventaire.db`, **pas** le fichier `.env` :

```bash
git init
echo ".env" > .gitignore
echo "inventaire.db" >> .gitignore
git add app_conversationnel.py requirements_app.txt db.py .gitignore
git commit -m "Outil conversationnel"
```

Crée un nouveau dépôt sur github.com (public ou privé, peu importe puisqu'aucune donnée sensible n'y est), puis :
```bash
git remote add origin https://github.com/TON-COMPTE/mediatheque-arcachon.git
git branch -M main
git push -u origin main
```

## Étape 2 — Déployer sur Streamlit Cloud

1. Sur https://share.streamlit.io, "New app"
2. Choisis ton dépôt, fichier principal `app_conversationnel.py`
3. Dans "Advanced settings" → "Secrets", colle (avec tes vraies valeurs) :
   ```
   ANTHROPIC_API_KEY = "sk-ant-ta-vraie-clé"
   TURSO_DATABASE_URL = "libsql://mediatheque-arcachon-thomaslafargue.aws-eu-west-1.turso.io"
   TURSO_AUTH_TOKEN = "le-jeton-EN-LECTURE-SEULE"
   ```
4. "Deploy"

Après une minute ou deux : une URL du type `https://mediatheque-arcachon.streamlit.app`, accessible depuis n'importe quel navigateur, téléphone compris.

## Mettre la base à jour — plus rien à faire ici

Tes scripts (`traiter_fichier.py`, `lancer_enrichissement.py`, `tache_de_fond.py`) écrivent déjà directement dans la base Turso, dès qu'un fichier `.env` est présent chez toi. L'outil en ligne lit cette même base — **toute mise à jour locale apparaît immédiatement dans l'outil en ligne**, sans action supplémentaire de ta part.

## Sécurité

- L'outil n'a accès qu'en **lecture** (jeton lecture seule + filtre SELECT-only vérifié dans le code) — aucune écriture possible, même en cas de problème.
- Connexion chiffrée (HTTPS) entre l'app et Turso.
- Mot de passe optionnel : ajoute `MOT_DE_PASSE = "ton-mot-de-passe"` dans les mêmes secrets Streamlit si tu veux restreindre l'accès à l'équipe.
- `.env` et `inventaire.db` ne quittent jamais ta machine (exclus du dépôt via `.gitignore`).
