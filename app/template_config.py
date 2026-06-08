from fastapi.templating import Jinja2Templates

from app.config import ALLOWED_UPLOAD_EXTENSIONS, BASE_DIR, ORGANIZATION_NAME, PROJECT_NAME, TINYMCE_API_KEY
from app.utils import material_type_label, status_label, visibility_label

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

templates.env.globals["PROJECT_NAME"] = PROJECT_NAME
templates.env.globals["ORGANIZATION_NAME"] = ORGANIZATION_NAME
templates.env.globals["TINYMCE_API_KEY"] = TINYMCE_API_KEY
templates.env.globals["ALLOWED_UPLOAD_EXTENSIONS"] = ALLOWED_UPLOAD_EXTENSIONS
templates.env.filters["material_type_label"] = material_type_label
templates.env.filters["status_label"] = status_label
templates.env.filters["visibility_label"] = visibility_label
