"""One-command local launcher for the ORI AI application."""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

def ensure_frontend_dependencies() -> None:
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").exists():
        print("[launcher] Frontend dependencies not found; running npm install...")
        subprocess.run(["npm.cmd" if os.name == "nt" else "npm", "install"], cwd=frontend, check=True)

def start_frontend() -> subprocess.Popen | None:
    if not (ROOT / "frontend" / "package.json").exists():
        print("[launcher] React frontend not found; skipping frontend.")
        return None
    try:
        ensure_frontend_dependencies()
        port = os.getenv("FRONTEND_PORT", "5173")
        command = ["npm.cmd" if os.name == "nt" else "npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", port]
        return subprocess.Popen(command, cwd=ROOT / "frontend")
    except FileNotFoundError:
        print("[launcher] Node.js/npm not installed. Install Node.js 20+ to launch React.")
        return None
    except subprocess.CalledProcessError as exc:
        print(f"[launcher] npm install failed: {exc}")
        return None

def main() -> None:
    from backend.app import app
    from backend.training import training_worker

    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    frontend_port = os.getenv("FRONTEND_PORT", "5173")

    # Keep the background trainer independent of browser requests.
    worker = threading.Thread(target=training_worker, name="mongo-training-worker", daemon=True)
    worker.start()

    frontend_process = start_frontend()

    from werkzeug.serving import make_server
    server = make_server(host, port, app, threaded=True)
    api_thread = threading.Thread(target=server.serve_forever, name="flask-api", daemon=True)
    api_thread.start()

    print("\\n[ORI AI] Services started.")
    print(f"[ORI AI] API:      http://{host}:{port}")
    if frontend_process:
        print(f"[ORI AI] Frontend: http://127.0.0.1:{frontend_port}")
        time.sleep(2)
        try:
            webbrowser.open(f"http://127.0.0.1:{frontend_port}")
        except Exception:
            pass
    print("[ORI AI] Press Ctrl+C to stop all services.\\n")

    try:
        while True:
            if frontend_process and frontend_process.poll() is not None:
                print("[launcher] React frontend exited.")
                frontend_process = None
            time.sleep(1)
    except KeyboardInterrupt:
        print("\\n[ORI AI] Shutting down...")
    finally:
        server.shutdown()
        if frontend_process and frontend_process.poll() is None:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                frontend_process.kill()

if __name__ == "__main__":
    main()
