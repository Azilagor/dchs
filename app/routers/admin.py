from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.config import ADMIN_PAGE_SIZE, MAX_UPLOAD_SIZE_MB
from app.database import get_db
from app.models import Category, Department, HeroSlide, Material, MaterialFile, MaterialLink, MaterialVersion, MaterialVideo, User
from app.security import hash_password, require_roles, validate_csrf
from app.search_index import refresh_file_extracted_text, refresh_material_search_text
from app.template_config import templates
from app.utils import get_or_create_tags, parse_lines, save_upload_file, slugify, unique_material_slug

router = APIRouter(prefix="/admin")

MATERIAL_TYPES = ["document", "instruction", "order", "video", "link", "article", "faq", "template"]
STATUSES = ["draft", "review", "published", "archived"]
VISIBILITIES = ["public", "internal"]
ROLES = ["admin", "moderator", "editor", "staff"]


@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    total_storage_bytes = db.query(func.coalesce(func.sum(MaterialFile.size_bytes), 0)).scalar() or 0
    stats = {
        "materials": db.query(Material).count(),
        "published": db.query(Material).filter(Material.status == "published").count(),
        "drafts": db.query(Material).filter(Material.status == "draft").count(),
        "categories": db.query(Category).count(),
        "users": db.query(User).count(),
        "files": db.query(MaterialFile).count(),
        "slides": db.query(HeroSlide).count(),
        "storage_mb": round(total_storage_bytes / (1024 * 1024), 2),
    }
    latest = db.query(Material).order_by(Material.updated_at.desc()).limit(8).all()
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {"request": request, "current_user": current_user, "stats": stats, "latest": latest},
    )


@router.get("/materials")
def admin_materials(request: Request, page: int = 1, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    page = max(page, 1)
    query = db.query(Material).options(joinedload(Material.category))
    total = query.count()
    total_pages = max((total + ADMIN_PAGE_SIZE - 1) // ADMIN_PAGE_SIZE, 1)
    if page > total_pages:
        page = total_pages
    materials = (
        query.order_by(Material.updated_at.desc())
        .offset((page - 1) * ADMIN_PAGE_SIZE)
        .limit(ADMIN_PAGE_SIZE)
        .all()
    )
    return templates.TemplateResponse(
        request,
        "admin/materials/list.html",
        {
            "request": request,
            "current_user": current_user,
            "materials": materials,
            "page": page,
            "total_pages": total_pages,
            "total_materials": total,
        },
    )


@router.get("/slides")
def slides_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    slides = db.query(HeroSlide).order_by(HeroSlide.sort_order, HeroSlide.id).all()
    return templates.TemplateResponse(
        request,
        "admin/slides/list.html",
        {"request": request, "current_user": current_user, "slides": slides},
    )


@router.get("/slides/create")
def create_slide_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    context = _slide_form_context(request, current_user, slide=None)
    return templates.TemplateResponse(request, "admin/slides/form.html", context)


@router.post("/slides/create")
async def create_slide(
    request: Request,
    title: str = Form(...),
    subtitle: str = Form(""),
    sort_order: int = Form(0),
    is_active: bool = Form(False),
    csrf_token: str = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    try:
        saved = await save_upload_file(image, "sliders")
        if not saved:
            raise ValueError("Изображение слайда не загружено.")
    except ValueError as exc:
        context = _slide_form_context(
            request,
            current_user,
            slide=None,
            error=str(exc),
            form_values={"title": title, "subtitle": subtitle, "sort_order": sort_order, "is_active": is_active},
        )
        return templates.TemplateResponse(request, "admin/slides/form.html", context, status_code=400)

    db.add(
        HeroSlide(
            title=title,
            subtitle=subtitle,
            sort_order=sort_order,
            is_active=is_active,
            image_path=saved["file_path"],
            image_name=saved["original_name"],
        )
    )
    db.commit()
    return RedirectResponse(url="/admin/slides", status_code=303)


@router.get("/slides/{slide_id}/edit")
def edit_slide_page(slide_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    slide = db.query(HeroSlide).filter(HeroSlide.id == slide_id).first()
    if not slide:
        return RedirectResponse(url="/admin/slides", status_code=303)
    context = _slide_form_context(request, current_user, slide=slide)
    return templates.TemplateResponse(request, "admin/slides/form.html", context)


@router.post("/slides/{slide_id}/edit")
async def edit_slide(
    slide_id: int,
    request: Request,
    title: str = Form(...),
    subtitle: str = Form(""),
    sort_order: int = Form(0),
    is_active: bool = Form(False),
    csrf_token: str = Form(...),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    slide = db.query(HeroSlide).filter(HeroSlide.id == slide_id).first()
    if not slide:
        return RedirectResponse(url="/admin/slides", status_code=303)

    slide.title = title
    slide.subtitle = subtitle
    slide.sort_order = sort_order
    slide.is_active = is_active

    if image and image.filename:
        try:
            saved = await save_upload_file(image, "sliders")
            if not saved:
                raise ValueError("Изображение слайда не загружено.")
        except ValueError as exc:
            context = _slide_form_context(
                request,
                current_user,
                slide=slide,
                error=str(exc),
                form_values={"title": title, "subtitle": subtitle, "sort_order": sort_order, "is_active": is_active},
            )
            return templates.TemplateResponse(request, "admin/slides/form.html", context, status_code=400)
        slide.image_path = saved["file_path"]
        slide.image_name = saved["original_name"]

    db.commit()
    return RedirectResponse(url="/admin/slides", status_code=303)


@router.post("/slides/{slide_id}/delete")
def delete_slide(
    slide_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    slide = db.query(HeroSlide).filter(HeroSlide.id == slide_id).first()
    if slide:
        db.delete(slide)
        db.commit()
    return RedirectResponse(url="/admin/slides", status_code=303)


@router.get("/materials/create")
def create_material_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    context = _material_form_context(request, db, current_user, material=None)
    return templates.TemplateResponse(request, "admin/materials/form.html", context)


@router.post("/materials/create")
async def create_material(
    request: Request,
    title: str = Form(...),
    material_type: str = Form(...),
    status: str = Form("draft"),
    visibility: str = Form("public"),
    category_id: int = Form(0),
    department_id: int = Form(0),
    short_description: str = Form(""),
    content: str = Form(""),
    order_number: str = Form(""),
    is_pinned: bool = Form(False),
    tags: str = Form(""),
    links: str = Form(""),
    videos: str = Form(""),
    csrf_token: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    material = Material(
        title=title,
        slug=unique_material_slug(db, title),
        material_type=material_type,
        status=status,
        visibility=visibility,
        category_id=category_id or None,
        department_id=department_id or None,
        short_description=short_description,
        content=content,
        order_number=order_number,
        is_pinned=is_pinned,
        created_by_id=current_user.id,
        updated_by_id=current_user.id,
        published_at=datetime.utcnow() if status == "published" else None,
    )
    material.tags = get_or_create_tags(db, tags)
    db.add(material)
    db.flush()

    try:
        _replace_links(material, links)
        _replace_videos(material, videos)
        await _append_files(material, files)
        refresh_material_search_text(material)
    except ValueError as exc:
        db.rollback()
        context = _material_form_context(
            request,
            db,
            current_user,
            material=None,
            error=str(exc),
            form_values=_submitted_material_form_values(
                title=title,
                material_type=material_type,
                status=status,
                visibility=visibility,
                category_id=category_id,
                department_id=department_id,
                short_description=short_description,
                content=content,
                order_number=order_number,
                is_pinned=is_pinned,
                tags=tags,
                links=links,
                videos=videos,
            ),
        )
        return templates.TemplateResponse(request, "admin/materials/form.html", context, status_code=400)

    db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)


@router.get("/materials/{material_id}/edit")
def edit_material_page(material_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    material = (
        db.query(Material)
        .options(joinedload(Material.tags), joinedload(Material.files), joinedload(Material.links), joinedload(Material.videos))
        .filter(Material.id == material_id)
        .first()
    )
    if not material:
        return RedirectResponse(url="/admin/materials", status_code=303)
    context = _material_form_context(request, db, current_user, material=material)
    return templates.TemplateResponse(request, "admin/materials/form.html", context)


@router.post("/materials/{material_id}/edit")
async def edit_material(
    material_id: int,
    request: Request,
    title: str = Form(...),
    material_type: str = Form(...),
    status: str = Form("draft"),
    visibility: str = Form("public"),
    category_id: int = Form(0),
    department_id: int = Form(0),
    short_description: str = Form(""),
    content: str = Form(""),
    order_number: str = Form(""),
    is_pinned: bool = Form(False),
    tags: str = Form(""),
    links: str = Form(""),
    videos: str = Form(""),
    csrf_token: str = Form(...),
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        return RedirectResponse(url="/admin/materials", status_code=303)

    latest_version = db.query(func.max(MaterialVersion.version_number)).filter(MaterialVersion.material_id == material.id).scalar() or 0
    db.add(
        MaterialVersion(
            material_id=material.id,
            version_number=latest_version + 1,
            title=material.title,
            content=material.content,
            short_description=material.short_description,
            changed_by_id=current_user.id,
        )
    )

    material.title = title
    material.slug = unique_material_slug(db, title, current_id=material.id)
    material.material_type = material_type
    material.status = status
    material.visibility = visibility
    material.category_id = category_id or None
    material.department_id = department_id or None
    material.short_description = short_description
    material.content = content
    material.order_number = order_number
    material.is_pinned = is_pinned
    material.updated_by_id = current_user.id
    if status == "published" and not material.published_at:
        material.published_at = datetime.utcnow()
    material.tags = get_or_create_tags(db, tags)

    try:
        _replace_links(material, links)
        _replace_videos(material, videos)
        await _append_files(material, files)
        refresh_material_search_text(material)
    except ValueError as exc:
        db.rollback()
        material = (
            db.query(Material)
            .options(joinedload(Material.tags), joinedload(Material.files), joinedload(Material.links), joinedload(Material.videos))
            .filter(Material.id == material_id)
            .first()
        )
        context = _material_form_context(
            request,
            db,
            current_user,
            material=material,
            error=str(exc),
            form_values=_submitted_material_form_values(
                title=title,
                material_type=material_type,
                status=status,
                visibility=visibility,
                category_id=category_id,
                department_id=department_id,
                short_description=short_description,
                content=content,
                order_number=order_number,
                is_pinned=is_pinned,
                tags=tags,
                links=links,
                videos=videos,
            ),
        )
        return templates.TemplateResponse(request, "admin/materials/form.html", context, status_code=400)

    db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)


@router.post("/materials/{material_id}/status")
def update_material_status(
    material_id: int,
    request: Request,
    status: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    material = db.query(Material).filter(Material.id == material_id).first()
    if material and status in STATUSES:
        material.status = status
        material.updated_by_id = current_user.id
        if status == "published" and not material.published_at:
            material.published_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)


@router.post("/materials/{material_id}/delete")
def delete_material(
    material_id: int,
    request: Request,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin"])
    validate_csrf(request, csrf_token)
    material = db.query(Material).filter(Material.id == material_id).first()
    if material:
        db.delete(material)
        db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)


@router.get("/categories")
def categories_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    categories = db.query(Category).order_by(Category.sort_order, Category.name).all()
    return templates.TemplateResponse(
        request,
        "admin/categories/list.html",
        {"request": request, "current_user": current_user, "categories": categories},
    )


@router.post("/categories")
def create_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    sort_order: int = Form(0),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    category = Category(name=name, slug=_unique_category_slug(db, name), description=description, sort_order=sort_order)
    db.add(category)
    db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)


@router.get("/departments")
def departments_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    departments = db.query(Department).order_by(Department.name).all()
    return templates.TemplateResponse(
        request,
        "admin/departments/list.html",
        {"request": request, "current_user": current_user, "departments": departments},
    )


@router.post("/departments")
def create_department(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin", "moderator", "editor"])
    validate_csrf(request, csrf_token)
    exists = db.query(Department).filter(Department.name == name).first()
    if not exists:
        db.add(Department(name=name, description=description))
        db.commit()
    return RedirectResponse(url="/admin/departments", status_code=303)


@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin"])
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        request,
        "admin/users/list.html",
        {"request": request, "current_user": current_user, "users": users, "roles": ROLES},
    )


@router.post("/users")
def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("staff"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin"])
    validate_csrf(request, csrf_token)
    exists = db.query(User).filter(User.email == email).first()
    if not exists and role in ROLES:
        db.add(User(email=email, full_name=full_name, hashed_password=hash_password(password), role=role))
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)


def _material_form_context(
    request: Request,
    db: Session,
    current_user: User,
    material: Material | None,
    error: str | None = None,
    form_values: dict | None = None,
):
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
    departments = db.query(Department).order_by(Department.name).all()
    values = {
        "title": material.title if material else "",
        "short_description": material.short_description if material else "",
        "content": material.content if material else "",
        "tags": ", ".join([tag.name for tag in material.tags]) if material else "",
        "links": "\n".join([f"{link.title}|{link.url}" for link in material.links]) if material else "",
        "videos": "\n".join([f"{video.title or 'Видео'}|{video.video_url or video.embed_url or ''}" for video in material.videos]) if material else "",
        "material_type": material.material_type if material else MATERIAL_TYPES[0],
        "status": material.status if material else STATUSES[0],
        "visibility": material.visibility if material else VISIBILITIES[0],
        "category_id": material.category_id if material and material.category_id else 0,
        "department_id": material.department_id if material and material.department_id else 0,
        "order_number": material.order_number if material else "",
        "is_pinned": material.is_pinned if material else False,
    }
    if form_values:
        values.update(form_values)
    return {
        "request": request,
        "current_user": current_user,
        "material": material,
        "categories": categories,
        "departments": departments,
        "material_types": MATERIAL_TYPES,
        "statuses": STATUSES,
        "visibilities": VISIBILITIES,
        "form_values": values,
        "error": error,
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
    }


def _slide_form_context(
    request: Request,
    current_user: User,
    slide: HeroSlide | None,
    error: str | None = None,
    form_values: dict | None = None,
):
    values = {
        "title": slide.title if slide else "",
        "subtitle": slide.subtitle if slide else "",
        "sort_order": slide.sort_order if slide else 0,
        "is_active": slide.is_active if slide else True,
    }
    if form_values:
        values.update(form_values)
    return {
        "request": request,
        "current_user": current_user,
        "slide": slide,
        "form_values": values,
        "error": error,
    }


def _submitted_material_form_values(
    *,
    title: str,
    material_type: str,
    status: str,
    visibility: str,
    category_id: int,
    department_id: int,
    short_description: str,
    content: str,
    order_number: str,
    is_pinned: bool,
    tags: str,
    links: str,
    videos: str,
):
    return {
        "title": title,
        "material_type": material_type,
        "status": status,
        "visibility": visibility,
        "category_id": category_id,
        "department_id": department_id,
        "short_description": short_description,
        "content": content,
        "order_number": order_number,
        "is_pinned": is_pinned,
        "tags": tags,
        "links": links,
        "videos": videos,
    }


def _replace_links(material: Material, raw_links: str):
    material.links.clear()
    for title, url in parse_lines(raw_links):
        material.links.append(MaterialLink(title=title, url=url))


def _replace_videos(material: Material, raw_videos: str):
    material.videos.clear()
    for title, url in parse_lines(raw_videos):
        material.videos.append(MaterialVideo(title=title, video_url=url, embed_url=url))


async def _append_files(material: Material, files: Optional[List[UploadFile]]):
    if not files:
        return
    for upload in files:
        saved = await save_upload_file(upload, "documents")
        if saved:
            file = MaterialFile(title=saved["original_name"], **saved)
            refresh_file_extracted_text(file)
            material.files.append(file)


def _unique_category_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    counter = 2
    while db.query(Category).filter(Category.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug
