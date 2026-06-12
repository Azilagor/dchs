from markupsafe import Markup, escape
from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import ALLOWED_UPLOAD_EXTENSIONS, BASE_DIR, ORGANIZATION_NAME, PROJECT_NAME, SITE_DESCRIPTION, SITE_URL, TINYMCE_API_KEY
from app.security import get_csrf_token
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


def absolute_asset_url(path: str, request: Request | None = None) -> str:
    relative = asset_url(path)
    if relative.startswith(("http://", "https://")):
        return relative
    if SITE_URL:
        return f"{SITE_URL}{relative}"
    if request:
        return str(request.url_for("site_asset", filename=path.rsplit("/", 1)[-1])) if path.startswith("/site-assets/") else str(request.base_url).rstrip("/") + relative
    return relative


def csrf_input(request: Request) -> Markup:
    token = get_csrf_token(request)
    return Markup(f'<input type="hidden" name="csrf_token" value="{escape(token)}">')


def nl2br(value: str | None) -> Markup:
    if not value:
        return Markup("")
    escaped = escape(value)
    return Markup(str(escaped).replace("\n", "<br>"))


templates.env.globals["PROJECT_NAME"] = PROJECT_NAME
templates.env.globals["ORGANIZATION_NAME"] = ORGANIZATION_NAME
templates.env.globals["SITE_DESCRIPTION"] = SITE_DESCRIPTION
templates.env.globals["SITE_URL"] = SITE_URL
templates.env.globals["TINYMCE_API_KEY"] = TINYMCE_API_KEY
templates.env.globals["ALLOWED_UPLOAD_EXTENSIONS"] = ALLOWED_UPLOAD_EXTENSIONS
templates.env.globals["asset_url"] = asset_url
templates.env.globals["absolute_asset_url"] = absolute_asset_url
templates.env.globals["csrf_input"] = csrf_input
templates.env.filters["material_type_label"] = material_type_label
templates.env.filters["status_label"] = status_label
templates.env.filters["visibility_label"] = visibility_label
templates.env.filters["nl2br"] = nl2br
