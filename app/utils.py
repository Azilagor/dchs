import re
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_SIZE_MB, UPLOAD_DIR
from app.models import Material, Tag

CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "a", "ғ": "g", "қ": "q", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i",
}

UPLOAD_SIGNATURES = {
    ".pdf": [b"%PDF-"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".webp": [b"RIFF"],
    ".zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".docx": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".xlsx": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".pptx": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".rtf": [b"{\\rtf"],
}

ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".doc": {"application/msword", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    ".xls": {"application/vnd.ms-excel", "application/octet-stream"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
    ".ppt": {"application/vnd.ms-powerpoint", "application/octet-stream"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
        "application/octet-stream",
    },
    ".txt": {"text/plain", "application/octet-stream"},
    ".rtf": {"application/rtf", "text/rtf", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".png": {"image/png", "application/octet-stream"},
    ".webp": {"image/webp", "application/octet-stream"},
    ".mp4": {"video/mp4", "application/octet-stream"},
    ".avi": {"video/x-msvideo", "video/avi", "application/octet-stream"},
    ".mov": {"video/quicktime", "application/octet-stream"},
    ".zip": {"application/zip", "application/x-zip-compressed", "application/octet-stream"},
}

BLOCKED_MAGIC_HEADERS = (
    b"MZ",
    b"\x7fELF",
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"#!",
)


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = "".join(CYRILLIC_MAP.get(ch, ch) for ch in value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or uuid.uuid4().hex[:8]


def unique_material_slug(db: Session, title: str, current_id: int | None = None) -> str:
    base = slugify(title)
    slug = base
    counter = 2
    while True:
        query = db.query(Material).filter(Material.slug == slug)
        if current_id:
            query = query.filter(Material.id != current_id)
        if not query.first():
            return slug
        slug = f"{base}-{counter}"
        counter += 1


def unique_tag_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    counter = 2
    while db.query(Tag).filter(Tag.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def get_or_create_tags(db: Session, raw_tags: str) -> list[Tag]:
    result: list[Tag] = []
    names = [name.strip() for name in raw_tags.split(",") if name.strip()]
    for name in names:
        tag = db.query(Tag).filter(Tag.name.ilike(name)).first()
        if not tag:
            tag = Tag(name=name, slug=unique_tag_slug(db, name))
            db.add(tag)
            db.flush()
        result.append(tag)
    return result


def parse_lines(raw: str) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if "|" in line:
            title, value = line.split("|", 1)
        else:
            title, value = line, line
        title = title.strip()
        value = value.strip()
        if title and value:
            items.append((title, value))
    return items


def _looks_like_text(content: bytes) -> bool:
    if not content:
        return True
    text_bytes = sum(byte in b"\t\n\r\f\b" or 32 <= byte <= 126 or byte >= 128 for byte in content)
    return (text_bytes / len(content)) >= 0.85


def _validate_upload_signature(filename: str, content_type: str | None, header: bytes) -> None:
    suffix = Path(filename).suffix.lower()
    if header.startswith(BLOCKED_MAGIC_HEADERS):
        raise ValueError(f"Файл '{filename}' отклонен из соображений безопасности.")

    allowed_types = ALLOWED_CONTENT_TYPES.get(suffix)
    if content_type and allowed_types and content_type not in allowed_types:
        raise ValueError(f"Файл '{filename}' имеет неподдерживаемый content-type: {content_type}.")

    signatures = UPLOAD_SIGNATURES.get(suffix, [])
    if suffix == ".webp":
        if not (header.startswith(b"RIFF") and b"WEBP" in header[:16]):
            raise ValueError(f"Файл '{filename}' не похож на корректный WEBP.")
    elif suffix == ".mp4":
        if len(header) < 12 or b"ftyp" not in header[:32]:
            raise ValueError(f"Файл '{filename}' не похож на корректный MP4.")
    elif suffix in {".txt", ".doc", ".xls", ".ppt", ".avi", ".mov"}:
        if not _looks_like_text(header) and suffix in {".txt"}:
            raise ValueError(f"Файл '{filename}' не похож на текстовый документ.")
    elif signatures and not any(header.startswith(signature) for signature in signatures):
        raise ValueError(f"Файл '{filename}' не прошел проверку сигнатуры.")


async def save_upload_file(upload: UploadFile, folder: str = "documents") -> dict | None:
    if not upload or not upload.filename:
        return None

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        allowed = ", ".join(ALLOWED_UPLOAD_EXTENSIONS)
        raise ValueError(f"Файл '{upload.filename}' запрещен. Разрешены только: {allowed}.")

    header = upload.file.read(8192)
    upload.file.seek(0)
    _validate_upload_signature(upload.filename, upload.content_type, header)

    target_dir = UPLOAD_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}{suffix}"
    target_path = target_dir / safe_name
    max_size_bytes = MAX_UPLOAD_SIZE_MB * 1024 * 1024
    total_written = 0

    try:
        with target_path.open("wb") as buffer:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total_written += len(chunk)
                if total_written > max_size_bytes:
                    raise ValueError(f"Файл '{upload.filename}' превышает лимит {MAX_UPLOAD_SIZE_MB} МБ.")
                buffer.write(chunk)
    except Exception:
        if target_path.exists():
            target_path.unlink()
        raise
    finally:
        await upload.close()

    relative_path = target_path.relative_to(UPLOAD_DIR).as_posix()
    public_path = f"uploads/{relative_path}"
    return {
        "original_name": upload.filename,
        "file_path": public_path,
        "file_type": upload.content_type,
        "size_bytes": target_path.stat().st_size,
    }


def material_type_label(value: str) -> str:
    return {
        "document": "Документ",
        "instruction": "Инструкция",
        "order": "Приказ",
        "video": "Видео",
        "link": "Ссылка",
        "article": "Статья",
        "faq": "FAQ",
        "template": "Шаблон",
    }.get(value, value)


def status_label(value: str) -> str:
    return {
        "draft": "Черновик",
        "review": "На проверке",
        "published": "Опубликовано",
        "archived": "Архив",
    }.get(value, value)


def visibility_label(value: str) -> str:
    return {
        "public": "Публичный",
        "internal": "Внутренний",
    }.get(value, value)
