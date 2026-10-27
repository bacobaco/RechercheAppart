# 🏢 RechercheBiens - Veille Immobilière & Stationnements (Lyon)

🌐 **Tableau de bord accessible en ligne** : **[https://bacobaco.github.io/RechercheAppart/](https://bacobaco.github.io/RechercheAppart/)**  
*(Note : l'URL GitHub Pages conserve le nom de dépôt `RechercheAppart` tant que le repo GitHub distant n'est pas renommé).*

---

## 📌 Présentation du Projet

**RechercheBiens** est une plateforme autonome de veille immobilière et de stationnements. Actuellement configurée pour la recherche d'emplacements de stationnement, garages et box fermés adaptés pour **Tesla (Model 3 / Y)** autour du **56 avenue Félix Faure, 69003 Lyon** via un système modulaire défini dans `searches.json` :
1. **Recherche Achat Parking** (`achat_parking_felix_faure`) : Achat de garage, box fermé ou place de stationnement (budget **20 000 € à 35 000 €**).
2. **Recherche Location Parking** (`parking_felix_faure`) : Location de parking, box ou garage fermé (budget **< 150 €/mois**).

---

## 🎯 Profils de Recherche et Critères

### 1. 🏢 Achat Parking Tesla (`achat_parking_felix_faure`)
- **Cible** : 56 avenue Félix Faure, 69003 Lyon (GPS: 45.7528, 4.8531).
- **Type** : Achat de garage, box fermé ou place en sous-sol.
- **Périmètre** : Rayon piéton strict (~300m) calculé via OpenStreetMap OSRM.
- **Véhicule** : Tesla Model 3 / Y (box fermé et prises de recharge priorisés, vérification du poids/monte-charge).
- **Budget** : Entre 20 000 € et 35 000 €.
- **Sources** : Bien'ici (filtre `buy`), SeLoger (via Jinka + direct), Gens de Confiance (catégorie `realestate__sale`).
- **Données** : `data_achat_parking_felix_faure.json`.

### 2. 🚗 Location Parking Tesla (`parking_felix_faure`)
- **Cible** : 56 avenue Félix Faure, 69003 Lyon (GPS: 45.7528, 4.8531).
- **Type** : Location de parking / box fermé privatif / garage en sous-sol.
- **Périmètre** : Rayon piéton strict (~300m) calculé via OpenStreetMap OSRM.
- **Véhicule** : Tesla Model 3 / Y (exclusion automatique des emplacements moto/2-roues < 8m²).
- **Budget** : Maximum 150 € / mois.
- **Sources** : Bien'ici, SeLoger (via Jinka + direct), Gens de Confiance.
- **Données** : `data_parking_felix_faure.json`.

---

## 🚀 Fonctionnalités Principales

1. **Multi-sources de scraping résilient** :
   - **Gens de Confiance** : Isolation stricte des annonces parking (vente et location) via `curl_cffi` (impersonation TLS Chrome) et auto-renouvellement des cookies de session.
   - **Bien'ici API** : Interrogation directe pour achat (`filterType: buy`) et location (`filterType: rent`) avec géocodage précis.
   - **Jinka API** : Agrégation des alertes et annonces SeLoger, LeBonCoin et ParuVendu avec token JWT auto-géré.
   - **SeLoger** : Détection des annonces directes et relai Jinka.
2. **Filtrage et Scoring Intelligent** :
   - **Itinéraire Piéton Réel** : Distance et temps de marche calculés avec OpenStreetMap OSRM (itinéraires réels à pied).
   - **Compatibilité Tesla** : Détection automatique des box fermés, accès sécurisés (bip/badge), prises électriques/recharge et alertes sur les monte-charges limités en tonnage.
   - **Exclusion 2-roues** : Élimination automatique des emplacements moto/scooter < 8m².
3. **Tableau de Bord Interactif (`dashboard.html` / `index.html`)** :
   - Visualisation avec photos, prix, distance piétonne, temps de marche, itinéraire Google Maps.
   - Switcher d'onglets instantané entre profil Achat et Location.
   - Filtres dynamiques par statut : *Nouveau*, *Retenu*, *À visiter*, *Visité*, *Éliminer*.
   - Modal de réglage des critères en direct (ajustement du rayon et des budgets min/max).

---

## 📂 Structure du Répertoire

```text
├── agent.py                            # Script principal de scraping, filtrage et orchestration
├── server.py                           # Serveur HTTP local (API REST et service des fichiers statiques)
├── dashboard.html                      # Interface web du tableau de bord
├── index.html                          # Version miroir pour GitHub Pages
├── searches.json                       # Configuration des profils de recherche (Achat / Location)
├── data_achat_parking_felix_faure.json # Base de données des annonces d'achat
├── data_parking_felix_faure.json       # Base de données des annonces de location
├── login_gdc.py                        # Assistant de connexion GDC (test live, diagnostic)
├── login_jinka.py                      # Assistant d'authentification Jinka (profil persistant, capture token)
├── .gitignore                          # Exclusion des tokens de session, logs et fichiers temporaires
└── README.md                           # Documentation du projet
```

---

## 🛠️ Installation & Démarrage

### 1. Prérequis
- **Python 3.10+**
- Navigateur Google Chrome (recommandé pour Playwright)

### 2. Dépendances
```bash
pip install requests playwright curl_cffi beautifulsoup4 pyperclip
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
# Lancer toutes les recherches actives
python agent.py

# Lancer uniquement la recherche Achat Parking (Félix Faure)
python agent.py --search achat_parking_felix_faure

# Lancer uniquement la recherche Location Parking (Félix Faure)
python agent.py --search parking_felix_faure

# Lister les profils configurés
python agent.py --list
```

### 5. Gérer les connexions et statuts anti-bot
Les sessions sont gérées de façon autonome :
- **Gens de Confiance** :
  - Contournement Cloudflare transparent via `curl_cffi` (impersonation TLS Chrome 120).
  - Renouvellement automatique continu des cookies de session (`__cf_bm`).
  - Vérifier l'état de la session : `python login_gdc.py --status`
- **Jinka** :
  - Vérification préventive de la validité du token JWT avec auto-récupération sur 401.
  - Vérifier l'état du token : `python login_jinka.py --status`
  - Renouveler le token : `python login_jinka.py`

---

## 📋 Historique des Versions

- **v2.1.0** *(2026-10-27)* :
  - **Renommage du projet** : Nouveau nom **RechercheBiens** pour refléter la flexibilité multi-recherches (Achat, Location, Stationnements).
  - **Nettoyage complet** : Suppression des fichiers de travail obsolètes (`data.json`, `prompt agent`, `download_photos.py`, `temp_photos/`).
  - **Achat Stationnement** : Création et liaison directe de l'alerte Jinka correspondante (`Achat Parking Lyon Félix Faure`).
  - **Amélioration UI** : Onglets dynamiques, synchronisation automatique GitHub et parité stricte `dashboard.html` / `index.html`.
- **v2.0.0** *(2026-10-27)* :
  - Architecture multi-recherches (`searches.json`) avec support des stationnements Tesla (Félix Faure).
  - Intégration du routage piéton OpenStreetMap OSRM et détection de compatibilité Tesla.
- **v1.5.0** *(2026-09-14)* :
  - Automatisation anti-bot Gens de Confiance via `curl_cffi` et fiabilisation Jinka.
- **v1.4.0** *(2026-09-09)* :
  - Déploiement du tableau de bord sur GitHub Pages.

