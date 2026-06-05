import re
import shutil
import uuid
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.models import Material, Tag

CYRILLIC_MAP = {
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"e", "ж":"zh", "з":"z", "и":"i", "й":"y",
    "к":"k", "л":"l", "м":"m", "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u", "ф":"f",
    "х":"h", "ц":"ts", "ч":"ch", "ш":"sh", "щ":"sch", "ъ":"", "ы":"y", "ь":"", "э":"e", "ю":"yu", "я":"ya",
    "ә":"a", "ғ":"g", "қ":"q", "ң":"n", "ө":"o", "ұ":"u", "ү":"u", "һ":"h", "і":"i",
}

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

async def save_upload_file(upload: UploadFile, folder: str = "documents") -> dict | None:
    if not upload or not upload.filename:
        return None

    target_dir = UPLOAD_DIR / folder
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload.filename).suffix
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    target_path = target_dir / safe_name

    with target_path.open("wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)

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
