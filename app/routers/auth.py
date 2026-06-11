from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import (
    clear_login_attempts,
    ensure_login_allowed,
    get_current_user,
    register_failed_login,
    validate_csrf,
    verify_password,
)
from app.template_config import templates

router = APIRouter()


@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db)):
    current_user = get_current_user(request, db)
    if current_user:
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request, "auth/login.html", {"request": request, "error": None, "current_user": None})


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    validate_csrf(request, csrf_token)
    try:
        ensure_login_allowed(request, email)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"request": request, "error": exc.detail, "current_user": None},
            status_code=exc.status_code,
        )

    user = db.query(User).filter(User.email == email, User.is_active.is_(True)).first()
    if not user or not verify_password(password, user.hashed_password):
        register_failed_login(request, email)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"request": request, "error": "Неверный email или пароль", "current_user": None},
            status_code=400,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    clear_login_attempts(request, email)
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
