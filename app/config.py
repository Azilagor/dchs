import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'mchs_directory.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))

PROJECT_NAME = os.getenv("PROJECT_NAME", "Справочник МЧС")
ORGANIZATION_NAME = os.getenv("ORGANIZATION_NAME", "МЧС")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
