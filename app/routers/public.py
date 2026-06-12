from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR, PAGE_SIZE
from app.database import get_db
from app.models import Category, HeroSlide, Material, MaterialFile, MaterialLink, Tag
from app.security import get_current_user
from app.search_index import resolve_upload_path, strip_markup
from app.template_config import templates
from app.utils import material_type_label

router = APIRouter()

MATERIAL_TYPES = ["document", "instruction", "order", "video", "link", "article", "faq", "template"]
SITE_ASSETS = {
    "logo.jpg": Path("logo.jpg"),
    "photo1.jpeg": Path("photo1.jpeg"),
    "photo2.jpeg": Path("photo2.jpeg"),
}


def build_content_disposition(filename: str, disposition_type: str = "inline") -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_fallback:
        ascii_fallback = "download"
    encoded_filename = quote(filename, safe="")
    return f'{disposition_type}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_filename}'


def resolve_slide_image_path(image_path: str) -> Path | None:
    if not image_path:
        return None
    if image_path.startswith("uploads/"):
        return resolve_upload_path(image_path)
    candidate = BASE_DIR / image_path
    return candidate if candidate.exists() else None


def accessible_materials(db: Session, current_user):
    query = db.query(Material).options(joinedload(Material.category), joinedload(Material.tags)).filter(Material.status == "published")
    if not current_user:
        query = query.filter(Material.visibility == "public")
    return query


def apply_material_search(query, q: str):
    if not q or not q.strip():
        return query
    pattern = f"%{q.strip()}%"
    return query.filter(
        or_(
            Material.search_text.ilike(pattern),
            Material.title.ilike(pattern),
            Material.short_description.ilike(pattern),
            Material.content.ilike(pattern),
            Material.order_number.ilike(pattern),
            Material.category.has(Category.name.ilike(pattern)),
            Material.tags.any(Tag.name.ilike(pattern)),
            Material.files.any(MaterialFile.original_name.ilike(pattern)),
            Material.files.any(MaterialFile.extracted_text.ilike(pattern)),
            Material.links.any(MaterialLink.title.ilike(pattern)),
            Material.links.any(MaterialLink.url.ilike(pattern)),
        )
    )


def make_search_snippet(material: Material) -> str:
    raw = material.short_description or material.content or material.search_text or ""
    clean = strip_markup(raw)
    if not clean:
        return material.category.name if material.category else "Открыть материал"
    return clean[:140] + ("..." if len(clean) > 140 else "")


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    base = accessible_materials(db, current_user)
    slides = db.query(HeroSlide).filter(HeroSlide.is_active.is_(True)).order_by(HeroSlide.sort_order, HeroSlide.id).all()
    pinned_materials = base.filter(Material.is_pinned.is_(True)).order_by(Material.published_at.desc().nullslast()).limit(6).all()
    latest_materials = base.order_by(Material.published_at.desc().nullslast(), Material.created_at.desc()).limit(8).all()
    popular_materials = base.order_by(Material.views_count.desc(), Material.created_at.desc()).limit(5).all()
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
    featured_sections = []
    featured_categories = [category for category in categories if category.featured_on_home]
    for category in featured_categories:
        featured_sections.append(
            {
                "name": category.name,
                "slug": category.slug,
                "description": category.description or "Открыть подборку материалов по направлению.",
                "material_count": base.filter(Material.category_id == category.id).count(),
            }
        )
    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "request": request,
            "current_user": current_user,
            "pinned_materials": pinned_materials,
            "latest_materials": latest_materials,
            "popular_materials": popular_materials,
            "categories": categories,
            "material_types": MATERIAL_TYPES,
            "featured_sections": featured_sections,
            "slides": slides,
        },
    )


@router.get("/site-assets/{filename}")
def site_asset(filename: str):
    asset_path = SITE_ASSETS.get(filename)
    if not asset_path or not asset_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)


@router.get("/slides/{slide_id}/image")
def slide_image(slide_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    slide = db.query(HeroSlide).filter(HeroSlide.id == slide_id).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Слайд не найден")
    if not slide.is_active and not current_user:
        raise HTTPException(status_code=404, detail="Слайд не найден")
    image_path = resolve_slide_image_path(slide.image_path)
    if not image_path or not image_path.exists():
        raise HTTPException(status_code=404, detail="Изображение не найдено")
    return FileResponse(image_path)


@router.get("/files/{file_id}/download")
def download_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    file = (
        db.query(MaterialFile)
        .options(joinedload(MaterialFile.material).joinedload(Material.category))
        .filter(MaterialFile.id == file_id)
        .first()
    )
    if not file or not file.material:
        raise HTTPException(status_code=404, detail="Файл не найден")

    material = file.material
    is_privileged_user = bool(current_user and current_user.role in {"admin", "moderator", "editor"})
    if not is_privileged_user:
        if material.status != "published":
            raise HTTPException(status_code=404, detail="Файл не найден")
        if material.visibility != "public" and not current_user:
            raise HTTPException(status_code=403, detail="Недостаточно прав")

    file_path = resolve_upload_path(file.file_path)
    if not file_path or not file_path.exists():
        raise HTTPException(status_code=404, detail="Файл не найден")

    media_type = file.file_type or "application/octet-stream"
    response = FileResponse(file_path, media_type=media_type)
    response.headers["Content-Disposition"] = build_content_disposition(file.original_name)
    return response


@router.get("/api/search")
def live_search(request: Request, q: str = "", limit: int = 8, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    limit = max(1, min(limit, 12))
    trimmed = q.strip()
    if len(trimmed) < 2:
        return JSONResponse({"items": []})

    query = apply_material_search(accessible_materials(db, current_user), trimmed)
    materials = (
        query.order_by(Material.is_pinned.desc(), Material.views_count.desc(), Material.published_at.desc().nullslast(), Material.created_at.desc())
        .limit(limit)
        .all()
    )
    items = [
        {
            "title": item.title,
            "slug": item.slug,
            "url": f"/materials/{item.slug}",
            "category": item.category.name if item.category else "",
            "type": material_type_label(item.material_type),
            "snippet": make_search_snippet(item),
        }
        for item in materials
    ]
    return JSONResponse({"items": items})


@router.get("/materials")
def material_list(
    request: Request,
    q: str = "",
    category: str = "",
    material_type: str = "",
    tag: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    current_user = get_current_user(request, db)
    query = accessible_materials(db, current_user)

    if q:
        query = apply_material_search(query, q)
    if category:
        query = query.join(Category).filter(Category.slug == category)
    if material_type:
        query = query.filter(Material.material_type == material_type)
    if tag:
        query = query.join(Material.tags).filter(Tag.slug == tag)

    page = max(page, 1)
    total = query.count()
    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    if page > total_pages:
        page = total_pages

    materials = (
        query.order_by(Material.is_pinned.desc(), Material.published_at.desc().nullslast(), Material.created_at.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    )
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
    tags = db.query(Tag).order_by(Tag.name).all()
    return templates.TemplateResponse(
        request,
        "materials/list.html",
        {
            "request": request,
            "current_user": current_user,
            "materials": materials,
            "categories": categories,
            "tags": tags,
            "material_types": MATERIAL_TYPES,
            "q": q,
            "selected_category": category,
            "selected_material_type": material_type,
            "selected_tag": tag,
            "page": page,
            "total_pages": total_pages,
            "total_materials": total,
        },
    )


@router.get("/materials/{slug}")
def material_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    query = db.query(Material).options(
        joinedload(Material.category),
        joinedload(Material.tags),
        joinedload(Material.files),
        joinedload(Material.links),
        joinedload(Material.videos),
        joinedload(Material.department),
    ).filter(Material.slug == slug, Material.status == "published")
    if not current_user:
        query = query.filter(Material.visibility == "public")
    material = query.first()
    if not material:
        return templates.TemplateResponse(request, "errors/404.html", {"request": request, "current_user": current_user}, status_code=404)

    material.views_count += 1
    db.commit()
    db.refresh(material)

    related = []
    if material.category_id:
        related = accessible_materials(db, current_user).filter(
            Material.category_id == material.category_id,
            Material.id != material.id,
        ).order_by(Material.published_at.desc().nullslast()).limit(4).all()

    return templates.TemplateResponse(
        request,
        "materials/detail.html",
        {"request": request, "current_user": current_user, "material": material, "related": related},
    )


@router.get("/categories")
def category_list(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
    return templates.TemplateResponse(request, "categories/list.html", {"request": request, "current_user": current_user, "categories": categories})


@router.get("/categories/{slug}")
def category_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    category = db.query(Category).filter(Category.slug == slug, Category.is_active.is_(True)).first()
    if not category:
        return templates.TemplateResponse(request, "errors/404.html", {"request": request, "current_user": current_user}, status_code=404)
    materials = accessible_materials(db, current_user).filter(Material.category_id == category.id).order_by(Material.published_at.desc().nullslast()).all()
    return templates.TemplateResponse(request, "categories/detail.html", {"request": request, "current_user": current_user, "category": category, "materials": materials})
