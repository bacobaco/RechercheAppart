"""
Script de connexion Gens de Confiance perfectionné.
- Détection automatique des cookies dans le presse-papiers au lancement.
- Importation directe depuis cookies_gdc.json ou presse-papiers.
- Test immédiat de la connexion via curl_cffi pour valider le contournement Cloudflare.
- Mémorisation de la session dans gdc_session.json.

Usage: python login_gdc.py [--status] [--clipboard]
"""
import json
import os
import sys
import time

SESSION_FILE = "gdc_session.json"
URL_FILE = "gdc_url.json"
DEFAULT_COOKIES_FILE = "cookies_gdc.json"

def get_clipboard_text():
    """Tente de récupérer le texte du presse-papiers sous Windows."""
    try:
        import pyperclip
        text = pyperclip.paste()
        if text and text.strip():
            return text.strip()
    except Exception:
        pass

    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        if text and text.strip():
            return text.strip()
    except Exception:
        pass

    try:
        import ctypes
        CF_UNICODETEXT = 13
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if user32.OpenClipboard(None):
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if handle:
                    kernel32.GlobalLock.restype = ctypes.c_void_p
                    ptr = kernel32.GlobalLock(handle)
                    if ptr:
                        try:
                            val = ctypes.c_wchar_p(ptr).value
                            if val and val.strip():
                                return val.strip()
                        finally:
                            kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
    except Exception:
        pass

    try:
        import subprocess
        res = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, encoding="utf-8"
        )
        if res.stdout and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass

    return None

def test_gdc_connection():
    """Teste immédiatement la validité des cookies avec curl_cffi."""
    if not os.path.exists(SESSION_FILE):
        return False
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = {c["name"]: c["value"] for c in data.get("cookies", []) if "name" in c and "value" in c}
        
        from curl_cffi import requests as curl_requests
        url = "https://gensdeconfiance.com/fr/s/immobilier/locations-immobilieres?type=offering&rootLocales=fr%2Cen&currentAdSort=displayDate_desc"
        r = curl_requests.get(url, impersonate="chrome120", cookies=cookies, timeout=15)
        
        if r.status_code == 200 and "Just a moment" not in r.text:
            # Check for ad items in Next.js data
            import re
            has_ads = "/ui/post/" in r.text or "/annonce/" in r.text or "__NEXT_DATA__" in r.text
            print(f"[TEST CONNEXION OK] Statut HTTP 200 - Accès Gens de Confiance validé sans blocage Cloudflare !")
            return True
        elif r.status_code == 403 or "Just a moment" in r.text:
            print(f"[WARN] Cloudflare a renvoyé un challenge (statut {r.status_code}).")
            return False
        else:
            print(f"[WARN] Statut inhabituel: HTTP {r.status_code}")
            return False
    except ImportError:
        print("[INFO] curl_cffi non disponible pour le test direct.")
        return True
    except Exception as e:
        print(f"[WARN] Erreur lors du test de connexion: {e}")
        return False

def show_status():
    """Affiche l'état des cookies actuels."""
    print("=" * 65)
    print("        État de la session Gens de Confiance")
    print("=" * 65)
    if not os.path.exists(SESSION_FILE):
        print(f"[ÉTAT] Aucune session configurée ({SESSION_FILE} introuvable).")
        return
        
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cookies = data.get("cookies", [])
        print(f"[INFO] {len(cookies)} cookies enregistrés dans '{SESSION_FILE}'.")
        now = time.time()
        for c in cookies:
            name = c.get("name", "")
            exp = c.get("expires", -1)
            if name in ["accounts_session", "session", "ory_kratos_continuity", "__cf_bm"]:
                if exp > 0:
                    exp_str = time.strftime("%d/%m/%Y à %H:%M", time.localtime(exp))
                    days_left = round((exp - now) / 86400, 1)
                    status_txt = f"valide encore {days_left} jours" if exp > now else "EXPIRÉ"
                    print(f"  - {name:<22}: {exp_str} ({status_txt})")
                else:
                    print(f"  - {name:<22}: Session active")
        print("\nTest de connexion en cours...")
        test_gdc_connection()
    except Exception as e:
        print(f"[ERREUR] Lecture impossible : {e}")

def save_cookies_from_json(json_str):
    try:
        json_str = json_str.strip()
        cookies_list = json.loads(json_str)
        if not isinstance(cookies_list, list):
            if isinstance(cookies_list, dict) and "cookies" in cookies_list:
                cookies_list = cookies_list["cookies"]
            else:
                print("[ERREUR] Le format JSON doit être une liste de cookies [...] ou un objet storageState.")
                return False
                
        playwright_cookies = []
        for c in cookies_list:
            name = c.get("name")
            value = c.get("value")
            if not name or value is None:
                continue
                
            raw_same_site = str(c.get("sameSite", "")).lower().strip()
            if "strict" in raw_same_site:
                same_site = "Strict"
            elif "none" in raw_same_site or "no_restriction" in raw_same_site:
                same_site = "None"
            else:
                same_site = "Lax"
                
            expires = c.get("expirationDate") or c.get("expires")
            if expires is not None:
                try:
                    expires = int(float(expires))
                except Exception:
                    expires = -1
            else:
                expires = -1
                
            domain = c.get("domain", ".gensdeconfiance.com")
            
            playwright_cookie = {
                "name": str(name),
                "value": str(value),
                "domain": str(domain),
                "path": str(c.get("path", "/")),
                "expires": expires,
                "httpOnly": bool(c.get("httpOnly", False)),
                "secure": bool(c.get("secure", False)),
                "sameSite": same_site
            }
            playwright_cookies.append(playwright_cookie)
            
        if not playwright_cookies:
            print("[ERREUR] Aucun cookie valide trouvé dans le JSON fourni.")
            return False

        storage_state = {
            "cookies": playwright_cookies,
            "origins": []
        }
        
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(storage_state, f, ensure_ascii=False, indent=2)
            
        default_url = "https://gensdeconfiance.com/fr/s/immobilier/locations-immobilieres?type=offering&rootLocales=fr%2Cen&currentAdSort=displayDate_desc"
        with open(URL_FILE, "w", encoding="utf-8") as f_url:
            json.dump({"search_url": default_url}, f_url, ensure_ascii=False, indent=2)
            
        print(f"\n[SUCCÈS] {len(playwright_cookies)} cookies sauvegardés avec succès dans '{SESSION_FILE}' !")
        test_gdc_connection()
        return True
    except Exception as e:
        print(f"[ERREUR] Impossible de décoder le JSON : {e}")
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
            browser = p.chromium.launch(
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ]
            )
            
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
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            page.goto("https://gensdeconfiance.com/fr/s/immobilier/locations-immobilieres", wait_until="domcontentloaded", timeout=45000)
            
            input(">>> Appuyez sur Entrée une fois connecté et la recherche Lyon affichée... ")
            
            context.storage_state(path=SESSION_FILE)
            search_url = page.url
            with open(URL_FILE, "w", encoding="utf-8") as f:
                json.dump({"search_url": search_url}, f, ensure_ascii=False, indent=2)
                
            print(f"\n[OK] Session sauvegardée dans {SESSION_FILE}")
            print(f"[OK] URL de recherche sauvegardée : {search_url}")
            browser.close()
            test_gdc_connection()
            return True
    except Exception as e:
        print(f"[ERREUR] Échec de la connexion automatique Playwright Stealth : {e}")
        return False

def import_from_file(filepath=DEFAULT_COOKIES_FILE):
    if not os.path.exists(filepath):
        print(f"[ERREUR] Fichier introuvable : '{filepath}'")
        print(f"[CONSEIL] Créez ou ouvrez le fichier '{filepath}' dans VS Code, collez-y les cookies exportés et sauvegardez.")
        return False
        
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"[INFO] Lecture du fichier '{filepath}' ({len(content)} octets)...")
        return save_cookies_from_json(content)
    except Exception as e:
        print(f"[ERREUR] Lecture impossible du fichier '{filepath}' : {e}")
        return False

def import_from_clipboard():
    print("[INFO] Lecture du presse-papiers...")
    text = get_clipboard_text()
    if not text:
        print("[ERREUR] Aucun texte trouvé dans le presse-papiers.")
        return False
        
    if not (text.strip().startswith("[") or text.strip().startswith("{")):
        print(f"[ERREUR] Le presse-papiers ne contient pas de JSON (début: {text[:60]!r}...)")
        return False
        
    return save_cookies_from_json(text)

def read_console_paste():
    print("\n--- Saisie console ---")
    print("Collez le JSON ici.")
    print("Astuce : La fin sera détectée AUTOMATIQUEMENT dès que le crochet final ']' est collé.")
    print("Vous pouvez aussi appuyer sur Entrée deux fois de suite ou taper 'FIN'.\n")
    
    lines = []
    while True:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
            
        stripped = line.strip()
        if stripped.upper() == "FIN":
            break
            
        lines.append(line)
        joined = "\n".join(lines).strip()
        
        if stripped.endswith("]") or stripped.endswith("}"):
            try:
                json.loads(joined)
                print("\n[INFO] Fin du JSON détectée automatiquement !")
                break
            except Exception:
                pass
                
        if stripped == "" and len(lines) > 2:
            try:
                json.loads(joined)
                print("\n[INFO] Fin du JSON validée.")
                break
            except Exception:
                pass

    joined = "\n".join(lines).strip()
    if not joined:
        print("[ERREUR] Aucun texte reçu.")
        return False
    return save_cookies_from_json(joined)

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ["--status", "-s"]:
            show_status()
            return
        elif arg in ["--clipboard", "-c", "clip"]:
            import_from_clipboard()
            return
        elif os.path.isfile(arg):
            import_from_file(arg)
            return

    print("=" * 65)
    print("     Connexion Gens de Confiance - Gestion de la session")
    print("=" * 65)
    
    # Vérification automatique du presse-papiers au lancement
    clip_text = get_clipboard_text()
    if clip_text and (clip_text.strip().startswith("[") or clip_text.strip().startswith("{")) and "gensdeconfiance" in clip_text.lower():
        print("\n" + "*" * 65)
        print(" [DÉTECTION AUTOMATIQUE] Des cookies Gens de Confiance ont été détectés dans le presse-papiers !")
        print("*" * 65)
        choice = input("\nVoulez-vous les importer directement ? (O/n) [défaut: O] : ").strip().lower()
        if choice in ["o", "oui", "y", "yes", ""]:
            save_cookies_from_json(clip_text)
            return
    
    has_file = os.path.exists(DEFAULT_COOKIES_FILE)
    file_info = f" (Fichier '{DEFAULT_COOKIES_FILE}' trouvé dans le dossier)" if has_file else f" (Collez dans '{DEFAULT_COOKIES_FILE}' dans VS Code)"
    
    print("\nChoisissez la méthode d'importation :")
    print(f"1) Importer depuis le fichier '{DEFAULT_COOKIES_FILE}' [Recommandé]{file_info}")
    print("2) Importer directement depuis le presse-papiers Windows (1 clic après 'Export JSON')")
    print("3) Coller le JSON dans la console (détection de fin automatique)")
    print("4) Tenter la connexion automatique (Playwright Stealth avec Chrome)")
    print("5) Afficher l'état de la session et tester la connexion")
    print()
    
    choice = input("Votre choix (1, 2, 3, 4 ou 5) [défaut: 1] : ").strip()
    if choice in ["1", ""]:
        import_from_file(DEFAULT_COOKIES_FILE)
    elif choice == "2":
        import_from_clipboard()
    elif choice == "3":
        read_console_paste()
    elif choice == "4":
        run_playwright_stealth()
    elif choice == "5":
        show_status()
    else:
        print("[ERREUR] Choix invalide.")

if __name__ == "__main__":
    main()
