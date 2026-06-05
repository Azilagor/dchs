from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Category, Department, Material, MaterialFile, MaterialLink, MaterialVersion, MaterialVideo, Tag, User
from app.security import hash_password, require_roles
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
    stats = {
        "materials": db.query(Material).count(),
        "published": db.query(Material).filter(Material.status == "published").count(),
        "drafts": db.query(Material).filter(Material.status == "draft").count(),
        "categories": db.query(Category).count(),
        "users": db.query(User).count(),
    }
    latest = db.query(Material).order_by(Material.updated_at.desc()).limit(8).all()
    return templates.TemplateResponse(request,"admin/dashboard.html", {"request": request, "current_user": current_user, "stats": stats, "latest": latest})

@router.get("/materials")
def admin_materials(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    materials = db.query(Material).options(joinedload(Material.category)).order_by(Material.updated_at.desc()).all()
    return templates.TemplateResponse(request,"admin/materials/list.html", {"request": request, "current_user": current_user, "materials": materials})

@router.get("/materials/create")
def create_material_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    context = _material_form_context(request, db, current_user, material=None)
    return templates.TemplateResponse(request,"admin/materials/form.html", context)

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
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
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

    _replace_links(db, material, links)
    _replace_videos(db, material, videos)
    await _append_files(material, files)

    db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)

@router.get("/materials/{material_id}/edit")
def edit_material_page(material_id: int, request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    material = db.query(Material).options(joinedload(Material.tags), joinedload(Material.files), joinedload(Material.links), joinedload(Material.videos)).filter(Material.id == material_id).first()
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
    files: Optional[List[UploadFile]] = File(None),
    db: Session = Depends(get_db),
):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        return RedirectResponse(url="/admin/materials", status_code=303)

    latest_version = db.query(func.max(MaterialVersion.version_number)).filter(MaterialVersion.material_id == material.id).scalar() or 0
    db.add(MaterialVersion(
        material_id=material.id,
        version_number=latest_version + 1,
        title=material.title,
        content=material.content,
        short_description=material.short_description,
        changed_by_id=current_user.id,
    ))

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

    _replace_links(db, material, links)
    _replace_videos(db, material, videos)
    await _append_files(material, files)

    db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)

@router.post("/materials/{material_id}/status")
def update_material_status(material_id: int, request: Request, status: str = Form(...), db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    material = db.query(Material).filter(Material.id == material_id).first()
    if material and status in STATUSES:
        material.status = status
        material.updated_by_id = current_user.id
        if status == "published" and not material.published_at:
            material.published_at = datetime.utcnow()
        db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)

@router.post("/materials/{material_id}/delete")
def delete_material(material_id: int, request: Request, db: Session = Depends(get_db)):
    require_roles(request, db, ["admin"])
    material = db.query(Material).filter(Material.id == material_id).first()
    if material:
        db.delete(material)
        db.commit()
    return RedirectResponse(url="/admin/materials", status_code=303)

@router.get("/categories")
def categories_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    categories = db.query(Category).order_by(Category.sort_order, Category.name).all()
    return templates.TemplateResponse(request, "admin/categories/list.html", {"request": request, "current_user": current_user, "categories": categories})

@router.post("/categories")
def create_category(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin", "moderator", "editor"])
    category = Category(name=name, slug=_unique_category_slug(db, name), description=description, sort_order=sort_order)
    db.add(category)
    db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@router.get("/departments")
def departments_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin", "moderator", "editor"])
    departments = db.query(Department).order_by(Department.name).all()
    return templates.TemplateResponse( request, "admin/departments/list.html", {"request": request, "current_user": current_user, "departments": departments})

@router.post("/departments")
def create_department(request: Request, name: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    require_roles(request, db, ["admin", "moderator", "editor"])
    exists = db.query(Department).filter(Department.name == name).first()
    if not exists:
        db.add(Department(name=name, description=description))
        db.commit()
    return RedirectResponse(url="/admin/departments", status_code=303)

@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    current_user = require_roles(request, db, ["admin"])
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(request, "admin/users/list.html", {"request": request, "current_user": current_user, "users": users, "roles": ROLES})

@router.post("/users")
def create_user(
    request: Request,
    email: str = Form(...),
    full_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("staff"),
    db: Session = Depends(get_db),
):
    require_roles(request, db, ["admin"])
    exists = db.query(User).filter(User.email == email).first()
    if not exists and role in ROLES:
        db.add(User(email=email, full_name=full_name, hashed_password=hash_password(password), role=role))
        db.commit()
    return RedirectResponse(url="/admin/users", status_code=303)

def _material_form_context(request: Request, db: Session, current_user: User, material: Material | None):
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
    departments = db.query(Department).order_by(Department.name).all()
    return {
        "request": request,
        "current_user": current_user,
        "material": material,
        "categories": categories,
        "departments": departments,
        "material_types": MATERIAL_TYPES,
        "statuses": STATUSES,
        "visibilities": VISIBILITIES,
        "tag_value": ", ".join([tag.name for tag in material.tags]) if material else "",
        "link_value": "\n".join([f"{link.title}|{link.url}" for link in material.links]) if material else "",
        "video_value": "\n".join([f"{video.title or 'Видео'}|{video.video_url or video.embed_url or ''}" for video in material.videos]) if material else "",
    }

def _replace_links(db: Session, material: Material, raw_links: str):
    material.links.clear()
    for title, url in parse_lines(raw_links):
        material.links.append(MaterialLink(title=title, url=url))

def _replace_videos(db: Session, material: Material, raw_videos: str):
    material.videos.clear()
    for title, url in parse_lines(raw_videos):
        material.videos.append(MaterialVideo(title=title, video_url=url, embed_url=url))

async def _append_files(material: Material, files: Optional[List[UploadFile]]):
    if not files:
        return
    for upload in files:
        saved = await save_upload_file(upload, "documents")
        if saved:
            material.files.append(MaterialFile(title=saved["original_name"], **saved))

def _unique_category_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    counter = 2
    while db.query(Category).filter(Category.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug
