from fastapi.templating import Jinja2Templates

from app.config import ALLOWED_UPLOAD_EXTENSIONS, BASE_DIR, ORGANIZATION_NAME, PROJECT_NAME, TINYMCE_API_KEY
from app.utils import material_type_label, status_label, visibility_label

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def asset_url(path: str) -> str:
    relative_path = path.lstrip("/")
    if relative_path.startswith("site-assets/"):
        file_path = BASE_DIR / relative_path.split("/", 1)[1]
    else:
        file_path = BASE_DIR / relative_path
    if file_path.exists():
        version = int(file_path.stat().st_mtime)
        return f"{path}?v={version}"
    return path

templates.env.globals["PROJECT_NAME"] = PROJECT_NAME
templates.env.globals["ORGANIZATION_NAME"] = ORGANIZATION_NAME
templates.env.globals["TINYMCE_API_KEY"] = TINYMCE_API_KEY
templates.env.globals["ALLOWED_UPLOAD_EXTENSIONS"] = ALLOWED_UPLOAD_EXTENSIONS
templates.env.globals["asset_url"] = asset_url
templates.env.filters["material_type_label"] = material_type_label
templates.env.filters["status_label"] = status_label
templates.env.filters["visibility_label"] = visibility_label
