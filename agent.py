import os
import json
import math
import re
import requests
import urllib.parse
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

DATA_FILE = "data.json"
JINKA_SESSION_FILE = "jinka_session.json"
JINKA_TOKEN_FILE = "jinka_token.json"

# List of Metro and Tram stations in central Lyon (1er, 2e, 3e, 6e)
METRO_TRAM_STATIONS = [
    # Metro A
    {"name": "Perrache", "lat": 45.7486, "lon": 4.8258},
    {"name": "Ampère - Victor Hugo", "lat": 45.7531, "lon": 4.8294},
    {"name": "Bellecour", "lat": 45.7578, "lon": 4.8322},
    {"name": "Cordeliers", "lat": 45.7642, "lon": 4.8358},
    {"name": "Hôtel de Ville - Louis Pradel", "lat": 45.7675, "lon": 4.8356},
    {"name": "Foch", "lat": 45.7694, "lon": 4.8433},
    {"name": "Masséna", "lat": 45.7725, "lon": 4.8475},
    {"name": "Charpennes", "lat": 45.7736, "lon": 4.8631},
    # Metro B
    {"name": "Brotteaux", "lat": 45.7675, "lon": 4.8597},
    {"name": "Gare Part-Dieu - Vivier Merle", "lat": 45.7606, "lon": 4.8597},
    {"name": "Place Guichard - Bourse du Travail", "lat": 45.7597, "lon": 4.8486},
    {"name": "Saxe - Gambetta", "lat": 45.7533, "lon": 4.8483},
    {"name": "Jean Macé", "lat": 45.7478, "lon": 4.8428},
    {"name": "Place Jean Jaurès", "lat": 45.7417, "lon": 4.8361},
    {"name": "Debourg", "lat": 45.7314, "lon": 4.8353},
    {"name": "Stade de Gerland", "lat": 45.7264, "lon": 4.8344},
    # Metro C
    {"name": "Croix-Paquet", "lat": 45.7699, "lon": 4.8368},
    {"name": "Croix-Rousse", "lat": 45.7744, "lon": 4.8317},
    # Metro D
    {"name": "Vieux Lyon", "lat": 45.7622, "lon": 4.8272},
    {"name": "Guillotière - Gabriel Péri", "lat": 45.7575, "lon": 4.8428},
    {"name": "Garibaldi", "lat": 45.7514, "lon": 4.8547},
    {"name": "Sans Souci", "lat": 45.7483, "lon": 4.8617},
    # Tram T1 (central stations not covered by Metro)
    {"name": "Liberté", "lat": 45.7578, "lon": 4.8425},
    {"name": "Lafayette - Préfecture", "lat": 45.7619, "lon": 4.8436},
    {"name": "Palais de Justice - Mairie du 3ème", "lat": 45.7600, "lon": 4.8481},
    {"name": "Saint-André", "lat": 45.7553, "lon": 4.8392},
    {"name": "Rue de l'Université", "lat": 45.7525, "lon": 4.8364},
    {"name": "Quai Claude Bernard", "lat": 45.7503, "lon": 4.8361},
    # Tram T2 (central stations)
    {"name": "Centre Berthelot", "lat": 45.7478, "lon": 4.8358}
]

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance between two points in meters."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371000 # Radius of earth in meters
    return c * r

def estimate_travel_time(station_name, walk_to_station_meters):
    """Estimate travel time to Framatome Gerland (Debourg / Stade de Gerland)."""
    walk_time = int(walk_to_station_meters / 80) # 80 m/min average speed
    
    transit_times = {
        # Metro B (direct to Debourg)
        "Debourg": 0,
        "Stade de Gerland": 2,
        "Place Jean Jaurès": 2,
        "Jean Macé": 6,
        "Saxe - Gambetta": 8,
        "Place Guichard - Bourse du Travail": 10,
        "Gare Part-Dieu - Vivier Merle": 14,
        "Brotteaux": 16,
        "Charpennes": 18,
        
        # Metro A (transfer to B at Charpennes or via Bellecour/D/Saxe)
        "Masséna": 22,
        "Foch": 24,
        "Hôtel de Ville - Louis Pradel": 26,
        "Cordeliers": 28,
        "Bellecour": 12, # Bellecour -> Saxe (Metro D) -> Debourg (Metro B)
        "Ampère - Victor Hugo": 16,
        "Perrache": 18,
        
        # Metro D (transfer to B at Saxe-Gambetta)
        "Guillotière - Gabriel Péri": 14,
        "Vieux Lyon": 24,
        "Garibaldi": 14,
        "Sans Souci": 18,
        
        # Metro C (transfer to A then B)
        "Croix-Paquet": 32,
        "Croix-Rousse": 35,
        
        # Tram T1 (direct to Debourg)
        "Liberté": 15,
        "Lafayette - Préfecture": 18,
        "Palais de Justice - Mairie du 3ème": 16,
        "Saint-André": 12,
        "Rue de l'Université": 10,
        "Quai Claude Bernard": 8,
        
        # Tram T2 (transfer to B at Jean Macé)
        "Centre Berthelot": 12
    }
    
    transit_time = transit_times.get(station_name, 25)
    walk_to_work = 5 # minutes from Debourg station to Framatome
    
    return walk_time + transit_time + walk_to_work

def is_text_furnished(text):
    """Detect if text indicates a furnished apartment, excluding 'non-meublé'/'non meublé'."""
    text_lower = text.lower()
    # Remove negation patterns first
    cleaned = re.sub(r'non[- ]?meublée?', '', text_lower)
    cleaned = re.sub(r'vide\s*/\s*non\s*meublée?', '', cleaned)
    # Now check for remaining 'meublé' occurrences
    return bool(re.search(r'\bmeublée?\b', cleaned))

def extract_address(description, postal_code):
    """Look for street address in description and format it."""
    pattern = r'(?:\b(\d+)\s*(?:bis|ter)?\s+)?\b(rue|avenue|boulevard|place|quai|cours|allée|chemin|passage|route|r\.|av\.|bd\.|pl\.|q\.|crs)\s+([A-Za-zÀ-ÿ0-9\s\'-]+?)(?=\b(?:est|ouest|nord|sud|lyon|dans|avec|au|en|proche|métro|tram|gare|comportant|comprenant|\.|\,|;|\n|\t))'
    
    match = re.search(pattern, description, re.IGNORECASE)
    if match:
        number = match.group(1) or ""
        street_type = match.group(2)
        street_name = match.group(3).strip()
        
        words = street_name.split()
        cleaned_words = []
        for word in words:
            if word.lower() in ["dans", "avec", "situé", "au", "en", "proche", "métro", "tram", "lyon"]:
                break
            cleaned_words.append(word)
        street_name = " ".join(cleaned_words)
        
        full_address = f"{number} {street_type} {street_name}".strip()
        if street_type and len(street_name) > 2:
            return f"{full_address}, {postal_code} Lyon"
    return None

def get_district_coordinates(text):
    """Fallback coordinates based on Lyon districts/arrondissement names."""
    text_lower = text.lower()
    if "ainay" in text_lower:
        return 45.7531, 4.8294 # Ampère
    elif "bellecour" in text_lower:
        return 45.7578, 4.8322 # Bellecour
    elif "cordeliers" in text_lower:
        return 45.7642, 4.8358 # Cordeliers
    elif "jacobins" in text_lower:
        return 45.7578, 4.8322 # Bellecour/Jacobins
    elif "foch" in text_lower:
        return 45.7694, 4.8433 # Foch
    elif "tête d'or" in text_lower or "tete d'or" in text_lower or "masséna" in text_lower or "massena" in text_lower:
        return 45.7725, 4.8475 # Masséna
    elif "brotteaux" in text_lower:
        return 45.7675, 4.8597 # Brotteaux
    elif "terreaux" in text_lower or "pentes" in text_lower or "croix-paquet" in text_lower:
        return 45.7675, 4.8356 # Hôtel de Ville
    elif "préfecture" in text_lower or "prefecture" in text_lower or "quais du rhône" in text_lower or "quais du rhone" in text_lower:
        return 45.7619, 4.8436 # Lafayette - Préfecture
    elif "lyon 2" in text_lower or "69002" in text_lower or "lyon 2e" in text_lower:
        return 45.7578, 4.8322 # Bellecour
    elif "lyon 6" in text_lower or "69006" in text_lower or "lyon 6e" in text_lower:
        return 45.7694, 4.8433 # Foch
    elif "lyon 1" in text_lower or "69001" in text_lower or "lyon 1er" in text_lower:
        return 45.7675, 4.8356 # Hôtel de Ville
    elif "lyon 3" in text_lower or "69003" in text_lower or "lyon 3e" in text_lower:
        return 45.7597, 4.8486 # Place Guichard
    return 45.7578, 4.8322 # Default Bellecour

def parse_barnes_page(html_text, url):
    """Helper to extract details from Barnes Lyon property details page."""
    lines = [line.strip() for line in html_text.split('\n') if line.strip()]
    
    price = None
    surface = None
    rooms = None
    bedrooms = None
    floor = None
    description = ""
    
    for i, line in enumerate(lines):
        if line == "SURFACE" and i + 1 < len(lines):
            m = re.search(r'([\d,.]+)', lines[i+1])
            if m:
                surface = float(m.group(1).replace(",", "."))
        elif line == "LOYER" and i + 1 < len(lines):
            val = lines[i+1]
            price_digits = "".join(c for c in val if c.isdigit())
            if price_digits:
                price = float(price_digits)
        elif line == "PIÈCES" and i + 1 < len(lines):
            m = re.search(r'(\d+)', lines[i+1])
            if m:
                rooms = int(m.group(1))
        elif line == "CHAMBRES" and i + 1 < len(lines):
            m = re.search(r'(\d+)', lines[i+1])
            if m:
                bedrooms = int(m.group(1))
        elif line == "ÉTAGE" and i + 1 < len(lines):
            floor_str = lines[i+1].lower()
            if "rdc" in floor_str or "rez" in floor_str:
                floor = 0
            else:
                m = re.search(r'(\d+)', floor_str)
                if m:
                    floor = int(m.group(1))
                    
    description_lines = []
    found_desc = False
    for line in lines:
        if "exclusivité" in line.lower() or "situé au" in line.lower() or "dans un immeuble" in line.lower():
            description_lines.append(line)
            found_desc = True
        elif found_desc and len(description_lines) < 5:
            if len(line) > 30 and not any(kw in line.upper() for kw in ["LOYER", "SURFACE", "HONORAIRES", "DPE", "GES", "CONTACT"]):
                description_lines.append(line)
                
    description = "\n".join(description_lines)
    
    if not surface:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', description, re.IGNORECASE)
        if m:
            surface = float(m.group(1).replace(",", "."))
    if not rooms:
        m = re.search(r'(\d+)\s*(?:pièces|pieces)', description, re.IGNORECASE)
        if m:
            rooms = int(m.group(1))
    if not bedrooms:
        m = re.search(r'(\d+)\s*(?:chambres|chambre)', description, re.IGNORECASE)
        if m:
            bedrooms = int(m.group(1))
            
    return {
        "price": price,
        "surface": surface,
        "rooms": rooms,
        "bedrooms": bedrooms,
        "floor": floor,
        "description": description
    }

def scrape_bienici():
    print("[INFO] Interrogation du site Bien'ici...")
    url = "https://www.bienici.com/realEstateAds.json"
    filters = {
      "size": 50,
      "from": 0,
      "filterType": "rent",
      "propertyType": ["flat"],
      "minPrice": 1500,
      "maxPrice": 2500,
      "minRooms": 3,
      "maxRooms": 4,
      "minArea": 75,
      "page": 1,
      "sortBy": "publicationDate",
      "sortOrder": "desc",
      "onTheMarket": [True],
      "furnished": [True],
      "zoneIdsByTypes": {
        "zoneIds": ["-10680", "-10679", "-10690", "-120967"] # Lyon 2, 1, 6, 3
      }
    }
    
    params = {
        "filters": json.dumps(filters),
        "extensionType": "extendedIfNoResult"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"[ERREUR] Code d'erreur Bien'ici: {response.status_code}")
            return []
        data = response.json()
        ads = data.get("realEstateAds", [])
        for ad in ads:
            ad["source"] = "Bien'ici"
            ad_id = ad.get("id")
            ad["url"] = f"https://www.bienici.com/annonce/{ad_id}"
        return ads
    except Exception as e:
        print(f"[ERREUR] Échec de la requête vers Bien'ici: {e}")
        return []

def scrape_barnes():
    print("[INFO] Interrogation du site Barnes Lyon...")
    url = "https://www.barnes-lyon.com/location-immobilier-prestige/lyon"
    ads = []
    
    if not sync_playwright:
        print("[ERREUR] Playwright n'est pas disponible pour Barnes.")
        return []
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            links = page.locator("a").all()
            listing_urls = []
            for link in links:
                href = link.get_attribute("href")
                if href and "/location-immobilier-prestige/" in href and href != "/location-immobilier-prestige/lyon" and "page=" not in href:
                    listing_urls.append("https://www.barnes-lyon.com" + href)
                    
            listing_urls = sorted(list(set(listing_urls)))
            print(f"[INFO] {len(listing_urls)} annonces trouvées sur Barnes Lyon. Récupération des détails...")
            
            for ad_url in listing_urls[:10]:
                try:
                    page.goto(ad_url, wait_until="networkidle", timeout=20000)
                    body_text = page.locator("body").inner_text()
                    title = page.locator("h1").inner_text()
                    
                    parsed = parse_barnes_page(body_text, ad_url)
                    parsed["title"] = title
                    
                    postal_code_match = re.search(r'6900\d', ad_url + " " + title + " " + parsed["description"])
                    postal_code = postal_code_match.group(0) if postal_code_match else "69002"
                    
                    lat, lon = get_district_coordinates(title + " " + parsed["description"])
                    
                    ad_item = {
                        "source": "Barnes Lyon",
                        "id": f"barnes_{ad_url.split('-')[-1]}",
                        "url": ad_url,
                        "title": title,
                        "description": parsed["description"],
                        "price": parsed["price"],
                        "surfaceArea": parsed["surface"],
                        "postalCode": postal_code,
                        "city": "Lyon",
                        "district": {"libelle": f"Lyon {postal_code[-1]}e"},
                        "roomsQuantity": parsed["rooms"],
                        "bedroomsQuantity": parsed["bedrooms"],
                        "isFurnished": is_text_furnished(title + " " + parsed["description"]),
                        "publicationDate": datetime.now().strftime("%Y-%m-%d"),
                        "hasElevator": "sans ascenseur" not in parsed["description"].lower() and ("ascenseur" in parsed["description"].lower() or "ascenseur" in title.lower()),
                        "floor": parsed["floor"],
                        "isGroundFloor": parsed["floor"] == 0 or "rdc" in parsed["description"].lower() or "rez-de-chaussée" in parsed["description"].lower(),
                        "blurInfo": {
                            "position": {
                                "lat": lat,
                                "lon": lon
                            }
                        },
                        "hasBalcony": "balcon" in parsed["description"].lower() or "terrasse" in parsed["description"].lower(),
                        "hasTerrace": "terrasse" in parsed["description"].lower()
                    }
                    ads.append(ad_item)
                except Exception as ex:
                    print(f"[ERREUR] Échec du scraping de {ad_url}: {ex}")
            browser.close()
    except Exception as e:
        print(f"[ERREUR] Échec de la récupération sur Barnes Lyon: {e}")
        
    return ads

def scrape_leboncoin():
    print("[INFO] Interrogation du site LeBonCoin...")
    url = "https://www.leboncoin.fr/recherche?category=10&locations=Lyon_69001__45.76795_4.83438_3586,Lyon_69002__45.75365_4.82888_3765,Lyon_69003__45.75639_4.85558_7254,Lyon_69006__45.7716_4.85352_3618&real_estate_type=2&price=1500-2500&square=75-max&rooms=3-4&furnished=1&sort=time&order=desc"
    ads = []
    
    if not sync_playwright:
        print("[ERREUR] Playwright n'est pas disponible pour LeBonCoin.")
        return []
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            
            # Accept cookies if present
            try:
                cookie_btn = page.locator("button#didomi-notice-agree-button, button:has-text('Accepter'), button:has-text('Tout accepter')")
                if cookie_btn.count() > 0:
                    cookie_btn.first.click()
                    page.wait_for_timeout(2000)
            except:
                pass
            
            # LeBonCoin listing cards
            cards = page.locator("a[data-test-id='ad'], a[href*='/ad/'], article a").all()
            print(f"[INFO] {len(cards)} annonces trouvées sur LeBonCoin.")
            
            for card in cards[:15]:
                try:
                    href = card.get_attribute("href")
                    if not href or "/ad/" not in href:
                        continue
                    
                    text = card.inner_text()
                    ad_url = href if href.startswith("http") else f"https://www.leboncoin.fr{href}"
                    
                    # Extract postal code
                    postal_code = "69002"
                    for pc in ["69001", "69002", "69003", "69006"]:
                        if pc in text:
                            postal_code = pc
                            break
                    for dist in ["Lyon 1e", "Lyon 2e", "Lyon 3e", "Lyon 6e", "Lyon 1er"]:
                        if dist in text:
                            if "1" in dist: postal_code = "69001"
                            elif "2" in dist: postal_code = "69002"
                            elif "3" in dist: postal_code = "69003"
                            elif "6" in dist: postal_code = "69006"
                            break
                    
                    # Parse price
                    price = None
                    price_match = re.search(r'([\d\s]+)\s*€', text)
                    if price_match:
                        price_digits = "".join(c for c in price_match.group(1) if c.isdigit())
                        if price_digits:
                            price = float(price_digits)
                    
                    # Parse surface
                    surface = None
                    m = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', text, re.IGNORECASE)
                    if m:
                        surface = float(m.group(1).replace(",", "."))
                    
                    # Parse rooms
                    rooms = None
                    m = re.search(r'(\d+)\s*(?:pièces|p\.)', text, re.IGNORECASE)
                    if m:
                        rooms = int(m.group(1))
                    
                    # Title extraction (first line usually)
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    title = lines[0] if lines else "Appartement"
                    
                    lat, lon = get_district_coordinates(text + " " + postal_code)
                    
                    ad_item = {
                        "source": "LeBonCoin",
                        "id": f"lbc_{ad_url.split('/')[-1]}",
                        "url": ad_url,
                        "title": title,
                        "description": text,
                        "price": price,
                        "surfaceArea": surface,
                        "postalCode": postal_code,
                        "city": "Lyon",
                        "district": {"libelle": f"Lyon {postal_code[-1]}e"},
                        "roomsQuantity": rooms,
                        "bedroomsQuantity": None,
                        "isFurnished": is_text_furnished(text),
                        "publicationDate": datetime.now().strftime("%Y-%m-%d"),
                        "hasElevator": "ascenseur" in text.lower() and "sans ascenseur" not in text.lower(),
                        "floor": None,
                        "isGroundFloor": "rez-de-chaussée" in text.lower() or "rdc" in text.lower(),
                        "blurInfo": {
                            "position": {
                                "lat": lat,
                                "lon": lon
                            }
                        },
                        "hasBalcony": "balcon" in text.lower(),
                        "hasTerrace": "terrasse" in text.lower()
                    }
                    ads.append(ad_item)
                except Exception as ex:
                    print(f"[ERREUR] Échec du parsing d'une carte LeBonCoin: {ex}")
            browser.close()
    except Exception as e:
        print(f"[ERREUR] Échec de la récupération sur LeBonCoin: {e}")
        
    return ads

def scrape_jinka():
    """Récupère les annonces depuis Jinka via leur API privée.
    Nécessite d'avoir lancé login_jinka.py au moins une fois.
    Jinka agrège SeLoger, LeBonCoin, PAP, etc."""
    print("[INFO] Interrogation de Jinka (agrégateur SeLoger/LBC/PAP)...")
    ads = []
    
    # 1. Récupérer le token d'authentification
    token = None
    
    # Méthode A : depuis le fichier token sauvegardé par login_jinka.py
    if os.path.exists(JINKA_TOKEN_FILE):
        try:
            with open(JINKA_TOKEN_FILE, "r", encoding="utf-8") as f:
                token_data = json.load(f)
                token = token_data.get("token")
                if token:
                    print("[INFO] Token Jinka chargé depuis jinka_token.json")
        except Exception as e:
            print(f"[WARN] Impossible de lire {JINKA_TOKEN_FILE}: {e}")
    
    # Méthode B : se reconnecter via la session Playwright sauvegardée
    if not token and os.path.exists(JINKA_SESSION_FILE) and sync_playwright:
        try:
            print("[INFO] Pas de token direct, tentative via session Playwright...")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(storage_state=JINKA_SESSION_FILE)
                page = context.new_page()
                # Naviguer vers Jinka pour récupérer le token depuis le localStorage
                page.goto("https://www.jinka.fr/", wait_until="networkidle", timeout=20000)
                js_token = page.evaluate("""() => {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        const val = localStorage.getItem(key);
                        if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                            return val;
                        }
                    }
                    return null;
                }""")
                if js_token:
                    token = js_token
                    # Sauvegarder pour la prochaine fois
                    with open(JINKA_TOKEN_FILE, "w", encoding="utf-8") as f:
                        json.dump({"token": token}, f)
                    print("[OK] Token Jinka récupéré via session Playwright")
                browser.close()
        except Exception as e:
            print(f"[WARN] Échec de récupération du token via Playwright: {e}")
    
    if not token:
        print("[ERREUR] Aucun token Jinka disponible. Lancez d'abord: python login_jinka.py")
        return []
    
    # 2. Récupérer les alertes
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "Origin": "https://www.jinka.fr",
    }
    
    try:
        r_alerts = requests.get("https://api.jinka.fr/apiv2/alert", headers=headers, timeout=15)
        if r_alerts.status_code == 401:
            print("[ERREUR] Token Jinka expiré. Relancez: python login_jinka.py")
            return []
        if r_alerts.status_code != 200:
            print(f"[ERREUR] Échec de récupération des alertes Jinka: {r_alerts.status_code}")
            return []
        
        alerts = r_alerts.json()
        print(f"[INFO] {len(alerts)} alerte(s) Jinka trouvée(s).")
        
    except Exception as e:
        print(f"[ERREUR] Impossible de contacter l'API Jinka: {e}")
        return []
    
    # 3. Pour chaque alerte, récupérer les annonces
    for alert in alerts:
        alert_id = alert.get("id")
        alert_name = alert.get("name", "Sans nom")
        print(f"[INFO] Traitement alerte: {alert_name}")
        
        # Récupérer le dashboard (première page)
        try:
            r_dashboard = requests.get(
                f"https://api.jinka.fr/apiv2/alert/{alert_id}/dashboard",
                headers=headers,
                timeout=15
            )
            if r_dashboard.status_code != 200:
                print(f"[WARN] Impossible de charger le dashboard Jinka pour l'alerte {alert_name} (status {r_dashboard.status_code})")
                continue
            dashboard = r_dashboard.json()
            nb_pages = dashboard.get("pagination", {}).get("nbPages", 1)
            results = dashboard.get("ads", [])
            
            # Récupérer les pages suivantes (max 3 pages pour ne pas surcharger)
            for page_num in range(2, min(nb_pages + 1, 4)):
                try:
                    r_page = requests.get(
                        f"https://api.jinka.fr/apiv2/alert/{alert_id}/dashboard?page={page_num}",
                        headers=headers,
                        timeout=15
                    )
                    if r_page.status_code == 200:
                        page_results = r_page.json().get("ads", [])
                        results.extend(page_results)
                except Exception:
                    break
            
            print(f"[INFO] {len(results)} annonces récupérées pour l'alerte {alert_name}.")
            
            # 4. Normaliser chaque annonce au format attendu par le pipeline
            for item in results:
                try:
                    # Extraire les champs Jinka
                    jinka_price = item.get("rent")
                    jinka_surface = item.get("area")
                    jinka_rooms = item.get("room")
                    jinka_bedrooms = item.get("bedroom")
                    jinka_title = item.get("type") or item.get("title") or "Appartement"
                    jinka_desc = item.get("description", "")
                    jinka_id = item.get("id", "")
                    
                    # Lien de redirection Jinka pour voir l'annonce originale
                    external_id = item.get("external_id")
                    jinka_source = (item.get("source") or "").lower()
                    if "bienici" in jinka_source and external_id:
                        jinka_url = f"https://www.bienici.com/annonce/{external_id}"
                    elif "seloger" in jinka_source and external_id:
                        jinka_url = f"https://www.seloger.com/annonces/locations/appartement/lyon/{external_id}.htm"
                    elif "leboncoin" in jinka_source and external_id and external_id.isdigit():
                        jinka_url = f"https://www.leboncoin.fr/ad/locations/{external_id}"
                    else:
                        jinka_url = f"https://www.jinka.fr/ad/{jinka_id}"
                    
                    jinka_source = item.get("source_label") or item.get("source", "Jinka")
                    jinka_date = item.get("created_at") or item.get("date", "")
                    jinka_city = item.get("city", "Lyon")
                    jinka_zip = item.get("postal_code", "")
                    jinka_lat = item.get("lat") or item.get("latitude")
                    jinka_lon = item.get("lng") or item.get("longitude") or item.get("lon")
                    
                    # Convertir le flag meublé
                    furnished_val = item.get("furnished")
                    jinka_furnished = (furnished_val == 1 or furnished_val is True)
                    
                    # L'ascenseur est dans features.lift
                    features = item.get("features", {})
                    lift_val = features.get("lift") if isinstance(features, dict) else None
                    jinka_elevator = (lift_val == 1 or lift_val is True)
                    
                    jinka_floor = item.get("floor")
                    # Gérer -1 ou valeurs étranges pour l'étage
                    if jinka_floor is not None and int(jinka_floor) < 0:
                        jinka_floor = None
                    
                    # Certains champs peuvent être dans des sous-objets
                    if not jinka_lat and isinstance(item.get("location"), dict):
                        jinka_lat = item["location"].get("lat")
                        jinka_lon = item["location"].get("lng") or item["location"].get("lon")
                    
                    if not jinka_zip and isinstance(item.get("address"), dict):
                        jinka_zip = item["address"].get("zipcode", "")
                    
                    # Déterminer le code postal depuis la ville si manquant
                    if not jinka_zip:
                        city_lower = (jinka_city or "").lower()
                        desc_and_title = (jinka_title + " " + jinka_desc + " " + city_lower).lower()
                        for pc in ["69001", "69002", "69003", "69006"]:
                             if pc in desc_and_title:
                                 jinka_zip = pc
                                 break
                    
                    # Convertir le postal code en string propre
                    jinka_zip = str(jinka_zip).strip() if jinka_zip else ""
                    
                    # Déterminer le district
                    district_map = {
                        "69001": "Lyon 1er",
                        "69002": "Lyon 2e",
                        "69003": "Lyon 3e",
                        "69006": "Lyon 6e"
                    }
                    district_name = district_map.get(jinka_zip, f"Lyon {jinka_zip[-1]}e" if jinka_zip.startswith("6900") else "Lyon Centre")
                    
                    # Fallback coordonnées GPS depuis le quartier
                    if not jinka_lat or not jinka_lon:
                        jinka_lat, jinka_lon = get_district_coordinates(
                            jinka_title + " " + jinka_desc + " " + jinka_zip
                        )
                    
                    # Publication date
                    pub_date = ""
                    if jinka_date:
                        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S.%fZ"]:
                            try:
                                # Nettoyer le format de date
                                date_str = jinka_date[:19]
                                pub_date = datetime.strptime(date_str, fmt[:18]).strftime("%Y-%m-%d")
                                break
                            except ValueError:
                                continue
                        if not pub_date:
                            pub_date = jinka_date[:10]
                    
                    # Construire l'objet normalisé
                    ad_item = {
                        "source": f"Jinka ({jinka_source})",
                        "id": f"jinka_{jinka_id}",
                        "url": jinka_url,
                        "title": jinka_title,
                        "description": jinka_desc,
                        "price": float(jinka_price) if jinka_price else None,
                        "surfaceArea": float(jinka_surface) if jinka_surface else None,
                        "postalCode": jinka_zip,
                        "city": jinka_city or "Lyon",
                        "district": {"libelle": district_name},
                        "roomsQuantity": int(jinka_rooms) if jinka_rooms else None,
                        "bedroomsQuantity": int(jinka_bedrooms) if jinka_bedrooms else None,
                        "isFurnished": bool(jinka_furnished),
                        "publicationDate": pub_date,
                        "hasElevator": bool(jinka_elevator),
                        "floor": int(jinka_floor) if jinka_floor is not None else None,
                        "isGroundFloor": (jinka_floor == 0) if jinka_floor is not None else False,
                        "blurInfo": {
                            "position": {
                                "lat": float(jinka_lat) if jinka_lat else None,
                                "lon": float(jinka_lon) if jinka_lon else None
                            }
                        },
                        "hasBalcony": "balcon" in jinka_desc.lower() or "terrasse" in jinka_desc.lower(),
                        "hasTerrace": "terrasse" in jinka_desc.lower()
                    }
                    ads.append(ad_item)
                    
                except Exception as ex:
                    print(f"[WARN] Erreur parsing annonce Jinka {jinka_id}: {ex}")
                    continue
                    
        except Exception as e:
            print(f"[ERREUR] Échec de récupération alerte {alert_name}: {e}")
            continue
    
    print(f"[INFO] Total Jinka: {len(ads)} annonces récupérées.")
    return ads

def scrape_lodgis():
    """Récupère les annonces depuis Lodgis (spécialiste location meublée de standing à Lyon).
    Lodgis propose des annonces exclusives souvent absentes des agrégateurs classiques."""
    print("[INFO] Interrogation du site Lodgis...")
    ads = []
    
    if not sync_playwright:
        print("[ERREUR] Playwright n'est pas disponible pour Lodgis.")
        return []
    
    VALID_ARRONDISSEMENTS = {"1": "69001", "2": "69002", "3": "69003", "6": "69006"}
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            url = "https://www.lodgis.com/fr/lyon,location-meublee/location-meuble-lyon_19606.cat.html"
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)
            
            # Accept cookies if present
            try:
                cookie_btn = page.locator("button:has-text('Accepter'), button:has-text('Tout accepter'), #didomi-notice-agree-button")
                if cookie_btn.count() > 0:
                    cookie_btn.first.click()
                    page.wait_for_timeout(1000)
            except:
                pass
            
            html = page.content()
            
            # Parse cards from the search page
            import re as _re
            card_starts = [m.start() for m in _re.finditer(r'<div class="card card__appart">', html)]
            print(f"[INFO] {len(card_starts)} annonces trouvées sur Lodgis.")
            
            candidates = []
            for i, start in enumerate(card_starts):
                end = card_starts[i+1] if i + 1 < len(card_starts) else len(html)
                card_html = html[start:end]
                
                # Extract link
                link_match = _re.search(r'href="(https://www\.lodgis\.com/[^"]+\.mod\.html)"', card_html)
                if not link_match:
                    continue
                ad_url = link_match.group(1)
                
                # Extract ID
                id_match = _re.search(r'/(LPA\d+)', ad_url)
                ad_id = id_match.group(1) if id_match else None
                if not ad_id:
                    continue
                
                # Extract arrondissement from URL (e.g. -lyon-6.mod.html)
                arr_match = _re.search(r'-lyon-(\d+)\.mod\.html', ad_url)
                if not arr_match or arr_match.group(1) not in VALID_ARRONDISSEMENTS:
                    continue
                postal_code = VALID_ARRONDISSEMENTS[arr_match.group(1)]
                
                # Extract title
                title_match = _re.search(r'class="card-title card__appart__title">([^<]+)</p>', card_html)
                title = title_match.group(1).strip() if title_match else "Appartement"
                
                # Extract surface
                surface_match = _re.search(r'class="card-surface">([^<]+)</div>', card_html)
                surface = None
                if surface_match:
                    s_match = _re.search(r'(\d+(?:[.,]\d+)?)', surface_match.group(1))
                    if s_match:
                        surface = float(s_match.group(1).replace(",", "."))
                
                # Quick filter: surface > 75
                if not surface or surface < 75:
                    continue
                
                # Extract price
                price_match = _re.search(r'class="price">([^<]+)</span>', card_html)
                price = None
                if price_match:
                    price_clean = _re.sub(r'[^\d]', '', price_match.group(1))
                    if price_clean:
                        price = float(price_clean)
                
                # Quick filter: price 1500-2500
                if price and (price < 1500 or price > 2500):
                    continue
                
                # Quick filter: at least 2 bedrooms (filter out studios and 1-chambre)
                if "studio" in title.lower():
                    continue
                if "1 chambre" in title.lower():
                    continue
                
                candidates.append({
                    "id": ad_id,
                    "url": ad_url,
                    "title": title,
                    "surface": surface,
                    "price": price,
                    "postal_code": postal_code,
                })
            
            print(f"[INFO] {len(candidates)} annonces Lodgis passent le pré-filtrage. Récupération des détails...")
            
            # Visit detail pages for candidates
            for cand in candidates[:10]:  # Max 10 to avoid overloading
                try:
                    page.goto(cand["url"], wait_until="networkidle", timeout=20000)
                    page.wait_for_timeout(1000)
                    
                    body_text = page.locator("body").inner_text()
                    page_title = ""
                    try:
                        page_title = page.title()
                    except:
                        pass
                    
                    description = body_text
                    
                    # Extract rooms from title or description
                    rooms = None
                    rooms_match = _re.search(r'(\d+)\s*(?:pièces|pieces|p\.)', description, _re.IGNORECASE)
                    if rooms_match:
                        rooms = int(rooms_match.group(1))
                    else:
                        tf_match = _re.search(r'\b[tf](\d)\b', cand["title"] + " " + page_title, _re.IGNORECASE)
                        if tf_match:
                            rooms = int(tf_match.group(1))
                    
                    # Extract bedrooms
                    bedrooms = None
                    bed_match = _re.search(r'(\d+)\s*(?:chambres?|ch\b)', description, _re.IGNORECASE)
                    if bed_match:
                        bedrooms = int(bed_match.group(1))
                    elif "2 chambres" in cand["title"].lower():
                        bedrooms = 2
                    elif "3 chambres" in cand["title"].lower():
                        bedrooms = 3
                    
                    # Extract floor
                    floor = None
                    floor_match = _re.search(r'(\d+)(?:er|ème|e|eme)?\s*étage', description, _re.IGNORECASE)
                    if floor_match:
                        floor = int(floor_match.group(1))
                    
                    has_elevator = "ascenseur" in description.lower() and "sans ascenseur" not in description.lower()
                    is_rdc = "rez-de-chaussée" in description.lower() or "rdc" in description.lower()
                    if floor == 0:
                        is_rdc = True
                    
                    # Extract address from URL pattern
                    addr_match = _re.search(r'/LPA\d+-(.+?)-appartement-lyon', cand["url"])
                    address_hint = ""
                    if addr_match:
                        address_hint = addr_match.group(1).replace("-", " ").title()
                    
                    # Determine district label
                    district_map = {
                        "69001": "Lyon 1er",
                        "69002": "Lyon 2e",
                        "69003": "Lyon 3e",
                        "69006": "Lyon 6e"
                    }
                    district_name = district_map.get(cand["postal_code"], "Lyon Centre")
                    
                    # GPS coordinates based on postal code
                    lat, lon = get_district_coordinates(
                        address_hint + " " + cand["postal_code"] + " Lyon"
                    )
                    
                    ad_item = {
                        "source": "Lodgis",
                        "id": f"lodgis_{cand['id']}",
                        "url": cand["url"],
                        "title": cand["title"],
                        "description": description,
                        "price": cand["price"],
                        "surfaceArea": cand["surface"],
                        "postalCode": cand["postal_code"],
                        "city": "Lyon",
                        "district": {"libelle": district_name},
                        "roomsQuantity": rooms,
                        "bedroomsQuantity": bedrooms,
                        "isFurnished": True,  # Lodgis = meublé uniquement
                        "publicationDate": datetime.now().strftime("%Y-%m-%d"),
                        "hasElevator": has_elevator,
                        "floor": floor,
                        "isGroundFloor": is_rdc,
                        "blurInfo": {
                            "position": {
                                "lat": lat,
                                "lon": lon
                            }
                        },
                        "hasBalcony": "balcon" in description.lower() or "terrasse" in description.lower(),
                        "hasTerrace": "terrasse" in description.lower()
                    }
                    ads.append(ad_item)
                    
                except Exception as ex:
                    print(f"[ERREUR] Échec du scraping de {cand['url']}: {ex}")
            
            browser.close()
    except Exception as e:
        print(f"[ERREUR] Échec de la récupération sur Lodgis: {e}")
    
    print(f"[INFO] Total Lodgis: {len(ads)} annonces récupérées.")
    return ads

def scrape_urbansejour():
    """Récupère les annonces depuis Urban Séjour (spécialiste location meublée à Lyon).
    Petite agence locale avec un inventaire exclusif non présent sur les agrégateurs."""
    print("[INFO] Interrogation du site Urban Séjour...")
    ads = []
    
    if not sync_playwright:
        print("[ERREUR] Playwright n'est pas disponible pour Urban Séjour.")
        return []
    
    VALID_PREFIXES = {
        "lyon-1-": "69001",
        "lyon-2-": "69002",
        "lyon-3-": "69003",
        "lyon-6-": "69006",
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            })
            
            # 1. Crawl listing pages to discover all apartment URLs
            import re as _re
            all_apt_links = set()
            pages_to_crawl = [
                "https://www.urbansejour.com/",
                "https://www.urbansejour.com/appartements-par-localisation/",
                "https://www.urbansejour.com/location-meublee/lyon/",
                "https://www.urbansejour.com/location-meublee/lyon-1/",
                "https://www.urbansejour.com/location-meublee/lyon-2/",
                "https://www.urbansejour.com/location-meublee/lyon-3/",
                "https://www.urbansejour.com/location-meublee/lyon-6/",
            ]
            
            for crawl_url in pages_to_crawl:
                try:
                    resp = page.goto(crawl_url, wait_until="domcontentloaded", timeout=20000)
                    if resp and resp.status == 200:
                        html = page.content()
                        links = _re.findall(r'href="(https://www\.urbansejour\.com/appartement/[^"#]+)"', html)
                        all_apt_links.update(links)
                except:
                    pass
            
            # 2. Filter for target arrondissements only
            filtered_links = []
            for link in sorted(all_apt_links):
                # Extract arrondissement from URL
                postal_code = None
                for prefix, pc in VALID_PREFIXES.items():
                    if prefix in link:
                        postal_code = pc
                        break
                if not postal_code:
                    continue
                
                # Pre-filter from URL slug: skip studios and 1-chambre
                slug = link.lower()
                if "studio" in slug:
                    continue
                if "1-chambre" in slug and "2-chambre" not in slug and "3-chambre" not in slug:
                    continue
                
                filtered_links.append({"url": link, "postal_code": postal_code})
            
            print(f"[INFO] {len(all_apt_links)} annonces trouvées sur Urban Séjour, {len(filtered_links)} après pré-filtrage.")
            
            # 3. Visit each detail page
            for cand in filtered_links[:15]:  # Max 15
                try:
                    page.goto(cand["url"], wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(1000)
                    
                    body_text = page.locator("body").inner_text()
                    page_title = ""
                    try:
                        page_title = page.title()
                    except:
                        pass
                    
                    description = body_text
                    
                    # Extract surface (first m² mention that's > 20)
                    surface = None
                    surface_matches = _re.findall(r'(\d+(?:[.,]\d+)?)\s*m[²2]', description)
                    for sm in surface_matches:
                        val = float(sm.replace(",", "."))
                        if val > 20:
                            surface = val
                            break
                    
                    # Quick filter: surface > 75
                    if not surface or surface < 75:
                        continue
                    
                    # Extract price (first €/mois pattern)
                    price = None
                    price_matches = _re.findall(r'(\d[\d\s]*(?:,\d+)?)\s*€\s*(?:/\s*mois)?', description)
                    for pm in price_matches:
                        val_str = _re.sub(r'[^\d,.]', '', pm).replace(",", ".")
                        try:
                            val = float(val_str)
                            if 500 < val < 5000:  # Reasonable rent range
                                price = val
                                break
                        except:
                            pass
                    
                    # Quick filter: price 1500-2500
                    if price and (price < 1500 or price > 2500):
                        continue
                    
                    # Extract rooms
                    rooms = None
                    rooms_match = _re.search(r'(\d+)\s*(?:pièces|pieces|p\.)', description, _re.IGNORECASE)
                    if rooms_match:
                        rooms = int(rooms_match.group(1))
                    else:
                        tf_match = _re.search(r'\b[tf](\d)\b', page_title + " " + cand["url"], _re.IGNORECASE)
                        if tf_match:
                            rooms = int(tf_match.group(1))
                    
                    # Extract bedrooms
                    bedrooms = None
                    bed_match = _re.search(r'(\d+)\s*chambre', description, _re.IGNORECASE)
                    if bed_match:
                        bedrooms = int(bed_match.group(1))
                    elif "2 chambres" in cand["url"]:
                        bedrooms = 2
                    elif "3 chambres" in cand["url"]:
                        bedrooms = 3
                    
                    # Extract floor
                    floor = None
                    floor_match = _re.search(r'(\d+)(?:er|ème|e|eme)?\s*étage', description, _re.IGNORECASE)
                    if floor_match:
                        floor = int(floor_match.group(1))
                    
                    has_elevator = "ascenseur" in description.lower() and "sans ascenseur" not in description.lower()
                    is_rdc = "rez-de-chaussée" in description.lower() or "rdc" in description.lower()
                    if floor == 0:
                        is_rdc = True
                    
                    # Generate ad ID from URL slug
                    slug_match = _re.search(r'/appartement/(.+?)/?$', cand["url"])
                    ad_slug = slug_match.group(1) if slug_match else "unknown"
                    ad_id = f"urbansejour_{ad_slug[:50]}"
                    
                    # Title from page or URL
                    title = page_title.split(" - ")[0].strip() if page_title else "Appartement Urban Séjour"
                    if "Location" in title:
                        title = title.split("Location")[0].strip()
                    
                    # District label
                    district_map = {
                        "69001": "Lyon 1er",
                        "69002": "Lyon 2e",
                        "69003": "Lyon 3e",
                        "69006": "Lyon 6e"
                    }
                    district_name = district_map.get(cand["postal_code"], "Lyon Centre")
                    
                    # GPS coordinates
                    lat, lon = get_district_coordinates(
                        district_name + " " + cand["postal_code"] + " Lyon"
                    )
                    
                    ad_item = {
                        "source": "Urban Séjour",
                        "id": ad_id,
                        "url": cand["url"],
                        "title": title,
                        "description": description,
                        "price": price,
                        "surfaceArea": surface,
                        "postalCode": cand["postal_code"],
                        "city": "Lyon",
                        "district": {"libelle": district_name},
                        "roomsQuantity": rooms,
                        "bedroomsQuantity": bedrooms,
                        "isFurnished": True,  # Urban Séjour = meublé uniquement
                        "publicationDate": datetime.now().strftime("%Y-%m-%d"),
                        "hasElevator": has_elevator,
                        "floor": floor,
                        "isGroundFloor": is_rdc,
                        "blurInfo": {
                            "position": {
                                "lat": lat,
                                "lon": lon
                            }
                        },
                        "hasBalcony": "balcon" in description.lower() or "terrasse" in description.lower(),
                        "hasTerrace": "terrasse" in description.lower()
                    }
                    ads.append(ad_item)
                    
                except Exception as ex:
                    print(f"[ERREUR] Échec du scraping Urban Séjour {cand['url']}: {ex}")
            
            browser.close()
    except Exception as e:
        print(f"[ERREUR] Échec de la récupération sur Urban Séjour: {e}")
    
    print(f"[INFO] Total Urban Séjour: {len(ads)} annonces récupérées.")
    return ads

def scrape_gdc():
    """Récupère les annonces depuis Gens de Confiance.
    Nécessite d'avoir lancé login_gdc.py au moins une fois."""
    print("[INFO] Interrogation du site Gens de Confiance...")
    ads = []
    
    if not sync_playwright:
        print("[ERREUR] Playwright n'est pas disponible pour Gens de Confiance.")
        return []
        
    SESSION_FILE = "gdc_session.json"
    URL_FILE = "gdc_url.json"
    
    if not os.path.exists(SESSION_FILE):
        print("[WARN] Session Gens de Confiance absente. Lancez d'abord: python login_gdc.py")
        return []
        
    search_url = "https://gensdeconfiance.com/fr/s/immobilier/locations-immobilieres?type=offering&rootLocales=fr%2Cen&currentAdSort=displayDate_desc"
    if os.path.exists(URL_FILE):
        try:
            with open(URL_FILE, "r", encoding="utf-8") as f:
                url_data = json.load(f)
                search_url = url_data.get("search_url", search_url)
        except Exception as e:
            print(f"[WARN] Impossible de lire {URL_FILE}: {e}")
            
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=SESSION_FILE,
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            print(f"[INFO] Navigation vers {search_url}...")
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            
            # Dismiss cookie banner
            try:
                cookie_btn = page.locator("button#axeptio_btn_acceptAll")
                if cookie_btn.count() > 0:
                    cookie_btn.first.click(force=True)
                    page.wait_for_timeout(500)
            except:
                pass
                
            try:
                page.wait_for_selector("a[href*='/ui/post/'], a[href*='/annonce/']", timeout=15000)
            except Exception as e:
                print(f"[WARN] Aucune annonce trouvée ou chargement trop long sur GDC: {e}")
                browser.close()
                return []
                
            cards = page.locator("a[href*='/ui/post/'], a[href*='/annonce/']").all()
            print(f"[INFO] {len(cards)} éléments d'annonces trouvés sur Gens de Confiance.")
            
            candidates = []
            seen_urls = set()
            
            for card in cards:
                try:
                    href = card.get_attribute("href")
                    if not href or not ("/ui/post/" in href or "/annonce/" in href):
                        continue
                    
                    ad_url = href if href.startswith("http") else f"https://gensdeconfiance.com{href}"
                    norm_url = ad_url.split('?')[0]
                    if norm_url in seen_urls:
                        continue
                    seen_urls.add(norm_url)
                    
                    text = card.inner_text()
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    if not lines:
                        continue
                        
                    price = None
                    for line in lines:
                        if "€" in line:
                            price_digits = "".join(c for c in line if c.isdigit())
                            if price_digits:
                                price = float(price_digits)
                                break
                            
                    title_line = ""
                    for line in lines:
                        if len(line) > len(title_line) and not any(kw in line for kw in ["€", "minutes", "secondes", "heure", "jour"]):
                            title_line = line
                    
                    postal_code = "69002"
                    for pc in ["69001", "69002", "69003", "69006"]:
                        if pc in text:
                            postal_code = pc
                            break
                    for dist in ["Lyon 1e", "Lyon 2e", "Lyon 3e", "Lyon 6e", "Lyon 1er", "Lyon 2ème", "Lyon 3ème", "Lyon 6ème", "Lyon 1", "Lyon 2", "Lyon 3", "Lyon 6"]:
                        if dist in text:
                            if "1" in dist: postal_code = "69001"
                            elif "2" in dist: postal_code = "69002"
                            elif "3" in dist: postal_code = "69003"
                            elif "6" in dist: postal_code = "69006"
                            break
                    
                    surface = None
                    m = re.search(r'(\d+(?:[.,]\d+)?)\s*m²', text, re.IGNORECASE)
                    if m:
                        surface = float(m.group(1).replace(",", "."))
                        
                    if price and (price < 1500 or price > 2500):
                        continue
                    if surface and surface <= 75:
                        continue
                        
                    candidates.append({
                        "url": norm_url,
                        "title": title_line or "Appartement Gens de Confiance",
                        "price": price,
                        "surface": surface,
                        "postal_code": postal_code,
                        "card_text": text
                    })
                except Exception as ex:
                    print(f"[WARN] Erreur pré-parsing carte GDC: {ex}")
                    
            print(f"[INFO] {len(candidates)} annonces GDC passent le pré-filtrage. Récupération des détails...")
            
            for cand in candidates[:10]:
                try:
                    page.goto(cand["url"], wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    page_title = page.title()
                    description = page.locator("body").inner_text()
                    
                    if "Just a moment" in page_title or "Verification" in page_title or len(description) < 400:
                        print(f"[WARN] Impossible de charger les détails pour {cand['url']} (Cloudflare ou bloqué). Utilisation du texte de la carte.")
                        description = cand["card_text"]
                    
                    rooms = None
                    rooms_match = re.search(r'(\d+)\s*(?:pièces|pieces|p\.)', description, re.IGNORECASE)
                    if rooms_match:
                        rooms = int(rooms_match.group(1))
                        
                    bedrooms = None
                    bed_match = re.search(r'(\d+)\s*(?:chambres|chambre|ch\b)', description, re.IGNORECASE)
                    if bed_match:
                        bedrooms = int(bed_match.group(1))
                        
                    floor = None
                    floor_match = re.search(r'(\d+)(?:er|ème|e|eme)?\s*étage', description, re.IGNORECASE)
                    if floor_match:
                        floor = int(floor_match.group(1))
                        
                    has_elevator = "ascenseur" in description.lower() and "sans ascenseur" not in description.lower()
                    is_rdc = "rez-de-chaussée" in description.lower() or "rdc" in description.lower()
                    if floor == 0:
                        is_rdc = True
                        
                    postal_code = cand["postal_code"]
                    for pc in ["69001", "69002", "69003", "69006"]:
                        if pc in description:
                            postal_code = pc
                            break
                            
                    district_map = {
                        "69001": "Lyon 1er",
                        "69002": "Lyon 2e",
                        "69003": "Lyon 3e",
                        "69006": "Lyon 6e"
                    }
                    district_name = district_map.get(postal_code, "Lyon Centre")
                    
                    lat, lon = get_district_coordinates(
                        cand["title"] + " " + description + " " + postal_code
                    )
                    
                    # Extract unique identifier from URL
                    slug = cand['url'].split('/')[-1].split('?')[0]
                    suffix = slug.split('-')[-1]
                    ad_id = f"gdc_{suffix}"
                    
                    ad_item = {
                        "source": "Gens de Confiance",
                        "id": ad_id,
                        "url": cand["url"],
                        "title": cand["title"],
                        "description": description,
                        "price": cand["price"],
                        "surfaceArea": cand["surface"],
                        "postalCode": postal_code,
                        "city": "Lyon",
                        "district": {"libelle": district_name},
                        "roomsQuantity": rooms,
                        "bedroomsQuantity": bedrooms,
                        "isFurnished": is_text_furnished(cand["title"] + " " + description),
                        "publicationDate": datetime.now().strftime("%Y-%m-%d"),
                        "hasElevator": has_elevator,
                        "floor": floor,
                        "isGroundFloor": is_rdc,
                        "blurInfo": {
                            "position": {
                                "lat": lat,
                                "lon": lon
                            }
                        },
                        "hasBalcony": "balcon" in description.lower() or "terrasse" in description.lower(),
                        "hasTerrace": "terrasse" in description.lower()
                    }
                    ads.append(ad_item)
                    
                except Exception as ex:
                    print(f"[ERREUR] Échec du scraping de {cand['url']}: {ex}")
                    
            browser.close()
    except Exception as e:
        print(f"[ERREUR] Échec de la récupération sur Gens de Confiance: {e}")
        
    print(f"[INFO] Total Gens de Confiance: {len(ads)} annonces récupérées.")
    return ads

def start_server_if_not_running():
    import socket
    import subprocess
    import sys
    
    port = 8000
    is_running = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect(("127.0.0.1", port))
            is_running = True
    except (socket.timeout, ConnectionRefusedError, OSError):
        is_running = False

    if is_running:
        print(f"[INFO] Le serveur est déjà lancé sur le port {port}.")
    else:
        print(f"[INFO] Le serveur n'est pas lancé. Démarrage de server.py...")
        server_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")
        try:
            log_file = open("server.log", "w", encoding="utf-8")
            if sys.platform == "win32":
                subprocess.Popen(
                    [sys.executable, "-u", server_path],
                    creationflags=subprocess.DETACHED_PROCESS,
                    stdout=log_file,
                    stderr=subprocess.STDOUT
                )
            else:
                subprocess.Popen(
                    [sys.executable, "-u", server_path],
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    start_new_session=True
                )
            log_file.close()
            print("[INFO] server.py lancé avec succès.")
        except Exception as e:
            print(f"[ERREUR] Impossible de lancer server.py: {e}")

def main():
    print("=== Démarrage de l'Agent de Recherche Immobilière ===")
    
    # 1. Load existing listings
    existing_data = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    existing_data = json.loads(content)
            print(f"[INFO] {len(existing_data)} annonces chargées depuis {DATA_FILE}")
        except Exception as e:
            print(f"[ERREUR] Impossible de charger {DATA_FILE}: {e}")
            existing_data = []
    else:
        print(f"[INFO] Le fichier {DATA_FILE} n'existe pas encore, il sera créé.")
    
    existing_urls = {item.get("lien_annonce") for item in existing_data if item.get("lien_annonce")}
    
    # 2. Scrape multiple sources
    all_raw_ads = []
    
    # Source A: Bien'ici (JSON API, very stable)
    try:
        all_raw_ads.extend(scrape_bienici())
    except Exception as e:
        print(f"[ERREUR] Échec du scan Bien'ici: {e}")
        
    # Source B: Barnes Lyon (Playwright, Prestige)
    try:
        all_raw_ads.extend(scrape_barnes())
    except Exception as e:
        print(f"[ERREUR] Échec du scan Barnes Lyon: {e}")
    
    # Source C: Jinka (agrégateur — accède à SeLoger, LeBonCoin, PAP, etc.)
    try:
        all_raw_ads.extend(scrape_jinka())
    except Exception as e:
        print(f"[ERREUR] Échec du scan Jinka: {e}")
    
    # Source E: Lodgis (spécialiste location meublée de standing)
    try:
        all_raw_ads.extend(scrape_lodgis())
    except Exception as e:
        print(f"[ERREUR] Échec du scan Lodgis: {e}")
    
    # Source F: Urban Séjour (agence locale meublée de qualité)
    try:
        all_raw_ads.extend(scrape_urbansejour())
    except Exception as e:
        print(f"[ERREUR] Échec du scan Urban Séjour: {e}")
        
    # Source G: Gens de Confiance (Playwright + Session)
    try:
        all_raw_ads.extend(scrape_gdc())
    except Exception as e:
        print(f"[ERREUR] Échec du scan Gens de Confiance: {e}")
        
    # Source D: LeBonCoin (désactivé — protégé par DataDome/captcha même via Playwright)
    # PAP et SeLoger sont également bloqués par Cloudflare.
    # Jinka couvre ces sources via l'agrégation.
    # Pour réactiver le scraping direct, décommenter la ligne ci-dessous :
    # try:
    #     all_raw_ads.extend(scrape_leboncoin())
    # except Exception as e:
    #     print(f"[ERREUR] Échec du scan LeBonCoin: {e}")
    print("[INFO] LeBonCoin, PAP, SeLoger : désactivés (anti-bot / captcha).")
        
    print(f"[INFO] {len(all_raw_ads)} annonces brutes récoltées au total. Début du filtrage et de la validation...")
    
    new_listings_count = 0
    current_date = datetime.now().date()
    
    for ad in all_raw_ads:
        ad_id = ad.get("id")
        ad_url = ad.get("url")
        
        # A. Check duplicates
        if ad_url in existing_urls:
            continue
            
        title = ad.get("title", "Appartement")
        description = ad.get("description", "")
        price = ad.get("price")
        surface = ad.get("surfaceArea")
        postal_code = ad.get("postalCode", "")
        city = ad.get("city", "")
        district_libelle = ad.get("district", {}).get("libelle", "Lyon Centre")
        
        # B. Parse fields from text if missing
        nb_pieces = ad.get("roomsQuantity")
        if not nb_pieces:
            match = re.search(r'\b([34])\s*(?:pièces|pieces|p\.)\b', description, re.IGNORECASE)
            if match:
                nb_pieces = int(match.group(1))
            else:
                match = re.search(r'\b[tf]([34])\b', title + " " + description, re.IGNORECASE)
                if match:
                    nb_pieces = int(match.group(1))
                    
        nb_chambres = ad.get("bedroomsQuantity")
        if not nb_chambres:
            match = re.search(r'\b([234])\s*(?:chambres|chambre|ch\b)', description, re.IGNORECASE)
            if match:
                nb_chambres = int(match.group(1))
            else:
                if "deux chambres" in description.lower() or "2 chambres" in description.lower():
                    nb_chambres = 2
                elif "trois chambres" in description.lower() or "3 chambres" in description.lower():
                    nb_chambres = 3
                    
        if not surface:
            match = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(?:m²|m2|metres carrés|mètres carrés)\b', description, re.IGNORECASE)
            if match:
                surface = float(match.group(1).replace(",", "."))
                
        if not price:
            match = re.search(r'\b(\d{1,3}(?:\s*\d{3})*(?:[.,]\d+)?)\s*(?:€|euros|euro)\b', description, re.IGNORECASE)
            if match:
                price = float(match.group(1).replace(" ", "").replace(",", "."))
                
        # C. Filter Validation
        # 1. Furnished check (Meublé only)
        is_furnished = ad.get("isFurnished", False) or is_text_furnished(title + " " + description) or ad.get("furnished", False)
        if not is_furnished:
            print(f"[REJECT] {ad_id}: Logement non meublé.")
            continue

        # 1b. Climatisation check (Mandatory)
        has_ac = any(kw in (title + " " + description).lower() for kw in ["clim", "climatisation", "climatise", "climatisé"])
        if not has_ac:
            print(f"[REJECT] {ad_id}: Pas de climatisation.")
            continue

        # 1c. Duplex check (Forbidden)
        is_duplex = "duplex" in (title + " " + description).lower()
        if is_duplex:
            print(f"[REJECT] {ad_id}: Logement en duplex.")
            continue
            
        # 2. Surface check (> 75 m²)
        if not surface or surface <= 75:
            print(f"[REJECT] {ad_id}: Surface de {surface} m² insuffisante.")
            continue
            
        # 3. Rooms check (3 to 4 max, min 2 bedrooms)
        if nb_pieces and (nb_pieces < 3 or nb_pieces > 4):
            print(f"[REJECT] {ad_id}: {nb_pieces} pièces (attendu: 3 ou 4).")
            continue
        if nb_chambres and nb_chambres < 2:
            print(f"[REJECT] {ad_id}: {nb_chambres} chambres (attendu: >= 2).")
            continue
            
        # 4. Price check (1500 to 2500 CC)
        if price and (price < 1500 or price > 2500):
            print(f"[REJECT] {ad_id}: Loyer {price}€ hors budget.")
            continue
            
        # 5. Age check (Max 14 days)
        pub_date_str = ad.get("publicationDate")
        if not pub_date_str or pub_date_str.startswith("1970-01-01"):
            pub_date_str = ad.get("modificationDate")
        if not pub_date_str or pub_date_str.startswith("1970-01-01"):
            pub_date_str = current_date.strftime("%Y-%m-%d")
            
        if pub_date_str:
            try:
                pub_date = datetime.strptime(pub_date_str[:10], "%Y-%m-%d").date()
                days_ago = (current_date - pub_date).days
                if days_ago > 14:
                    print(f"[REJECT] {ad_id}: Annonce trop ancienne ({days_ago} jours).")
                    continue
            except Exception:
                pass
                
        # 6. Location check (69001, 69002, 69003, 69006)
        if postal_code not in ["69001", "69002", "69003", "69006"]:
            print(f"[REJECT] {ad_id}: Code postal {postal_code} en dehors de Lyon Centre.")
            continue
            
        # 7. Elevator check (Mandatory unless ground floor RDC)
        has_elevator = ad.get("hasElevator", False)
        floor = ad.get("floor")
        is_rdc = (floor == 0) or ad.get("isGroundFloor", False) or "rez-de-chaussée" in description.lower() or "rdc" in description.lower()
        if not is_rdc and not has_elevator:
            print(f"[REJECT] {ad_id}: Pas d'ascenseur au {floor if floor else 'étage inconnu'}ème étage.")
            continue
            
        # 8. Transport check (Metro / Tram close)
        lat = ad.get("blurInfo", {}).get("position", {}).get("lat")
        lon = ad.get("blurInfo", {}).get("position", {}).get("lon")
        nearest_station = None
        min_dist = float('inf')
        if lat and lon:
            for station in METRO_TRAM_STATIONS:
                dist = haversine(lat, lon, station["lat"], station["lon"])
                if dist < min_dist:
                    min_dist = dist
                    nearest_station = station
            
            if min_dist > 800:
                print(f"[REJECT] {ad_id}: Trop loin du métro/tram ({int(min_dist)}m).")
                continue
        else:
            print(f"[REJECT] {ad_id}: Coordonnées GPS indisponibles.")
            continue

        # 9. Commute time check (max 45 min to Framatome Gerland)
        commute = estimate_travel_time(nearest_station["name"], min_dist)
        if commute > 45:
            print(f"[REJECT] {ad_id}: Trajet trop long vers Framatome ({commute} min).")
            continue
        # D. Duplicate check by size/price/arrondissement (in case of duplicate syndication)
        quartier = f"{district_libelle}, {city}"
        formatted_price = f"{price:,.2f} €".replace(",", " ").replace(".", ",")
        
        def get_arr(text, zip_code):
            if zip_code and zip_code.startswith("6900"):
                return zip_code[-1]
            match = re.search(r'Lyon\s*(\d+)', text, re.IGNORECASE)
            return match.group(1) if match else None

        new_arr = get_arr(quartier + " " + title, postal_code)
        
        is_dupe = False
        for item in existing_data:
            if item.get("lien_annonce") == ad_url:
                is_dupe = True
                break
            
            same_price = item.get("prix") == formatted_price
            same_surface = abs(item.get("surface", 0) - surface) < 1.0
            
            if same_price and same_surface:
                exist_arr = get_arr(item.get("quartier", "") + " " + item.get("titre", "") + " " + item.get("adresse_estimee", ""), "")
                if new_arr and exist_arr and new_arr == exist_arr:
                    is_dupe = True
                    break
                    
        if is_dupe:
            print(f"[DUPLICATE] {ad_id}: Annonce déjà présente (doublon).")
            continue
            
        # E. Address and Google Street View
        exact_addr = extract_address(description, postal_code)
        if exact_addr and any(char.isdigit() for char in exact_addr.split(',')[0]):
            adresse_estimee = exact_addr
            google_street_view = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(exact_addr)}"
        else:
            adresse_estimee = f"Quartier {district_libelle}"
            google_street_view = ""
            
        # F. Advantages and Disadvantages
        advantages_list = []
        inconvenients_list = []
        
        if has_elevator:
            advantages_list.append("ascenseur")
        elif not is_rdc:
            inconvenients_list.append("sans ascenseur")
            
        if floor and floor >= 4:
            advantages_list.append(f"étage élevé ({floor}ème)")
            
        if ad.get("hasBalcony") or ad.get("hasTerrace") or "balcon" in description.lower() or "terrasse" in description.lower():
            advantages_list.append("balcon/terrasse")
        else:
            inconvenients_list.append("sans balcon/terrasse")
            
        if "parking" in description.lower() or "garage" in description.lower() or "box" in description.lower():
            advantages_list.append("parking/garage")
            
        if "clim" in description.lower() or "climatisation" in description.lower() or "climatise" in description.lower():
            advantages_list.append("climatisation")
            
        if any(kw in description.lower() for kw in ["cachet", "ancien", "parquet", "cheminée", "cheminee", "moulure", "hauteur sous plafond"]):
            advantages_list.append("cachet de l'ancien")
            
        if any(kw in description.lower() for kw in ["cuisine équipée", "cuisine equipee", "cuisine aménagée", "cuisine amenagee", "cuisine meublée", "cuisine meublee"]):
            advantages_list.append("cuisine équipée")
        else:
            inconvenients_list.append("cuisine non équipée ou non mentionnée")
            
        has_calm = any(kw in description.lower() for kw in ["calme", "paisible", "silencieux", "cour intérieure", "cour interieure", "double vitrage"])
        has_noisy = any(kw in description.lower() for kw in ["bruyant", "bruit", "rue passante", "bars", "animation", "animé", "anime"])
        
        if has_calm and not has_noisy:
            advantages_list.append("calme")
        elif has_noisy:
            inconvenients_list.append("bruit potentiel")
            
        if nearest_station:
            dist_str = f"proche métro/tram ({nearest_station['name']} à {int(min_dist)}m)"
            advantages_list.append(dist_str)
            
            commute_time = estimate_travel_time(nearest_station["name"], min_dist)
            advantages_list.append(f"trajet Framatome Gerland ~{commute_time} min")
            
        avantages = ", ".join(advantages_list)
        inconvenients = ", ".join(inconvenients_list)
        
        # G. Save format
        new_item = {
            "titre": title if title != "APPARTEMENT" else f"Appartement T{nb_pieces} de {surface} m², {city}",
            "prix": formatted_price,
            "surface": float(surface),
            "nb_pieces": int(nb_pieces) if nb_pieces else 3,
            "quartier": quartier,
            "adresse_estimee": adresse_estimee,
            "avantages": avantages,
            "inconvenients": inconvenients,
            "prix_m2": round(price / surface, 2) if price and surface else 0.0,
            "source": ad.get("source", "Bien'ici"),
            "lien_annonce": ad_url,
            "google_street_view": google_street_view,
            "date_decouverte": datetime.now().strftime("%Y-%m-%d"),
            "statut": "Nouveau",
            "remarques_visite": "",
            "questions_visite": "",
            "notes": f"Avantages: {avantages}\nInconvénients: {inconvenients}"
        }
        
        existing_data.append(new_item)
        existing_urls.add(ad_url)
        new_listings_count += 1
        print(f"[OK] Nouvelle annonce ajoutée : {new_item['titre']} ({new_item['prix']})")
        
    # 3. Write back to data.json
    if new_listings_count > 0:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
            print(f"[INFO] Scan terminé. {new_listings_count} nouvelles annonces ajoutées à {DATA_FILE}.")
        except Exception as e:
            print(f"[ERREUR] Impossible de sauvegarder dans {DATA_FILE}: {e}")
    else:
        print("[INFO] Scan terminé. Aucune nouvelle annonce trouvée.")

    # 4. Start the server if not already running
    start_server_if_not_running()
    
if __name__ == "__main__":
    main()
