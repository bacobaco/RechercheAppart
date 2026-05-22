"""
Script de connexion Jinka.
Permet d'ouvrir un navigateur automatique OU de renseigner manuellement
le token d'authentification si Google bloque la connexion automatisée.

Usage: python login_jinka.py
"""
import json
import os
import sys

SESSION_FILE = "jinka_session.json"
TOKEN_FILE = "jinka_token.json"

def save_manual_token(token):
    token = token.strip()
    # Supprimer les guillemets éventuels autour du token collé
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
        
    if not token:
        print("[ERREUR] Le token ne peut pas être vide.")
        return False
    
    # Supprimer le préfixe "Bearer " si présent
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
        
    session_data = {
        "cookies": [],
        "token": token,
        "storage_state_file": SESSION_FILE
    }
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] Token sauvegardé avec succès dans {TOKEN_FILE} !")
    return True

def run_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERREUR] Playwright n'est pas installé. Lancez: pip install playwright && playwright install chromium")
        return False

    print("\nUn navigateur Chromium va s'ouvrir sur la page de connexion Jinka.")
    print("Connectez-vous à votre compte.")
    print("Une fois connecté et sur le tableau de bord Jinka,")
    print("revenez ici et appuyez sur Entrée.")
    print()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--start-maximized"]
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Aller sur la page de connexion Jinka
            page.goto("https://www.jinka.fr/connexion", wait_until="networkidle", timeout=30000)

            print("[INFO] Le navigateur est ouvert sur jinka.fr/connexion")
            print("[INFO] Connectez-vous, puis revenez ici et appuyez sur Entrée...")
            print()
            input(">>> Appuyez sur Entrée une fois connecté sur le dashboard Jinka... ")

            cookies = context.cookies()
            storage = context.storage_state()

            # Extraire le token du localStorage
            token = None
            for origin_data in storage.get("origins", []):
                for item in origin_data.get("localStorage", []):
                    if "token" in item.get("name", "").lower() or "auth" in item.get("name", "").lower():
                        token = item.get("value")
                        break

            # Essayer via JavaScript si non trouvé
            if not token:
                try:
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
                except Exception:
                    pass

            # Sauvegarder la session Playwright
            context.storage_state(path=SESSION_FILE)

            # Sauvegarder le token
            session_data = {
                "cookies": cookies,
                "token": token,
                "storage_state_file": SESSION_FILE
            }
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

            browser.close()

        if token:
            print(f"\n[OK] Session sauvegardée dans {SESSION_FILE}")
            print(f"[OK] Token sauvegardé dans {TOKEN_FILE}")
            print("[OK] L'agent est prêt à scanner !")
            return True
        else:
            print(f"\n[OK] Session sauvegardée dans {SESSION_FILE}")
            print("[WARN] Token d'accès direct non trouvé, mais les cookies de session devraient suffire.")
            return True
    except Exception as e:
        print(f"[ERREUR] Une erreur est survenue lors de l'exécution de Playwright : {e}")
        return False

def main():
    print("=" * 60)
    print("  Connexion Jinka - Gestion de la session")
    print("=" * 60)
    print()
    print("Comme Google bloque souvent les connexions sur les navigateurs automatisés,")
    print("vous pouvez soit tenter la connexion Playwright, soit coller directement")
    print("le token récupéré depuis votre propre navigateur.")
    print()
    print("1) Tenter la connexion automatique (Playwright)")
    print("2) Saisir le Token d'authentification manuellement (Recommandé si Google bloque)")
    print()
    
    choice = input("Votre choix (1 ou 2) : ").strip()
    if choice == "1":
        run_playwright()
    elif choice == "2":
        print("\n--- Récupération du Token manuellement ---")
        print("1. Ouvrez Jinka.fr sur votre navigateur habituel (Chrome, Firefox, etc.) et connectez-vous.")
        print("2. Appuyez sur F12 (Inspecter) -> allez dans l'onglet 'Console'.")
        print("3. Collez ce code ci-dessous et appuyez sur Entrée :")
        print()
        print("   (() => {")
        print("     const jwtRegex = /eyJ[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+\\.[a-zA-Z0-9_-]+/g;")
        print("     const tokens = [];")
        print("     const checkValue = (val) => {")
        print("       if (typeof val !== 'string') return;")
        print("       const matches = val.match(jwtRegex);")
        print("       if (matches) {")
        print("         matches.forEach(m => { if (!tokens.includes(m)) tokens.push(m); });")
        print("       }")
        print("       try {")
        print("         const parsed = JSON.parse(val);")
        print("         if (parsed && typeof parsed === 'object') {")
        print("           Object.values(parsed).forEach(v => checkValue(typeof v === 'string' ? v : JSON.stringify(v)));")
        print("         }")
        print("       } catch(e) {}")
        print("     };")
        print("     for (let i = 0; i < localStorage.length; i++) { checkValue(localStorage.getItem(localStorage.key(i))); }")
        print("     for (let i = 0; i < sessionStorage.length; i++) { checkValue(sessionStorage.getItem(sessionStorage.key(i))); }")
        print("     checkValue(document.cookie);")
        print("     if (tokens.length > 0) {")
        print("       console.log('\\n--- VOTRE TOKEN DE CONNEXION ---');")
        print("       console.log(tokens[0]);")
        print("       try { copy(tokens[0]); console.log('(Copié automatiquement dans votre presse-papiers !)'); } catch(e){}")
        print("     } else {")
        print("       console.log('Aucun token d\\'authentification trouvé. Êtes-vous connecté sur Jinka ?');")
        print("     }")
        print("   })();")
        print()
        token = input("Collez votre token ici : ").strip()
        save_manual_token(token)
    else:
        print("[ERREUR] Choix invalide.")

if __name__ == "__main__":
    main()
