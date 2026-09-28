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

import shutil

sync_lock = threading.Lock()

def sync_github_background(commit_msg="Mise à jour des annonces"):
    """Synchronise data.json (et fichiers html si modifiés) en arrière-plan sans bloquer la requête HTTP."""
    def _sync():
        with sync_lock:
            try:
                # Assurer la stricte parité entre dashboard.html et index.html
                dash_path = os.path.join(BASE_DIR, "dashboard.html")
                idx_path = os.path.join(BASE_DIR, "index.html")
                if os.path.exists(dash_path) and os.path.exists(idx_path):
                    with open(dash_path, "rb") as f1, open(idx_path, "rb") as f2:
                        if f1.read() != f2.read():
                            shutil.copyfile(dash_path, idx_path)

                files_to_check = [DATA_FILE, dash_path, idx_path]
                res = subprocess.run(["git", "status", "--porcelain"] + files_to_check, capture_output=True, text=True, cwd=BASE_DIR)
                if res.stdout.strip():
                    subprocess.run(["git", "add"] + files_to_check, cwd=BASE_DIR, check=True, capture_output=True)
                    subprocess.run(["git", "commit", "-m", commit_msg], cwd=BASE_DIR, check=True, capture_output=True)
                    push_res = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True)
                    if push_res.returncode == 0:
                        print(f"[GITHUB SYNC] Synchronisé sur GitHub : {commit_msg}")
                    else:
                        print(f"[GITHUB SYNC] Rebase et nouvel essai push ({push_res.stderr.strip()})...")
                        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True)
                        push_retry = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True)
                        if push_retry.returncode == 0:
                            print(f"[GITHUB SYNC] Synchronisé après rebase : {commit_msg}")
                        else:
                            print(f"[GITHUB SYNC] Erreur push persistante : {push_retry.stderr.strip()}")
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
        
        elif self.path == "/api/add_listing":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = json.loads(post_data.decode('utf-8'))
            
            titre = params.get("titre", "").strip()
            if not titre:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Le titre est obligatoire"}).encode())
                return
            
            prix = params.get("prix", "").strip()
            try:
                surface = float(params.get("surface") or 0)
            except (ValueError, TypeError):
                surface = 0.0
                
            try:
                nb_pieces = int(params.get("nb_pieces") or 0)
            except (ValueError, TypeError):
                nb_pieces = 0
                
            quartier = params.get("quartier", "").strip()
            adresse = params.get("adresse_estimee", "").strip()
            lien = params.get("lien_annonce", "").strip()
            source = params.get("source", "Manuel").strip()
            notes = params.get("notes", "").strip()
            statut = params.get("statut", "Nouveau").strip()
            avantages = params.get("avantages", "").strip()
            inconvenients = params.get("inconvenients", "").strip()
            
            # Calcul du prix / m²
            prix_m2 = 0.0
            if surface > 0 and prix:
                clean_p = "".join(c for c in prix.split(",")[0] if c.isdigit())
                if clean_p:
                    try:
                        prix_m2 = round(float(clean_p) / surface, 2)
                    except ZeroDivisionError:
                        pass
            
            # Formatage prix
            formatted_prix = prix
            if formatted_prix and "€" not in formatted_prix:
                formatted_prix = f"{formatted_prix} €"
                
            # Google Street View
            gsv = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(adresse)}" if adresse else ""
            
            new_item = {
                "titre": titre,
                "prix": formatted_prix,
                "surface": surface,
                "nb_pieces": nb_pieces,
                "quartier": quartier,
                "adresse_estimee": adresse,
                "avantages": avantages,
                "inconvenients": inconvenients,
                "prix_m2": prix_m2,
                "source": source or "Manuel",
                "lien_annonce": lien,
                "google_street_view": gsv,
                "date_decouverte": datetime.now().strftime("%Y-%m-%d"),
                "statut": statut,
                "remarques_visite": "",
                "questions_visite": "",
                "notes": notes
            }
            
            data = []
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            
            # Vérifier si l'annonce existe déjà
            existing_idx = -1
            if lien:
                for idx, it in enumerate(data):
                    if it.get("lien_annonce") == lien:
                        existing_idx = idx
                        break
            
            if existing_idx >= 0:
                data[existing_idx].update(new_item)
            else:
                data.insert(0, new_item)
                
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "listing": new_item}).encode())
            sync_github_background(f"feat: ajout manuel de l'annonce '{titre}'")
            return

        elif self.path == "/api/sync_github":
            def _force_sync():
                with sync_lock:
                    try:
                        dash_path = os.path.join(BASE_DIR, "dashboard.html")
                        idx_path = os.path.join(BASE_DIR, "index.html")
                        if os.path.exists(dash_path) and os.path.exists(idx_path):
                            with open(dash_path, "rb") as f1, open(idx_path, "rb") as f2:
                                if f1.read() != f2.read():
                                    shutil.copyfile(dash_path, idx_path)

                        files_to_sync = [DATA_FILE, dash_path, idx_path]
                        subprocess.run(["git", "add"] + files_to_sync, cwd=BASE_DIR, check=True, capture_output=True)
                        subprocess.run(["git", "commit", "-m", "chore: synchronisation manuelle vers GitHub Pages"], cwd=BASE_DIR, capture_output=True)
                        subprocess.run(["git", "pull", "--rebase", "origin", "main"], cwd=BASE_DIR, capture_output=True)
                        push_res = subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, capture_output=True, text=True)
                        print(f"[GITHUB SYNC] Push manuel : {push_res.stdout} {push_res.stderr}")
                    except Exception as e:
                        print(f"[GITHUB SYNC] Erreur push manuel : {e}")

            t = threading.Thread(target=_force_sync, daemon=True)
            t.start()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Synchronisation lancée"}).encode())
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
