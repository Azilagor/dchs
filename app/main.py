from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.bootstrap import ensure_seed_data
from app.config import BASE_DIR, SECRET_KEY, UPLOAD_DIR
from app.database import Base, SessionLocal, engine
from app.routers import admin, auth, public
from app.template_config import templates

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MCHS Directory")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax", https_only=False)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

app.include_router(auth.router)
app.include_router(public.router)
app.include_router(admin.router)


@app.on_event("startup")
def seed_default_data():
    db = SessionLocal()
    try:
        ensure_seed_data(db)
    finally:
        db.close()


@app.exception_handler(403)
def forbidden_handler(request: Request, exc):
    return templates.TemplateResponse(request, "errors/403.html", {"request": request, "current_user": None}, status_code=403)


@app.exception_handler(404)
def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(request, "errors/404.html", {"request": request, "current_user": None}, status_code=404)


@app.get("/health", response_class=HTMLResponse)
def health():
    return "OK"
