# 🏠 RechercheAppart - Lyon (v1.4.0)

Agent intelligent et automatisé de recherche, filtrage et suivi d'annonces de location d'appartements meublés haut standing à Lyon.

🌐 **Tableau de bord accessible en ligne** : **[https://bacobaco.github.io/RechercheAppart/](https://bacobaco.github.io/RechercheAppart/)**

---

## 📌 Présentation du Projet

Ce projet a été conçu pour automatiser et centraliser la veille immobilière locative à Lyon selon un cahier des charges strict. Il agrège plusieurs sources d'annonces, applique des filtres algorithmiques avancés (géolocalisation, équipements, mots-clés) et fournit un tableau de bord web interactif pour gérer vos visites et vos choix.

---

## 🎯 Critères de Recherche

- **Type de bien** : Appartement **Meublé** de haut standing.
- **Secteurs géographiques** :
  - **Lyon 2e** (Presqu'île, Bellecour, Ainay, Cordeliers, Confluence récente).
  - **Lyon 6e** (Foch, Brotteaux, Masséna, Parc de la Tête d'Or).
  - **Lyon 3e** (Préfecture, Quais du Rhône - secteurs calmes).
  - **Lyon 1er** (Pentes / Terreaux - secteurs calmes).
  - **Lyon 5e** (**Vieux Lyon UNIQUEMENT** : Saint-Jean, Saint-Paul, Saint-Georges).
- **Surface** : $\ge 70\text{ m}^2$ (Idéal 100 à 150 m²).
- **Configuration** : 3 à 4 pièces (Minimum 2 chambres).
- **Équipements requis** :
  - **Ascenseur obligatoire** (sauf RDC).
  - **Climatisation obligatoire** (ou à défaut **balcon / terrasse** permettant l'installation d'une clim d'appoint).
- **Exclusions strictes** : Duplex strictement exclus, rues bruyantes / fêtardes.
- **Temps de trajet** : Accès métro/tram rapide vers Lyon Gerland (Framatome).

---

## 🚀 Fonctionnalités Principales

1. **Multi-sources de scraping** :
   - **Jinka API** : Récupération des alertes agrégées avec gestion des tokens.
   - **Gens de Confiance** : Scraping avec support de session Playwright & contournement Cloudflare.
   - **Urban Séjour & Agences locales** : Scraping dédié aux spécialistes de la location meublée lyonnaise.
2. **Filtrage et Scoring Intelligent** :
   - Détection automatique des doublons inter-plateformes.
   - Analyse sémantique des descriptions (détection d'ascenseur, climatisation, balcon, étage élevé, cachet, parking).
   - Calcul automatique du loyer au m² ($€/\text{m}^2$).
   - Purge automatique des annonces marquées *"Éliminer"* ou *"Déjà loué"* après 30 jours.
3. **Tableau de Bord Interactif (`dashboard.html`)** :
   - Visualisation claire des biens avec photos, prix, surface, étage, avantages/inconvénients.
   - Filtres dynamiques par statut : *À traiter*, *Retenu*, *À visiter*, *Visité*, *Éliminer*, *Déjà loué*.
   - Gestion des notes et suivi de l'avancement.
   - Bouton de déclenchement du scan en direct depuis le navigateur.

---

## 📂 Structure du Répertoire

```text
├── agent.py          # Script principal de scraping, filtrage et mise à jour de data.json
├── server.py         # Serveur HTTP local (API REST et service des fichiers statiques)
├── dashboard.html    # Interface web du tableau de bord
├── data.json         # Base de données locale des annonces et statuts
├── login_gdc.py      # Assistant de connexion pour Gens de Confiance (Playwright / Cookies)
├── login_jinka.py    # Assistant d'authentification pour Jinka
├── prompt agent      # Spécifications détaillées des critères et consignes pour l'agent
├── .gitignore        # Exclusion des tokens de session, logs et fichiers temporaires
└── README.md         # Documentation et version du projet
```

---

## 🛠️ Installation & Démarrage

### 1. Prérequis
- **Python 3.10+**
- Navigateur Google Chrome (recommandé pour Playwright)

### 2. Dépendances
```bash
pip install requests playwright
playwright install chromium
```

### 3. Lancer le Serveur et le Dashboard
Démarrez le serveur local :
```bash
python server.py
```
Ouvrez ensuite votre navigateur à l'adresse suivante :
👉 **`http://localhost:8000/dashboard.html`**

### 4. Lancer manuellement un Scan
```bash
python agent.py
```

### 5. Gérer les connexions (si nécessaire)
- Pour Gens de Confiance : `python login_gdc.py`
- Pour Jinka : `python login_jinka.py`

---

## 📋 Historique des Versions

- **v1.4.0** *(2026-09-09)* :
  - Déploiement du tableau de bord sur GitHub Pages pour consultation en ligne permanente.
  - Compatibilité du dashboard en mode statique (chargement direct de `data.json`, persistance locale via `localStorage`).
  - Ajout d'indicateurs de statut (en ligne vs serveur local) et bouton d'actualisation rapide.
- **v1.3.0** *(2026-08-30)* :
  - Intégration du secteur Lyon 5e (Vieux Lyon exclusivement).
  - Assouplissement du critère climatisation (acceptation des balcons/terrasses pour climatisation d'appoint).
  - Système de purge automatique des annonces archivées après 30 jours.
  - Synchronisation et sauvegarde de `data.json` sur GitHub.
- **v1.2.0** :
  - Intégration du scraper Gens de Confiance avec gestion des sessions anti-bot.
  - Ajout du scraper Urban Séjour.
- **v1.1.0** :
  - Refonte du tableau de bord interactif avec filtres et statut temps réel.
- **v1.0.0** :
  - Version initiale : Scraper Jinka, calcul du prix/m², filtrage selon cahier des charges.
