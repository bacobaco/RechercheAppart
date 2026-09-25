import http.server
import socketserver
import json
import os
import urllib.parse
import subprocess
import threading
import time
from datetime import datetime

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
LOG_FILE = os.path.join(BASE_DIR, "agent.log")

def sync_github_background(commit_msg="Mise à jour des annonces"):
    """Synchronise data.json en arrière-plan sans bloquer la requête HTTP."""
    def _sync():
        try:
            res = subprocess.run(["git", "status", "--porcelain", DATA_FILE], capture_output=True, text=True, cwd=BASE_DIR)
            if res.stdout.strip():
                subprocess.run(["git", "add", DATA_FILE], cwd=BASE_DIR, check=True, capture_output=True)
                subprocess.run(["git", "commit", "-m", commit_msg], cwd=BASE_DIR, check=True, capture_output=True)
                push_res = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True)
                if push_res.returncode == 0:
                    print(f"[GITHUB SYNC] Synchronisé sur GitHub : {commit_msg}")
                else:
                    print(f"[GITHUB SYNC] Erreur push : {push_res.stderr.strip()}")
        except Exception as e:
            print(f"[GITHUB SYNC] Exception : {e}")
    threading.Thread(target=_sync, daemon=True).start()

agent_status = {
    "running": False,
    "last_run": None,
    "message": "Prêt"
}

import sys

def run_agent_task():
    global agent_status
    agent_status["running"] = True
    agent_status["message"] = "Scan en cours..."
    try:
        # Ouvrir le fichier de log en mode écriture (écrase le précédent)
        with open(LOG_FILE, "w", encoding="utf-8") as f_log:
            result = subprocess.run(
                [sys.executable, "-u", os.path.join(BASE_DIR, "agent.py")], # Utilise le même interpréteur Python
                cwd=BASE_DIR,
                stdout=f_log,
                stderr=subprocess.STDOUT,
                text=True
            )
        
        if result.returncode == 0:
            agent_status["last_run"] = datetime.now().strftime("%H:%M:%S")
            agent_status["message"] = "Scan terminé avec succès"
        else:
            agent_status["message"] = "Le scan a rencontré une erreur (voir logs)"
    except Exception as e:
        agent_status["message"] = f"Erreur système: {str(e)}"
    finally:
        agent_status["running"] = False

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.path = "/dashboard.html"
        elif self.path == "/api/data":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode())
            else:
                self.wfile.write(b"[]")
            return
        elif self.path == "/api/agent_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(agent_status).encode())
            return
        elif self.path == "/api/agent_log":
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    # Envoyer les 20 dernières lignes
                    lines = f.readlines()
                    self.wfile.write("".join(lines[-20:]).encode())
            else:
                self.wfile.write(b"Aucun log disponible.")
            return
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/update_status":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            title = params.get("titre")
            url = params.get("lien_annonce")
            new_status = params.get("statut")
            
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                updated = False
                for item in data:
                    if (url and item.get("lien_annonce") == url) or (not url and item.get("titre") == title):
                        item["statut"] = new_status
                        # Enregistrer la date d'élimination pour permettre la purge automatique après 1 mois
                        if new_status in ("Éliminer", "Déjà loué"):
                            if "date_elimination" not in item:
                                item["date_elimination"] = datetime.now().strftime("%Y-%m-%d")
                        else:
                            # Si on remet un autre statut, annuler le compte à rebours de purge
                            item.pop("date_elimination", None)
                        updated = True
                        break
                if updated:
                    with open(DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode())
                    sync_github_background(f"chore: mise à jour statut '{new_status}'")
                    return
        
        elif self.path == "/api/update_notes":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            title = params.get("titre")
            url = params.get("lien_annonce")
            new_notes = params.get("notes")
            
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                updated = False
                for item in data:
                    if (url and item.get("lien_annonce") == url) or (not url and item.get("titre") == title):
                        item["notes"] = new_notes
                        updated = True
                        break
                if updated:
                    with open(DATA_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json")
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode())
                    sync_github_background("chore: mise à jour des notes d'annonce")
                    return
        
        elif self.path == "/api/update_order":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            new_data = json.loads(post_data.decode('utf-8'))
            
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)
            
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success"}).encode())
            sync_github_background("feat: réorganisation manuelle de l'ordre des annonces")
            return
        
        elif self.path == "/api/run_agent":
            global agent_status
            if not agent_status["running"]:
                thread = threading.Thread(target=run_agent_task)
                thread.start()
                self.send_response(202)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "started"}).encode())
            else:
                self.send_response(409)
                self.end_headers()
            return

if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Serveur démarré sur http://localhost:{PORT}")
        print(f"Tableau de bord local : http://localhost:{PORT}/dashboard.html")
        print(f"Tableau de bord en ligne (GitHub Pages) : https://bacobaco.github.io/RechercheAppart/")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            httpd.server_close()
