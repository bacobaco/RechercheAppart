"""
Script de connexion Jinka perfectionné et automatisé.
- Détection automatique du Token dans le presse-papiers Windows au lancement.
- Connexion via Chrome réel avec profil persistant et contournement anti-détection Google.
- Détection automatique du token dès la connexion réussie (sans avoir besoin d'ouvrir F12).
- Saisie manuelle directe comme alternative.

Usage: python login_jinka.py [--clipboard] [--status]
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
    """Récupère le texte du presse-papiers sous Windows."""
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
    """Affiche l'état actuel du token Jinka."""
    print("=" * 65)
    print("           État de la connexion Jinka")
    print("=" * 65)
    if not os.path.exists(TOKEN_FILE):
        print("[ÉTAT] Aucun token Jinka n'est configuré (jinka_token.json introuvable).")
        return
        
    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("token")
        if not token:
            print("[ÉTAT] Fichier présent mais token vide.")
            return
            
        info = decode_jwt_info(token)
        if not info:
            print("[ÉTAT] Token présent mais format JWT non reconnu.")
        elif info["valid"]:
            print(f"[ÉTAT] ACTIF - Connecté avec : {info['email']}")
            print(f"[EXPIRATION] Le {info['exp_date_str']} (dans {info['days_left']} jours)")
            test_jinka_api(token)
        else:
            print(f"[ÉTAT] EXPIRÉ depuis le {info['exp_date_str']}")
            print("[ACTION] Renouvelez votre token en relançant: python login_jinka.py")
    except Exception as e:
        print(f"[ERREUR] Lecture impossible : {e}")

def run_playwright_stealth():
    """Lance un navigateur Chrome avec profil persistant et contournement anti-détection Google."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERREUR] Playwright n'est pas installé. Lancez: pip install playwright")
        return False

    print("\nLancement du navigateur Chrome réel avec profil persistant...")
    print("Avantages de ce mode :")
    print("  1. Google Sign-In n'est PAS bloqué (détection anti-bot désactivée).")
    print("  2. Dès que vous vous connectez, le token est DÉTECTÉ AUTOMATIQUEMENT !")
    print("  3. La session est mémorisée sur votre disque pour les futurs renouvellements.")
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
            
            page = context.new_page() if not context.pages else context.pages[0]
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            print("[INFO] Navigation vers Jinka...")
            page.goto("https://www.jinka.fr/connexion", wait_until="domcontentloaded", timeout=30000)
            print("[ATTENTE] Connectez-vous à votre compte Jinka dans la fenêtre ouverte...")
            print("[INFO] Le script vérifie automatiquement la connexion toutes les secondes...\n")
            
            # Boucle de surveillance automatique du token
            detected_token = None
            max_seconds = 180
            start_time = time.time()
            
            while time.time() - start_time < max_seconds:
                try:
                    js_token = page.evaluate(r"""() => {
                        const jwtRegex = /eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/;
                        // 1. localStorage
                        for (let i = 0; i < localStorage.length; i++) {
                            const val = localStorage.getItem(localStorage.key(i));
                            if (typeof val === 'string' && jwtRegex.test(val)) {
                                const match = val.match(jwtRegex);
                                if (match) return match[0];
                            }
                        }
                        // 2. sessionStorage
                        for (let i = 0; i < sessionStorage.length; i++) {
                            const val = sessionStorage.getItem(sessionStorage.key(i));
                            if (typeof val === 'string' && jwtRegex.test(val)) {
                                const match = val.match(jwtRegex);
                                if (match) return match[0];
                            }
                        }
                        return null;
                    }""")
                    
                    if js_token:
                        info = decode_jwt_info(js_token)
                        if info and info["valid"]:
                            detected_token = js_token
                            print(f"\n[DÉTECTION AUTOMATIQUE RÉUSSIE] Token trouvé pour : {info['email']} !")
                            break
                except Exception:
                    pass
                    
                time.sleep(1.5)
                
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

    print("=" * 65)
    print("      Connexion Jinka - Gestion Automatisée de la Session")
    print("=" * 65)
    
    # 1. Vérifier d'abord le presse-papiers automatiquement
    clip_res = extract_jwt_from_text(get_clipboard_text())
    if clip_res:
        token, info = clip_res
        print("\n" + "*" * 65)
        print(f" [DÉTECTION AUTOMATIQUE] Un token valide a été trouvé dans le presse-papiers !")
        print(f"  - Compte      : {info['email']}")
        print(f"  - Expire le   : {info['exp_date_str']} (dans {info['days_left']} jours)")
        print("*" * 65)
        choice = input("\nVoulez-vous sauvegarder ce token directement ? (O/n) [défaut: O] : ").strip().lower()
        if choice in ["o", "oui", "y", "yes", ""]:
            save_manual_token(token)
            return

    print("\nChoisissez une méthode :")
    print("1) Ouvrir le navigateur Chrome sécurisé (Connexion facile, token détecté TOUT SEUL)")
    print("2) Saisir ou coller un Token JWT manuellement")
    print("3) Afficher l'état du token actuel")
    print()
    
    choice = input("Votre choix (1, 2 ou 3) [défaut: 1] : ").strip()
    if choice in ["1", ""]:
        run_playwright_stealth()
    elif choice == "2":
        token = input("\nCollez votre token ici : ").strip()
        if token:
            save_manual_token(token)
    elif choice == "3":
        show_status()
    else:
        print("[ERREUR] Choix invalide.")

if __name__ == "__main__":
    main()
