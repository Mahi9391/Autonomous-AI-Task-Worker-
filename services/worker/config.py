import os
from pathlib import Path
from pydantic import BaseModel
from typing import Optional, List

# Base workspace directory
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent

def load_env_file():
    env_file = WORKSPACE_ROOT / ".env"
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    os.environ[k] = v

load_env_file()

class Settings(BaseModel):
    # Gemini Configuration
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    gemini_base_url: str = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")

    # Server Ports
    worker_port: int = int(os.getenv("WORKER_PORT", "8000"))
    company_app_port: int = int(os.getenv("COMPANY_APP_PORT", "8001"))
    email_sandbox_port: int = int(os.getenv("EMAIL_SANDBOX_PORT", "8002"))
    dashboard_port: int = int(os.getenv("DASHBOARD_PORT", "5173"))

    # Server Base URLs
    worker_base_url: str = os.getenv("WORKER_BASE_URL", f"http://localhost:{os.getenv('WORKER_PORT', '8000')}")
    company_app_base_url: str = os.getenv("COMPANY_APP_BASE_URL", f"http://localhost:{os.getenv('COMPANY_APP_PORT', '8001')}")
    email_sandbox_base_url: str = os.getenv("EMAIL_SANDBOX_BASE_URL", f"http://localhost:{os.getenv('EMAIL_SANDBOX_PORT', '8002')}")
    dashboard_base_url: str = os.getenv("DASHBOARD_BASE_URL", f"http://localhost:{os.getenv('DASHBOARD_PORT', '5173')}")

    # Clock & Scheduler
    scheduler_timezone: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata")
    scheduler_interval_minutes: int = int(os.getenv("SCHEDULER_INTERVAL_MINUTES", "60"))
    business_hours_start: str = os.getenv("BUSINESS_HOURS_START", "09:00")
    business_hours_end: str = os.getenv("BUSINESS_HOURS_END", "18:00")
    business_days: List[int] = [0, 1, 2, 3, 4] # Mon-Fri
    enforce_business_hours: bool = os.getenv("ENFORCE_BUSINESS_HOURS", "false").lower() in ("true", "1")
    clock_override: Optional[str] = os.getenv("CLOCK_OVERRIDE", None)

    # Watcher & Storage
    data_dir: Path = WORKSPACE_ROOT / "data"
    watched_dir: Path = WORKSPACE_ROOT / "data" / "watched"
    uploads_dir: Path = WORKSPACE_ROOT / "data" / "uploads"
    traces_dir: Path = WORKSPACE_ROOT / "data" / "traces"
    watcher_stabilize_seconds: float = float(os.getenv("WATCHER_STABILIZE_SECONDS", "2.0"))

    # SQLite Databases
    worker_db_path: Path = WORKSPACE_ROOT / "data" / "worker.db"
    company_db_path: Path = WORKSPACE_ROOT / "data" / "company.db"
    email_db_path: Path = WORKSPACE_ROOT / "data" / "email.db"

settings = Settings()

# Ensure directories exist
for directory in [settings.data_dir, settings.watched_dir, settings.uploads_dir, settings.traces_dir]:
    directory.mkdir(parents=True, exist_ok=True)
