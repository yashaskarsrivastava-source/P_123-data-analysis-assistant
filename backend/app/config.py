import os
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE}/data/app.db")
SECRET_KEY = os.getenv("SECRET_KEY", "change-this-secret")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE / "data" / "uploads"))
SAMPLE_DIR = ROOT / "sample_data"
FRONTEND_DIR = ROOT / "frontend"
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "noreply@p123.local")
DEV_SHOW_PASSWORD = os.getenv("DEV_SHOW_PASSWORD", "1") == "1"  # only used when SMTP is not configured
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
