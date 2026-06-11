import re
from pathlib import Path

from app.config import UPLOAD_DIR
from app.models import Material, MaterialFile

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency import guard
    PdfReader = None

try:
    from docx import Document
except Exception:  # pragma: no cover - optional dependency import guard
    Document = None


def strip_markup(value: str | None) -> str:
    if not value:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", cleaned).strip()


def resolve_upload_path(public_path: str | None) -> Path | None:
    if not public_path:
        return None
    prefix = "uploads/"
    if not public_path.startswith(prefix):
        return None
    relative = public_path[len(prefix):]
    return UPLOAD_DIR / Path(relative)


def extract_text_from_path(path: Path | None) -> str:
    if not path or not path.exists():
        return ""

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf" and PdfReader:
            reader = PdfReader(str(path))
            return " ".join((page.extract_text() or "") for page in reader.pages).strip()
        if suffix == ".docx" and Document:
            document = Document(str(path))
            return " ".join(paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip())
        if suffix in {".txt", ".rtf"}:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
    except Exception:
        return ""
    return ""


def refresh_file_extracted_text(file: MaterialFile) -> str:
    extracted = strip_markup(extract_text_from_path(resolve_upload_path(file.file_path)))
    file.extracted_text = extracted or None
    return extracted


def build_material_search_text(material: Material) -> str:
    parts: list[str] = [
        material.title or "",
        strip_markup(material.short_description),
        strip_markup(material.content),
        material.order_number or "",
    ]

    if material.category:
        parts.append(material.category.name or "")
    if material.department:
        parts.append(material.department.name or "")

    parts.extend(tag.name for tag in material.tags if tag.name)
    parts.extend(file.original_name for file in material.files if file.original_name)
    parts.extend((file.extracted_text or "") for file in material.files if file.extracted_text)
    parts.extend(link.title for link in material.links if link.title)
    parts.extend(link.url for link in material.links if link.url)
    parts.extend((video.title or "") for video in material.videos if video.title)
    parts.extend((video.video_url or video.embed_url or "") for video in material.videos if video.video_url or video.embed_url)

    normalized = " ".join(part.strip() for part in parts if part and part.strip())
    return re.sub(r"\s+", " ", normalized).strip()


def refresh_material_search_text(material: Material) -> str:
    material.search_text = build_material_search_text(material) or None
    return material.search_text or ""
