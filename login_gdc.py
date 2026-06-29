"""
Script de connexion Gens de Confiance.
Permet d'enregistrer la session pour contourner la protection Cloudflare.

Propose deux méthodes :
1) Ouverture automatique d'un vrai Chrome avec masquage anti-détection.
2) Saisie manuelle des cookies exportés en JSON via une extension de navigateur (ex: Cookie-Editor).
"""
import json
import os
import sys

SESSION_FILE = "gdc_session.json"
URL_FILE = "gdc_url.json"

def save_cookies_from_json(json_str):
    try:
        cookies_list = json.loads(json_str.strip())
        if not isinstance(cookies_list, list):
            # Check if it was wrapped in a storage state format already
            if isinstance(cookies_list, dict) and "cookies" in cookies_list:
                cookies_list = cookies_list["cookies"]
            else:
                print("[ERREUR] Le format JSON doit être une liste de cookies ou un objet storageState.")
                return False
                
        playwright_cookies = []
        for c in cookies_list:
            same_site = c.get("sameSite", "Lax")
            if same_site:
                same_site = same_site.strip().capitalize()
                if same_site not in ["Lax", "Strict", "None"]:
                    same_site = "Lax"
            else:
                same_site = "Lax"
                
            # Convert expiration date
            expires = c.get("expirationDate") or c.get("expires")
            if expires is not None:
                try:
                    expires = int(float(expires))
                except:
                    expires = -1
            else:
                expires = -1
                
            playwright_cookie = {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": c.get("domain"),
                "path": c.get("path", "/"),
                "expires": expires,
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": same_site
            }
            playwright_cookies.append(playwright_cookie)
            
        storage_state = {
            "cookies": playwright_cookies,
            "origins": []
        }
        
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(storage_state, f, ensure_ascii=False, indent=2)
            
        # Créer une URL de recherche par défaut pour Lyon
        default_url = "https://gensdeconfiance.com/fr/s/immobilier/locations-immobilieres?type=offering&rootLocales=fr%2Cen&currentAdSort=displayDate_desc"
        with open(URL_FILE, "w", encoding="utf-8") as f_url:
            json.dump({"search_url": default_url}, f_url, ensure_ascii=False, indent=2)
            
        print(f"\n[OK] Session de cookies sauvegardée dans {SESSION_FILE} !")
        print(f"[INFO] L'URL de recherche par défaut pour Lyon a été initialisée dans {URL_FILE}.")
        return True
    except Exception as e:
        print(f"[ERREUR] Impossible de décoder ou de structurer les cookies : {e}")
        return False

def run_playwright_stealth():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERREUR] Playwright n'est pas installé. Lancez: pip install playwright && playwright install chromium")
        return False

    print("\nTentative de lancement d'un navigateur Chrome réel avec masquage anti-bot...")
    print("1. Si la page de vérification Cloudflare s'affiche, complétez-la ou patientez.")
    print("2. Connectez-vous à votre compte Gens de Confiance.")
    print("3. Recherchez 'Lyon' et appliquez vos filtres de recherche.")
    print("4. Une fois les annonces affichées, revenez ici et appuyez sur Entrée.")
    print()

    try:
        with sync_playwright() as p:
            # Essayer de lancer Chrome installé sur le système pour avoir des signatures réelles
            browser = p.chromium.launch(
                headless=False,
                channel="chrome", # Utilise le vrai Chrome du système
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ]
            )
            
            # Charger la session existante si dispo
            if os.path.exists(SESSION_FILE):
                context = browser.new_context(
                    storage_state=SESSION_FILE,
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            else:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            
            page = context.new_page()
            # Cacher le flag navigator.webdriver
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            page.goto("https://gensdeconfiance.com/fr/s/immobilier/locations-immobilieres", wait_until="domcontentloaded", timeout=45000)
            
            input(">>> Appuyez sur Entrée une fois connecté et la recherche Lyon affichée... ")
            
            # Enregistrer la session
            context.storage_state(path=SESSION_FILE)
            search_url = page.url
            with open(URL_FILE, "w", encoding="utf-8") as f:
                json.dump({"search_url": search_url}, f, ensure_ascii=False, indent=2)
                
            print(f"\n[OK] Session sauvegardée dans {SESSION_FILE}")
            print(f"[OK] URL de recherche sauvegardée : {search_url}")
            browser.close()
            return True
    except Exception as e:
        print(f"[ERREUR] Échec de la connexion automatique Playwright Stealth : {e}")
        print("[INFO] Essayez la méthode d'importation de cookies (Option 2) pour contourner le blocage.")
        return False

def main():
    print("=" * 60)
    print("  Connexion Gens de Confiance - Gestion de la session")
    print("=" * 60)
    print()
    print("Comme Gens de Confiance est protégé par Cloudflare, la connexion automatique")
    print("peut être bloquée sur la vérification de sécurité.")
    print()
    print("1) Tenter la connexion automatique (Playwright Stealth avec votre Chrome)")
    print("2) Importer manuellement les Cookies au format JSON (Recommandé - 100% fonctionnel)")
    print()
    
    choice = input("Votre choix (1 ou 2) : ").strip()
    if choice == "1":
        run_playwright_stealth()
    elif choice == "2":
        print("\n--- Procédure d'importation des Cookies ---")
        print("1. Ouvrez Chrome ou Firefox et installez l'extension 'Cookie-Editor' ou similaire.")
        print("2. Connectez-vous à votre compte sur https://gensdeconfiance.com/")
        print("3. Cliquez sur l'icône de l'extension 'Cookie-Editor', puis cliquez sur le bouton 'Export' > 'JSON'.")
        print("4. Collez le contenu JSON copié ci-dessous (appuyez sur Entrée puis Ctrl+Z/Ctrl+D pour valider sous Windows/Linux) :")
        print()
        
        print("Collez le JSON ici :")
        lines = []
        try:
            while True:
                line = input()
                lines.append(line)
        except EOFError:
            pass
        
        json_str = "\n".join(lines)
        if json_str.strip():
            save_cookies_from_json(json_str)
        else:
            print("[ERREUR] Aucun contenu saisi.")
    else:
        print("[ERREUR] Choix invalide.")

if __name__ == "__main__":
    main()
