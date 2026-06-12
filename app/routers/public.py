from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import BASE_DIR, PAGE_SIZE, PROJECT_NAME, SITE_DESCRIPTION, SITE_URL
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

INLINE_EXTENSIONS = {".pdf", ".txt", ".rtf", ".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"}
OFFICE_PREVIEW_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


def absolute_url(request: Request, path: str) -> str:
    base = SITE_URL or str(request.base_url).rstrip("/")
    return f"{base}{path}"


def build_seo_context(
    request: Request,
    *,
    title: str,
    description: str | None = None,
    canonical_path: str | None = None,
    robots: str = "index,follow",
    og_type: str = "website",
    og_image_path: str = "/site-assets/logo.jpg",
) -> dict:
    canonical = absolute_url(request, canonical_path or request.url.path)
    resolved_description = (description or SITE_DESCRIPTION).strip()
    return {
        "meta_title": title,
        "meta_description": resolved_description[:160],
        "meta_robots": robots,
        "canonical_url": canonical,
        "og_title": title,
        "og_description": resolved_description[:200],
        "og_type": og_type,
        "og_image_url": absolute_url(request, og_image_path),
    }


def public_materials_query(db: Session):
    return db.query(Material).filter(Material.status == "published", Material.visibility == "public")


def build_content_disposition(filename: str, disposition_type: str = "inline") -> str:
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii").strip()
    if not ascii_fallback:
        ascii_fallback = "download"
    encoded_filename = quote(filename, safe="")
    return f'{disposition_type}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_filename}'


def get_file_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def resolve_file_access(file_id: int, request: Request, db: Session):
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

    return current_user, file, material, file_path


def build_file_preview_context(file: MaterialFile, material: Material, request: Request) -> dict:
    extension = get_file_extension(file.original_name)
    can_inline = extension in INLINE_EXTENSIONS
    can_use_office_viewer = extension in OFFICE_PREVIEW_EXTENSIONS and material.visibility == "public"

    inline_url = f"/files/{file.id}/download?disposition=inline"
    download_url = f"/files/{file.id}/download?disposition=attachment"
    office_preview_url = None

    if can_use_office_viewer:
        absolute_inline_url = str(request.url_for("download_file", file_id=file.id).include_query_params(disposition="inline"))
        office_preview_url = f"https://view.officeapps.live.com/op/embed.aspx?src={quote(absolute_inline_url, safe='')}"

    return {
        "extension": extension,
        "can_inline": can_inline,
        "can_use_office_viewer": can_use_office_viewer,
        "inline_url": inline_url,
        "download_url": download_url,
        "office_preview_url": office_preview_url,
    }


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
            **build_seo_context(
                request,
                title=f"{PROJECT_NAME} - ДЧС Алматы",
                description="Официальный справочник ДЧС Алматы с материалами, инструкциями, приказами и актуальной служебной информацией.",
                canonical_path="/",
            ),
        },
    )


@router.get("/robots.txt")
def robots_txt(request: Request):
    sitemap_url = absolute_url(request, "/sitemap.xml")
    body = "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin",
            "Disallow: /login",
            "Disallow: /logout",
            "Disallow: /api/",
            "Disallow: /files/",
            f"Sitemap: {sitemap_url}",
        ]
    )
    return PlainTextResponse(body)


@router.get("/sitemap.xml")
def sitemap_xml(request: Request, db: Session = Depends(get_db)):
    pages: list[tuple[str, str | None]] = [
        (absolute_url(request, "/"), None),
        (absolute_url(request, "/materials"), None),
        (absolute_url(request, "/categories"), None),
    ]

    for category in db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.id).all():
        pages.append((absolute_url(request, f"/categories/{category.slug}"), None))

    for material in public_materials_query(db).order_by(Material.updated_at.desc().nullslast(), Material.id.desc()).all():
        lastmod = material.updated_at or material.published_at or material.created_at
        pages.append((absolute_url(request, f"/materials/{material.slug}"), lastmod.date().isoformat() if lastmod else None))

    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url, lastmod in pages:
        lines.append("<url>")
        lines.append(f"<loc>{url}</loc>")
        if lastmod:
            lines.append(f"<lastmod>{lastmod}</lastmod>")
        lines.append("</url>")
    lines.append("</urlset>")
    return Response("\n".join(lines), media_type="application/xml")


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
def download_file(file_id: int, request: Request, disposition: str = "inline", db: Session = Depends(get_db)):
    _, file, _, file_path = resolve_file_access(file_id, request, db)
    media_type = file.file_type or "application/octet-stream"
    disposition_type = "attachment" if disposition == "attachment" else "inline"
    response = FileResponse(file_path, media_type=media_type)
    response.headers["Content-Disposition"] = build_content_disposition(file.original_name, disposition_type)
    return response


@router.get("/files/{file_id}", name="file_preview")
def preview_file(file_id: int, request: Request, db: Session = Depends(get_db)):
    current_user, file, material, _ = resolve_file_access(file_id, request, db)
    preview = build_file_preview_context(file, material, request)
    return templates.TemplateResponse(
        request,
        "materials/file_preview.html",
        {
            "request": request,
            "current_user": current_user,
            "file": file,
            "material": material,
            "preview": preview,
            **build_seo_context(
                request,
                title=f"{file.title or file.original_name} - {PROJECT_NAME}",
                description=f"Предпросмотр файла из материала «{material.title}».",
                canonical_path=f"/files/{file.id}",
                robots="noindex,nofollow",
            ),
        },
    )


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
            **build_seo_context(
                request,
                title=f"Материалы - {PROJECT_NAME}",
                description="Каталог материалов ДЧС Алматы: документы, инструкции, приказы, статьи и внутренние справочные публикации.",
                canonical_path="/materials",
                robots="noindex,follow" if page > 1 or q or category or material_type or tag else "index,follow",
            ),
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
        {
            "request": request,
            "current_user": current_user,
            "material": material,
            "related": related,
            **build_seo_context(
                request,
                title=f"{material.title} - {PROJECT_NAME}",
                description=strip_markup(material.short_description or material.content or material.title),
                canonical_path=f"/materials/{material.slug}",
                og_type="article",
            ),
        },
    )


@router.get("/categories")
def category_list(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
    return templates.TemplateResponse(
        request,
        "categories/list.html",
        {
            "request": request,
            "current_user": current_user,
            "categories": categories,
            **build_seo_context(
                request,
                title=f"Категории - {PROJECT_NAME}",
                description="Разделы и категории справочника ДЧС Алматы для быстрого перехода к нужным материалам.",
                canonical_path="/categories",
            ),
        },
    )


@router.get("/categories/{slug}")
def category_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    category = db.query(Category).filter(Category.slug == slug, Category.is_active.is_(True)).first()
    if not category:
        return templates.TemplateResponse(request, "errors/404.html", {"request": request, "current_user": current_user}, status_code=404)
    materials = accessible_materials(db, current_user).filter(Material.category_id == category.id).order_by(Material.published_at.desc().nullslast()).all()
    return templates.TemplateResponse(
        request,
        "categories/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "category": category,
            "materials": materials,
            **build_seo_context(
                request,
                title=f"{category.name} - {PROJECT_NAME}",
                description=category.description or f"Материалы категории «{category.name}» в справочнике ДЧС Алматы.",
                canonical_path=f"/categories/{category.slug}",
            ),
        },
    )
