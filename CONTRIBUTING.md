# Développement

Utiliser Python 3.12 et installer `requirements-dev.txt` dans un environnement virtuel. Garder les modules métier dans `radar/`, les adaptateurs Databricks dans `notebooks/`, les opérations Azure dans `scripts/` et leurs paramètres dans `infra/`.

Avant une modification, lire le README et le guide de la partie concernée. Ajouter des tests pour les changements de comportement, puis lancer :

```bash
python -m unittest discover -s tests -v
```

Les tests unitaires ne dépendent pas du cloud. Les tests sur archives et index réels sont ignorés si ces fichiers manquent. Ne pas modifier leurs valeurs attendues sans examiner la provenance et les révisions de sources.

Ne pas committer de données sources, secrets ou configurations personnelles. Documenter les limites et le niveau de validation : test simulé, exécution locale ou exécution réelle Azure. Une configuration de job ne prouve pas que ce job a été exécuté.
