import http.server
import socketserver
import json
import os
import urllib.parse
import subprocess
import threading
import time
from datetime import datetime
import shutil
import sys

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data.json")
SEARCHES_FILE = os.path.join(BASE_DIR, "searches.json")
LOG_FILE = os.path.join(BASE_DIR, "agent.log")

sync_lock = threading.Lock()

def get_searches_config():
    """Charge la configuration des recherches depuis searches.json."""
    if os.path.exists(SEARCHES_FILE):
        try:
            with open(SEARCHES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERREUR] Lecture de {SEARCHES_FILE}: {e}")
    return {
        "active_search_id": "meuble_1",
        "searches": [
            {
                "id": "meuble_1",
                "name": "Recherche Meublé 1",
                "type": "appartement",
                "enabled": True,
                "data_file": "data.json"
            }
        ]
    }

def get_target_data_file(search_id=None):
    """Détermine le chemin absolu du fichier de données pour un ID de recherche."""
    cfg = get_searches_config()
    target_id = search_id or cfg.get("active_search_id", "meuble_1")
    
    for s in cfg.get("searches", []):
        if s.get("id") == target_id:
            df = s.get("data_file", "data.json")
            return os.path.join(BASE_DIR, df), s
            
    return DATA_FILE, None

def sync_github_background(commit_msg="Mise à jour des annonces"):
    """Synchronise data.json, searches.json et les fichiers de données vers GitHub en arrière-plan."""
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

                files_to_check = [DATA_FILE, SEARCHES_FILE, dash_path, idx_path]
                # Ajouter tous les fichiers de données data_*.json existants
                for f in os.listdir(BASE_DIR):
                    if f.startswith("data_") and f.endswith(".json"):
                        files_to_check.append(os.path.join(BASE_DIR, f))

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
    "current_search": "all",
    "message": "Prêt"
}

def run_agent_task(search_id=None):
    global agent_status
    agent_status["running"] = True
    agent_status["current_search"] = search_id or "all"
    agent_status["message"] = f"Scan en cours ({search_id if search_id else 'toutes les recherches'})..."
    try:
        cmd = [sys.executable, "-u", os.path.join(BASE_DIR, "agent.py")]
        if search_id:
            cmd.extend(["--search", search_id])
            
        with open(LOG_FILE, "w", encoding="utf-8") as f_log:
            result = subprocess.run(
                cmd,
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
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            self.path = "/dashboard.html"
            return super().do_GET()

        elif path == "/api/searches":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            cfg = get_searches_config()
            self.wfile.write(json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8"))
            return

        elif path == "/api/data":
            search_id = query.get("search", [None])[0] or query.get("id", [None])[0]
            target_file, _ = get_target_data_file(search_id)

            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            if os.path.exists(target_file):
                with open(target_file, "r", encoding="utf-8") as f:
                    self.wfile.write(f.read().encode("utf-8"))
            else:
                self.wfile.write(b"[]")
            return

        elif path == "/api/agent_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(json.dumps(agent_status).encode("utf-8"))
            return

        elif path == "/api/agent_log":
            self.send_response(200)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    self.wfile.write("".join(lines[-25:]).encode("utf-8"))
            else:
                self.wfile.write(b"Aucun log disponible.")
            return

        return super().do_GET()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            params = json.loads(post_data.decode('utf-8'))
        except Exception:
            params = {}

        if self.path == "/api/searches":
            # Sauvegarder la nouvelle configuration de searches.json
            with open(SEARCHES_FILE, "w", encoding="utf-8") as f:
                json.dump(params, f, ensure_ascii=False, indent=2)
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "config": params}).encode("utf-8"))
            sync_github_background("feat: mise à jour des paramètres de recherches")
            return

        elif self.path == "/api/update_status":
            search_id = params.get("search") or params.get("search_id")
            target_file, _ = get_target_data_file(search_id)
            title = params.get("titre")
            url = params.get("lien_annonce")
            new_status = params.get("statut")
            
            if os.path.exists(target_file):
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                updated = False
                for item in data:
                    if (url and item.get("lien_annonce") == url) or (not url and item.get("titre") == title):
                        item["statut"] = new_status
                        if new_status in ("Éliminer", "Déjà loué"):
                            if "date_elimination" not in item:
                                item["date_elimination"] = datetime.now().strftime("%Y-%m-%d")
                        else:
                            item.pop("date_elimination", None)
                        updated = True
                        break
                if updated:
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
                    sync_github_background(f"chore: mise à jour statut '{new_status}' ({search_id or 'défaut'})")
                    return
            self.send_response(404)
            self.end_headers()
            return
        
        elif self.path == "/api/update_notes":
            search_id = params.get("search") or params.get("search_id")
            target_file, _ = get_target_data_file(search_id)
            title = params.get("titre")
            url = params.get("lien_annonce")
            new_notes = params.get("notes")
            
            if os.path.exists(target_file):
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                updated = False
                for item in data:
                    if (url and item.get("lien_annonce") == url) or (not url and item.get("titre") == title):
                        item["notes"] = new_notes
                        updated = True
                        break
                if updated:
                    with open(target_file, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=4)
                    self.send_response(200)
                    self.send_header("Content-type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
                    sync_github_background(f"chore: mise à jour des notes ({search_id or 'défaut'})")
                    return
            self.send_response(404)
            self.end_headers()
            return
        
        elif self.path == "/api/update_order":
            search_id = params.get("search") or params.get("search_id")
            target_file, _ = get_target_data_file(search_id)
            new_data = params.get("data") if isinstance(params, dict) and "data" in params else params
            
            if isinstance(new_data, list):
                with open(target_file, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, ensure_ascii=False, indent=4)
                
                self.send_response(200)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success"}).encode("utf-8"))
                sync_github_background(f"feat: réorganisation ordre annonces ({search_id or 'défaut'})")
                return
            self.send_response(400)
            self.end_headers()
            return
        
        elif self.path == "/api/add_listing":
            search_id = params.get("search") or params.get("search_id")
            target_file, profile = get_target_data_file(search_id)
            
            titre = params.get("titre", "").strip()
            if not titre:
                self.send_response(400)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Le titre est obligatoire"}).encode("utf-8"))
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
            
            formatted_prix = prix
            if formatted_prix and "€" not in formatted_prix:
                formatted_prix = f"{formatted_prix} €"
                
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
            
            # Attributs spécifiques au parking
            if params.get("type_parking"):
                new_item["type_parking"] = params.get("type_parking")
            if params.get("distance_cible"):
                new_item["distance_cible"] = params.get("distance_cible")
            if params.get("tesla_compatible"):
                new_item["tesla_compatible"] = params.get("tesla_compatible")
            if params.get("prise_electrique"):
                new_item["prise_electrique"] = params.get("prise_electrique")
            
            data = []
            if os.path.exists(target_file):
                with open(target_file, "r", encoding="utf-8") as f:
                    try:
                        data = json.load(f)
                    except Exception:
                        data = []
            
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
                
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
                
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "listing": new_item}).encode("utf-8"))
            sync_github_background(f"feat: ajout manuel de l'annonce '{titre}' ({search_id or 'défaut'})")
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

                        files_to_sync = [DATA_FILE, SEARCHES_FILE, dash_path, idx_path]
                        for f in os.listdir(BASE_DIR):
                            if f.startswith("data_") and f.endswith(".json"):
                                files_to_sync.append(os.path.join(BASE_DIR, f))

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
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Synchronisation lancée"}).encode("utf-8"))
            return
        
        elif self.path == "/api/run_agent":
            global agent_status
            target_search = params.get("search") if isinstance(params, dict) else None
            if not agent_status["running"]:
                thread = threading.Thread(target=run_agent_task, args=(target_search,))
                thread.start()
                self.send_response(202)
                self.send_header("Content-type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "started", "search": target_search or "all"}).encode("utf-8"))
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
