from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import PAGE_SIZE
from app.database import get_db
from app.models import Category, Material, Tag
from app.security import get_current_user
from app.template_config import templates

router = APIRouter()

MATERIAL_TYPES = ["document", "instruction", "order", "video", "link", "article", "faq", "template"]
SITE_ASSETS = {
    "logo.jpg": Path("logo.jpg"),
    "photo1.jpeg": Path("photo1.jpeg"),
    "photo2.jpeg": Path("photo2.jpeg"),
}

def accessible_materials(db: Session, current_user):
    query = db.query(Material).options(joinedload(Material.category), joinedload(Material.tags)).filter(Material.status == "published")
    if not current_user:
        query = query.filter(Material.visibility == "public")
    return query

@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    base = accessible_materials(db, current_user)
    pinned_materials = base.filter(Material.is_pinned.is_(True)).order_by(Material.published_at.desc().nullslast()).limit(6).all()
    latest_materials = base.order_by(Material.published_at.desc().nullslast(), Material.created_at.desc()).limit(8).all()
    popular_materials = base.order_by(Material.views_count.desc(), Material.created_at.desc()).limit(5).all()
    categories = db.query(Category).filter(Category.is_active.is_(True)).order_by(Category.sort_order, Category.name).all()
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
        },
    )


@router.get("/site-assets/{filename}")
def site_asset(filename: str):
    asset_path = SITE_ASSETS.get(filename)
    if not asset_path or not asset_path.exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(asset_path)

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
        pattern = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Material.title.ilike(pattern),
                Material.short_description.ilike(pattern),
                Material.content.ilike(pattern),
                Material.order_number.ilike(pattern),
            )
        )
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
        return templates.TemplateResponse(request,"errors/404.html", {"request": request, "current_user": current_user}, status_code=404)

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
    return templates.TemplateResponse(request,"categories/list.html", {"request": request, "current_user": current_user, "categories": categories})

@router.get("/categories/{slug}")
def category_detail(slug: str, request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    category = db.query(Category).filter(Category.slug == slug, Category.is_active.is_(True)).first()
    if not category:
        return templates.TemplateResponse(request,"errors/404.html", {"request": request, "current_user": current_user}, status_code=404)
    materials = accessible_materials(db, current_user).filter(Material.category_id == category.id).order_by(Material.published_at.desc().nullslast()).all()
    return templates.TemplateResponse(request,"categories/detail.html", {"request": request, "current_user": current_user, "category": category, "materials": materials})
