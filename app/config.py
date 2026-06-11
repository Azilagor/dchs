import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'mchs_directory.db'}")
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
TINYMCE_API_KEY = os.getenv("TINYMCE_API_KEY", "no-api-key")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "12"))
ADMIN_PAGE_SIZE = int(os.getenv("ADMIN_PAGE_SIZE", "20"))
SESSION_HTTPS_ONLY = _bool_env("SESSION_HTTPS_ONLY", APP_ENV == "production")
SESSION_SAME_SITE = os.getenv("SESSION_SAME_SITE", "lax")
ALLOWED_UPLOAD_EXTENSIONS = tuple(
    ext.strip().lower()
    for ext in os.getenv(
        "ALLOWED_UPLOAD_EXTENSIONS",
        ".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.rtf,.jpg,.jpeg,.png,.webp,.mp4,.avi,.mov,.zip",
    ).split(",")
    if ext.strip()
)

PROJECT_NAME = os.getenv("PROJECT_NAME", "Справочник МЧС")
ORGANIZATION_NAME = os.getenv("ORGANIZATION_NAME", "МЧС")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
