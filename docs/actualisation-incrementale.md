# Actualisation incrémentale BAM et HCP

Le contrôleur `radar/refresh.py` consulte les deux ressources officielles configurées dans `config/ingestion.json`. Il télécharge leurs fichiers, compare le SHA-256, valide le format et les observations, puis prépare les versions nouvelles ou modifiées. Une réponse HTML, un format incompatible, un changement de licence ou des rejets bloquent la chaîne avant l'upload.

## Utilisation

Depuis le dossier du projet, dans PowerShell :

```powershell
# Consultation publique et archivage local, sans calcul Azure
./scripts/check-updates.ps1

# Transfert ADLS vérifié et soumission uniquement si une nouveauté attend
./scripts/check-updates.ps1 -Apply

# Rappeler cette commande pour consulter le statut du run déjà soumis
./scripts/check-updates.ps1 -Apply

# Après diagnostic d'un run en échec, autoriser une nouvelle tentative
./scripts/check-updates.ps1 -Apply -Retry
```

Le mode Apply utilise l'authentification Azure CLI existante, le workspace du projet et exclusivement l'abonnement déclaré dans `config/deployment.local.json`. Il ne modifie ni l'offre ni la limite de dépenses. Les notebooks et modules doivent déjà être importés dans `/Shared/radar-macro`, comme pour les exécutions précédemment validées.

## États et reprise

`data/refresh/state.json` conserve le dernier hash traité par source, le lot actif, son jeton, son run ID, ses sorties et l'historique. Conserver ce fichier : ne pas l'effacer pour résoudre un échec. La première initialisation démarre sans historique, sauf si `config/refresh-baseline.local.json` fournit une baseline déjà vérifiée sur le workspace cible. La référence publique `config/refresh-baseline.json` sert aux tests historiques et n'est pas appliquée automatiquement.

Les états sont : detected, archived, submitting, running, processed ou failed. Une archive présente n'est marquée traitée qu'après SUCCESS de toute la chaîne. Le transfert publie le manifeste en dernier et vérifie chaque fichier par retéléchargement. Une réponse perdue à la soumission réutilise le même jeton, enregistré avant l'appel réseau. Un run échoué exige `-Retry` ; aucun nouvel essai payant n'est lancé automatiquement.

Les tâches sont séquentielles : ingestion, analyse, assistant. Les deux dernières exigent la réussite de la tâche précédente. Le plafond global est de 30 minutes et chaque tâche conserve sa limite de 10 minutes. Ces limites ne constituent pas un plafond de facturation. Les identifiants et URI des nouveaux artefacts sont enregistrés dans `history[].outputs`. Les anciennes copies locales du rapport et de l'index ne sont pas remplacées automatiquement.

Le verrou `data/refresh/controller.lock` empêche deux contrôleurs locaux simultanés. Après un arrêt brutal, vérifier qu'aucun contrôleur ne tourne avant de supprimer uniquement ce fichier verrou. Le verrou n'empêche pas un utilisateur de lancer séparément une ingestion manuelle dans Azure. Utiliser un seul hôte de contrôle et éviter les lancements externes concurrents.

## Périmètre et limites

- La détection concerne le contenu des deux ressources configurées, pas tous les nouveaux jeux de données des sites BAM/HCP. Une ressource remplacée avec un nouvel identifiant demande une mise à jour contrôlée de la configuration.
- Les versions sont des snapshots complets ; les nouveaux fichiers doivent conserver le contrat des parseurs. Un retour à une archive plus ancienne est bloqué pour éviter une incohérence avec la sélection de la version courante dans Gold.
- Les PDF existants sont réindexés en fin de chaîne ; la découverte de nouveaux PDF n'est pas ajoutée ici.
- Les tests de l'assistant contiennent des valeurs de référence historiques. Une correction de ces valeurs peut faire échouer la tâche assistant et exiger une revue du jeu d'évaluation, sans accepter automatiquement le changement.
- Les notebooks existants restent limités en volume. La détection locale ne garantit pas le succès de tous leurs contrôles analytiques.
- L'état est local, sans verrou distribué ni transaction globale sur les tables. Une tâche aval en échec peut laisser les tables en amont actualisées ; le run reste en échec et la reprise est explicite.

## Planification

Aucune tâche planifiée n'est activée par cette livraison. La commande est prête pour un déclencheur périodique, mais la cadence et l'hôte doivent être choisis après validation du premier lot réellement nouveau. Sur un PC, la disponibilité et la session Azure CLI doivent être assurées ; pour un service hébergé, il faut une identité non interactive et un stockage durable de l'état. Ne pas planifier une relance aveugle des notebooks : planifier le contrôleur, qui évite le calcul lorsqu'il n'y a aucun changement.

Documentation de l'API de soumission et du jeton d'idempotence : https://docs.databricks.com/api/jobs/v2/submit-run
