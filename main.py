"""One-command local launcher for the ORI AI application."""
from __future__ import annotations

import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def _npm_command() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def ensure_frontend_dependencies() -> None:
    frontend = ROOT / "frontend"
    if not (frontend / "node_modules").exists():
        print("[launcher] Frontend dependencies not found; running npm install...")
        subprocess.run([_npm_command(), "install"], cwd=frontend, check=True)


def start_frontend() -> subprocess.Popen | None:
    frontend = ROOT / "frontend"
    if not (frontend / "package.json").exists():
        print("[launcher] React frontend not found; skipping frontend.")
        return None
    try:
        ensure_frontend_dependencies()
        port = os.getenv("FRONTEND_PORT", "5173")
        command = [
            _npm_command(), "run", "dev", "--",
            "--host", "127.0.0.1", "--port", port,
        ]
        return subprocess.Popen(command, cwd=frontend)
    except FileNotFoundError:
        print("[launcher] Node.js/npm not installed. Install Node.js 20+ to launch React.")
    except subprocess.CalledProcessError as exc:
        print(f"[launcher] Frontend dependency installation failed: {exc}")
    return None


def main() -> None:
    from werkzeug.serving import make_server
    from backend.app import app
    from backend.training import training_worker

    host = os.getenv("FLASK_HOST", "127.0.0.1")
    port = int(os.getenv("FLASK_PORT", "5000"))
    frontend_port = os.getenv("FRONTEND_PORT", "5173")

    # Bind before spawning other services so a port conflict cannot orphan Vite.
    server = make_server(host, port, app, threaded=True)
    api_thread = threading.Thread(target=server.serve_forever, name="flask-api", daemon=True)
    worker = threading.Thread(target=training_worker, name="mongo-training-worker", daemon=True)
    frontend_process = None

    try:
        api_thread.start()
        worker.start()
        frontend_process = start_frontend()
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
        if api_thread.is_alive():
            api_thread.join(timeout=5)


if __name__ == "__main__":
    main()
