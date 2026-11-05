# Publier le dépôt sur GitHub

Le dépôt utilise la branche `main`. Le premier historique a été organisé en quinze commits thématiques ; voir [la note sur les dates](history.md). Les commandes suivantes servent de référence pour publier une copie indépendante.

## Vérifications avant commit

```powershell
git status --short
git add --dry-run .
python -m unittest discover -s tests -v
```

Les données, PDF sources, index SQLite, sorties de runs, paramètres locaux et journaux privés doivent rester ignorés. Ne pas utiliser `git add -f` pour contourner ces exclusions. Les fichiers d'exemple ne doivent contenir aucun jeton ni mot de passe.

## Premier commit et push

Créer sur GitHub un dépôt vide, par exemple `radar-macro-financier`, sans README supplémentaire. Puis remplacer l'URL ci-dessous par celle de votre dépôt :

```powershell
git add .
git diff --cached --stat
git diff --cached
git commit -m "Initial commit: macro financial lakehouse portfolio"
git remote add origin https://github.com/VOTRE_COMPTE/radar-macro-financier.git
git push -u origin main
```

Configurer votre identité Git si Git la demande. L'authentification GitHub reste gérée par votre environnement ; ne jamais ajouter de token dans l'URL du remote ou un fichier du projet.

La CI effectue des tests locaux sans accès Azure. Choisir une licence avant d'autoriser explicitement la réutilisation du code ; les droits des données sources restent distincts.
