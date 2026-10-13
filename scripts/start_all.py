import sys
import subprocess
import time
import json
import signal
from pathlib import Path
import httpx

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = WORKSPACE_ROOT / "data"
PID_FILE = DATA_DIR / "pids.json"

PYTHON_BIN = sys.executable

def start_services():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 65)
    print("  Starting CentrAlign Autonomous AI Task Worker Platform")
    print("=" * 65)

    processes = {}

    # 1. Company App (Port 8001)
    print("-> Launching Company ERP App (port 8001)...")
    p_company = subprocess.Popen([
        PYTHON_BIN, "-m", "uvicorn", "main:app",
        "--app-dir", str(WORKSPACE_ROOT / "apps" / "company-app"),
        "--port", "8001", "--host", "127.0.0.1"
    ])
    processes["company_app"] = p_company.pid

    # 2. Email Sandbox (Port 8002)
    print("-> Launching Email Sandbox App (port 8002)...")
    p_email = subprocess.Popen([
        PYTHON_BIN, "-m", "uvicorn", "main:app",
        "--app-dir", str(WORKSPACE_ROOT / "apps" / "email-sandbox"),
        "--port", "8002", "--host", "127.0.0.1"
    ])
    processes["email_sandbox"] = p_email.pid

    # 3. Worker API & Runtime (Port 8000)
    print("-> Launching Worker API & Agent Runtime (port 8000)...")
    p_worker = subprocess.Popen([
        PYTHON_BIN, "-m", "uvicorn", "services.worker.main:app",
        "--port", "8000", "--host", "127.0.0.1"
    ], cwd=str(WORKSPACE_ROOT))
    processes["worker"] = p_worker.pid

    # 4. Dashboard (Port 5173)
    print("-> Launching Operational Dashboard (port 5173)...")
    p_dashboard = subprocess.Popen([
        PYTHON_BIN, str(WORKSPACE_ROOT / "scripts" / "run_dashboard.py")
    ], cwd=str(WORKSPACE_ROOT))
    processes["dashboard"] = p_dashboard.pid

    # Write PIDs
    with open(PID_FILE, "w") as f:
        json.dump(processes, f, indent=2)

    # Health Checks
    print("\nWaiting for services to become healthy...")
    urls = {
        "Worker API": "http://localhost:8000/health",
        "Company ERP": "http://localhost:8001/health",
        "Email Sandbox": "http://localhost:8002/health",
        "Dashboard": "http://localhost:5173/index.html"
    }

    all_healthy = False
    for attempt in range(15):
        time.sleep(1)
        healthy_count = 0
        for name, url in urls.items():
            try:
                r = httpx.get(url, timeout=1.0)
                if r.status_code == 200:
                    healthy_count += 1
            except Exception:
                pass
        if healthy_count == len(urls):
            all_healthy = True
            break

    print("=" * 65)
    if all_healthy:
        print("  ALL SERVICES ONLINE AND HEALTHY! ")
    else:
        print("  SERVICES STARTED (Some checks still warming up)")
    print("=" * 65)
    print("  1. Operational Dashboard:  http://localhost:5173")
    print("  2. Company ERP App:        http://localhost:8001")
    print("  3. Email Sandbox:          http://localhost:8002")
    print("  4. Worker API & Docs:      http://localhost:8000/docs")
    print("=" * 65)
    print("Press Ctrl+C to stop all services.\n")

    try:
        # Keep process running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down all services...")
        stop_services(processes)

def stop_services(processes=None):
    if not processes and PID_FILE.exists():
        try:
            with open(PID_FILE, "r") as f:
                processes = json.load(f)
        except Exception:
            processes = {}

    if processes:
        for name, pid in processes.items():
            print(f"Terminating {name} (PID {pid})...")
            try:
                if sys.platform == "win32":
                    subprocess.call(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    print("All services stopped.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "stop":
        stop_services()
    else:
        start_services()
