"""
Script de connexion Jinka perfectionné et automatisé.
- Correction de l'URL de connexion : https://www.jinka.fr/sign/in
- Détection multi-sources du Token : Cookies (LA_API_TOKEN), Requêtes/Réponses réseau, LocalStorage, SessionStorage.
- Détection automatique du Token dans le presse-papiers Windows au lancement.
- Récupération instantanée depuis la session Chrome persistante si déjà connecté.
- Connexion via Chrome réel avec profil persistant et contournement anti-détection Google.
- Saisie manuelle directe comme alternative.

Usage: python login_jinka.py [--clipboard] [--status] [--session]
"""
import json
import os
import sys
import time
import base64
import re

SESSION_FILE = "jinka_session.json"
TOKEN_FILE = "jinka_token.json"
PROFILE_DIR = os.path.abspath("./.jinka_profile")

def get_clipboard_text():
    """Récupère le texte du presse-papiers sous Windows de manière robuste."""
    # 1. Via ctypes Windows API (direct, pas de dépendance externe)
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

    # 2. Via pyperclip
    try:
        import pyperclip
        text = pyperclip.paste()
        if text and text.strip():
            return text.strip()
    except Exception:
        pass

    # 3. Via tkinter
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

    # 4. Via PowerShell
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

def decode_jwt_info(token):
    """Décode les informations d'expiration et d'utilisateur d'un JWT Jinka."""
    if not token or not isinstance(token, str):
        return None
    try:
        parts = token.strip().split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        exp = payload.get("exp", 0)
        email = payload.get("email", "Inconnu")
        user_id = payload.get("id", "Inconnu")
        now = time.time()
        days_left = (exp - now) / 86400
        is_valid = exp > now
        exp_date_str = time.strftime("%d/%m/%Y à %H:%M", time.localtime(exp))
        return {
            "valid": is_valid,
            "email": email,
            "id": user_id,
            "exp": exp,
            "exp_date_str": exp_date_str,
            "days_left": round(days_left, 1)
        }
    except Exception:
        return None

def extract_jwt_from_text(text):
    """Extrait le premier token JWT valide d'un texte."""
    if not text:
        return None
    matches = re.findall(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', text)
    for m in matches:
        info = decode_jwt_info(m)
        if info and info["valid"]:
            return m, info
    return None

def extract_token_from_session_file(session_file=SESSION_FILE):
    """Extrait le token JWT du fichier de session jinka_session.json (cookie LA_API_TOKEN)."""
    if not os.path.exists(session_file):
        return None
    try:
        with open(session_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data.get("cookies", []):
            val = c.get("value", "")
            name = c.get("name", "")
            if name == "LA_API_TOKEN" or (val and val.startswith("eyJ") and len(val) > 50):
                info = decode_jwt_info(val)
                if info and info["valid"]:
                    return val, info
    except Exception:
        pass
    return None

def extract_token_from_profile_cookies(profile_dir=PROFILE_DIR):
    """Tente de lire directement le cookie LA_API_TOKEN depuis le profil Chrome persistant."""
    if not os.path.exists(profile_dir):
        return None
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=True,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"]
            )
            cookies = ctx.cookies()
            ctx.close()
            for c in cookies:
                val = c.get("value", "")
                name = c.get("name", "")
                if name == "LA_API_TOKEN" or (val and val.startswith("eyJ") and len(val) > 50):
                    info = decode_jwt_info(val)
                    if info and info["valid"]:
                        return val, info
    except Exception:
        pass
    return None

def save_manual_token(token):
    """Enregistre le token dans jinka_token.json et vérifie sa validité auprès de l'API."""
    token = token.strip()
    if token.startswith(('"', "'")) and token.endswith(('"', "'")):
        token = token[1:-1].strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
        
    if not token:
        print("[ERREUR] Le token ne peut pas être vide.")
        return False
        
    info = decode_jwt_info(token)
    if not info:
        print("[WARN] Le texte fourni ne semble pas être un token JWT valide.")
    elif not info["valid"]:
        print(f"[ERREUR] Ce token a expiré le {info['exp_date_str']} !")
        return False
    else:
        print(f"[OK] Token valide pour : {info['email']} (expire le {info['exp_date_str']}, dans {info['days_left']} jours)")
        
    session_data = {
        "cookies": [],
        "token": token,
        "storage_state_file": SESSION_FILE,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
        
    print(f"[SUCCÈS] Token Jinka sauvegardé dans '{TOKEN_FILE}' !")
    
    # Tester immédiatement l'API Jinka
    test_jinka_api(token)
    return True

def test_jinka_api(token):
    """Vérifie immédiatement la connexion avec l'API Jinka."""
    try:
        try:
            from curl_cffi import requests as test_requests
            r = test_requests.get("https://api.jinka.fr/apiv2/alert", headers={"Authorization": f"Bearer {token}"}, impersonate="chrome120", timeout=10)
        except ImportError:
            import requests as test_requests
            r = test_requests.get("https://api.jinka.fr/apiv2/alert", headers={"Authorization": f"Bearer {token}"}, timeout=10)
            
        if r.status_code == 200:
            alerts = r.json()
            print(f"[TEST API OK] Accès Jinka confirmé ! {len(alerts)} alerte(s) active(s) détectée(s).")
            for a in alerts:
                name = a.get("user_name") or a.get("name") or "Alerte"
                print(f"  - Alerte : '{name}' (ID: {a.get('id')})")
            return True
        else:
            print(f"[WARN] L'API Jinka a renvoyé le statut HTTP {r.status_code}.")
            return False
    except Exception as e:
        print(f"[WARN] Impossible de tester l'API Jinka : {e}")
        return False

def show_status():
    """Affiche l'état actuel du token Jinka avec vérification et auto-récupération."""
    print("=" * 65)
    print("           État de la connexion Jinka")
    print("=" * 65)
    
    current_token_valid = False
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            token = data.get("token")
            if token:
                info = decode_jwt_info(token)
                if not info:
                    print("[ÉTAT] Token présent mais format JWT non reconnu.")
                elif info["valid"]:
                    print(f"[ÉTAT] ACTIF - Connecté avec : {info['email']}")
                    print(f"[EXPIRATION] Le {info['exp_date_str']} (dans {info['days_left']} jours)")
                    test_jinka_api(token)
                    current_token_valid = True
                else:
                    print(f"[ÉTAT] EXPIRÉ depuis le {info['exp_date_str']}")
            else:
                print("[ÉTAT] Fichier jinka_token.json présent mais sans token.")
        except Exception as e:
            print(f"[ERREUR] Lecture de {TOKEN_FILE} impossible : {e}")
    else:
        print("[ÉTAT] Aucun token Jinka n'est configuré (jinka_token.json introuvable).")

    if not current_token_valid:
        # Vérifier si un token valide existe dans jinka_session.json ou le profil
        session_res = extract_token_from_session_file()
        if session_res:
            s_token, s_info = session_res
            print("\n[RÉCUPÉRATION POSSIBLE] Un token valide a été trouvé dans 'jinka_session.json' !")
            print(f"  - Compte    : {s_info['email']}")
            print(f"  - Expire le : {s_info['exp_date_str']} (dans {s_info['days_left']} jours)")
            print("[ACTION] Sauvegarde automatique du token récupéré...")
            save_manual_token(s_token)
            return

        print("\n[ACTION] Renouvelez votre token en relançant : python login_jinka.py")

def run_playwright_stealth():
    """Lance un navigateur Chrome avec profil persistant et interception multi-sources du token."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERREUR] Playwright n'est pas installé. Lancez : pip install playwright")
        return False

    print("\nLancement du navigateur Chrome réel avec profil persistant...")
    print("Points forts :")
    print("  1. URL correcte : https://www.jinka.fr/sign/in")
    print("  2. Google Sign-In débloqué (détection anti-bot désactivée).")
    print("  3. Interception multi-sources du token (Cookies LA_API_TOKEN, Réseau, LocalStorage).")
    print("  4. Capture instantanée dès que la connexion réussit.")
    print()

    try:
        with sync_playwright() as p:
            # Persistent context pour retenir les identifiants
            context = p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ],
                viewport=None
            )
            
            detected_token = None

            def check_and_set_token(text):
                nonlocal detected_token
                if detected_token or not text or not isinstance(text, str):
                    return
                matches = re.findall(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', text)
                for m in matches:
                    info = decode_jwt_info(m)
                    if info and info["valid"]:
                        detected_token = m
                        print(f"\n[INTERCEPTION RÉSEAU RÉUSSIE] Token JWT capturé pour : {info['email']} !")
                        return

            # Écoute des requêtes réseau pour intercepter les headers Authorization
            def on_request(request):
                nonlocal detected_token
                if detected_token:
                    return
                try:
                    auth = request.headers.get("authorization", "")
                    if auth:
                        check_and_set_token(auth)
                    cookie_header = request.headers.get("cookie", "")
                    if "LA_API_TOKEN" in cookie_header:
                        check_and_set_token(cookie_header)
                except Exception:
                    pass

            # Écoute des réponses réseau pour intercepter Set-Cookie ou payload JSON
            def on_response(response):
                nonlocal detected_token
                if detected_token:
                    return
                try:
                    set_cookie = response.headers.get("set-cookie", "")
                    if "LA_API_TOKEN" in set_cookie:
                        check_and_set_token(set_cookie)
                except Exception:
                    pass

            context.on("request", on_request)
            context.on("response", on_response)

            def inspect_all_cookies():
                try:
                    for c in context.cookies():
                        val = c.get("value", "")
                        name = c.get("name", "")
                        if name == "LA_API_TOKEN" or (val and val.startswith("eyJ") and len(val) > 50):
                            info = decode_jwt_info(val)
                            if info and info["valid"]:
                                return val, info
                except Exception:
                    pass
                return None

            # Vérification préalable : est-on déjà connecté dans le profil ?
            pre_check = inspect_all_cookies()
            if pre_check:
                val, info = pre_check
                detected_token = val
                print(f"[DÉTECTION IMMÉDIATE] Session déjà active pour : {info['email']} (expire le {info['exp_date_str']}) !")
            
            page = context.new_page() if not context.pages else context.pages[0]
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            if not detected_token:
                # URL de connexion officielle Jinka (et non /connexion qui est un 404)
                login_url = "https://www.jinka.fr/sign/in"
                print(f"[INFO] Navigation vers Jinka ({login_url})...")
                try:
                    page.goto(login_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    print(f"[WARN] Chargement de la page : {e}")
                    
                print("[ATTENTE] Connectez-vous à votre compte Jinka dans la fenêtre Chrome...")
                print("[INFO] Détection automatique en cours (Cookies, Stockage local, Requêtes)...\n")
                
                # Boucle de surveillance automatique du token
                max_seconds = 180
                start_time = time.time()
                
                while time.time() - start_time < max_seconds:
                    if detected_token:
                        break
                        
                    # 1. Vérifier les cookies du contexte (tous onglets / popups confondus)
                    cookie_res = inspect_all_cookies()
                    if cookie_res:
                        detected_token = cookie_res[0]
                        print(f"\n[DÉTECTION COOKIE RÉUSSIE] Cookie 'LA_API_TOKEN' détecté pour : {cookie_res[1]['email']} !")
                        break

                    # 2. Vérifier document.cookie et le localStorage / sessionStorage
                    try:
                        js_token = page.evaluate(r"""() => {
                            const jwtRegex = /eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/;
                            // a. document.cookie
                            try {
                                const cookies = document.cookie.split(';');
                                for (let c of cookies) {
                                    const idx = c.indexOf('=');
                                    if (idx > -1) {
                                        const name = c.substring(0, idx).trim();
                                        const val = c.substring(idx + 1).trim();
                                        if (name === 'LA_API_TOKEN' || jwtRegex.test(val)) {
                                            const match = val.match(jwtRegex);
                                            if (match) return match[0];
                                        }
                                    }
                                }
                            } catch(e) {}
                            // b. localStorage
                            try {
                                for (let i = 0; i < localStorage.length; i++) {
                                    const val = localStorage.getItem(localStorage.key(i));
                                    if (typeof val === 'string' && jwtRegex.test(val)) {
                                        const match = val.match(jwtRegex);
                                        if (match) return match[0];
                                    }
                                }
                            } catch(e) {}
                            // c. sessionStorage
                            try {
                                for (let i = 0; i < sessionStorage.length; i++) {
                                    const val = sessionStorage.getItem(sessionStorage.key(i));
                                    if (typeof val === 'string' && jwtRegex.test(val)) {
                                        const match = val.match(jwtRegex);
                                        if (match) return match[0];
                                    }
                                }
                            } catch(e) {}
                            return null;
                        }""")
                        
                        if js_token:
                            info = decode_jwt_info(js_token)
                            if info and info["valid"]:
                                detected_token = js_token
                                print(f"\n[DÉTECTION DOM/STORAGE RÉUSSIE] Token trouvé pour : {info['email']} !")
                                break
                    except Exception:
                        pass
                        
                    time.sleep(1.0)
                
            # Sauvegarder cookies & state
            try:
                context.storage_state(path=SESSION_FILE)
            except Exception:
                pass
                
            context.close()
            
            if detected_token:
                save_manual_token(detected_token)
                return True
            else:
                print("\n[INFO] Aucun token capturé automatiquement dans le temps imparti.")
                print("Si vous vous êtes connecté, collez le token ci-dessous.")
                manual = input("Collez votre token (ou Entrée pour annuler) : ").strip()
                if manual:
                    return save_manual_token(manual)
                return False
                
    except Exception as e:
        print(f"[ERREUR] Échec du navigateur Playwright : {e}")
        print("[ASTUCE] Utilisez l'option presse-papiers ou saisie manuelle.")
        return False

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1].strip()
        if arg in ["--status", "-s"]:
            show_status()
            return
        elif arg in ["--clipboard", "-c"]:
            clip_res = extract_jwt_from_text(get_clipboard_text())
            if clip_res:
                token, info = clip_res
                save_manual_token(token)
            else:
                print("[ERREUR] Aucun token JWT valide trouvé dans le presse-papiers.")
            return
        elif arg in ["--session"]:
            s_res = extract_token_from_session_file()
            if s_res:
                token, info = s_res
                save_manual_token(token)
            else:
                print("[ERREUR] Aucun token valide trouvé dans 'jinka_session.json'.")
            return

    print("=" * 65)
    print("      Connexion Jinka - Gestion Automatisée de la Session")
    print("=" * 65)
    
    # 1. Vérifier d'abord le presse-papiers automatiquement
    clip_res = extract_jwt_from_text(get_clipboard_text())
    if clip_res:
        token, info = clip_res
        print("\n" + "*" * 65)
        print(f" [DÉTECTION PRESSE-PAPIERS] Un token valide a été trouvé !")
        print(f"  - Compte      : {info['email']}")
        print(f"  - Expire le   : {info['exp_date_str']} (dans {info['days_left']} jours)")
        print("*" * 65)
        choice = input("\nVoulez-vous sauvegarder ce token directement ? (O/n) [défaut: O] : ").strip().lower()
        if choice in ["o", "oui", "y", "yes", ""]:
            save_manual_token(token)
            return

    # 2. Vérifier si un token valide existe dans la session ou le profil persistant
    session_res = extract_token_from_session_file()
    if session_res:
        token, info = session_res
        print("\n" + "*" * 65)
        print(f" [DÉTECTION SESSION] Un token actif est présent dans votre session existante !")
        print(f"  - Compte      : {info['email']}")
        print(f"  - Expire le   : {info['exp_date_str']} (dans {info['days_left']} jours)")
        print("*" * 65)
        choice = input("\nVoulez-vous réactiver ce token directement ? (O/n) [défaut: O] : ").strip().lower()
        if choice in ["o", "oui", "y", "yes", ""]:
            save_manual_token(token)
            return

    print("\nChoisissez une méthode :")
    print("1) Ouvrir le navigateur Chrome sécurisé (Connexion facile, token détecté TOUT SEUL)")
    print("2) Récupérer le token depuis le profil Chrome persistant (si déjà connecté)")
    print("3) Saisir ou coller un Token JWT manuellement")
    print("4) Afficher l'état du token actuel")
    print()
    
    choice = input("Votre choix (1, 2, 3 ou 4) [défaut: 1] : ").strip()
    if choice in ["1", ""]:
        run_playwright_stealth()
    elif choice == "2":
        prof_res = extract_token_from_profile_cookies()
        if prof_res:
            token, info = prof_res
            save_manual_token(token)
        else:
            print("[INFO] Aucun token actif trouvé dans le profil Chrome. Lancez le choix 1.")
    elif choice == "3":
        token = input("\nCollez votre token ici : ").strip()
        if token:
            save_manual_token(token)
    elif choice == "4":
        show_status()
    else:
        print("[ERREUR] Choix invalide.")

if __name__ == "__main__":
    main()
