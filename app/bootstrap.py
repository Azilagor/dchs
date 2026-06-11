import os

from sqlalchemy.orm import Session

from app.models import Category, Department, Material, User
from app.search_index import refresh_material_search_text
from app.security import hash_password
from app.utils import slugify, unique_material_slug


def ensure_seed_data(db: Session) -> tuple[str, str]:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@mchs.local")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin12345")

    admin = db.query(User).filter(User.email == admin_email).first()
    if not admin:
        admin = User(
            email=admin_email,
            full_name="Администратор",
            hashed_password=hash_password(admin_password),
            role="admin",
        )
        db.add(admin)
        db.flush()

    categories = [
        (
            "Государственный инспектор в области пожарной безопасности",
            "Нормативные материалы, приказы, инструкции и служебные документы по направлению пожарной безопасности.",
        ),
        (
            "Сотрудникам Службы пожаротушения и аварийно-спасательных работ",
            "Оперативные материалы, методические документы и полезные рабочие подборки для подразделений службы.",
        ),
        ("Пожарная безопасность", "Инструкции, памятки и регламенты по пожарной безопасности"),
        ("Гражданская оборона", "Материалы по гражданской обороне и ЧС"),
        ("Первая помощь", "Памятки и инструкции по первой помощи"),
        ("Приказы", "Внутренние и публичные приказы"),
        ("Видеоинструкции", "Обучающие видео и записи инструктажей"),
    ]
    for order, (name, description) in enumerate(categories):
        if not db.query(Category).filter(Category.name == name).first():
            db.add(Category(name=name, slug=slugify(name), description=description, sort_order=order))

    if not db.query(Department).filter(Department.name == "Учебно-методический отдел").first():
        db.add(
            Department(
                name="Учебно-методический отдел",
                description="Ответственный отдел за справочные материалы",
            )
        )

    db.commit()

    if db.query(Material).count() == 0:
        category = db.query(Category).filter(Category.name == "Пожарная безопасность").first()
        material = Material(
            title="Памятка по действиям при пожаре",
            slug=unique_material_slug(db, "Памятка по действиям при пожаре"),
            material_type="instruction",
            status="published",
            visibility="public",
            category_id=category.id if category else None,
            short_description="Краткая инструкция для сотрудников и посетителей.",
            content=(
                "1. Сохраняйте спокойствие.\n"
                "2. Сообщите о пожаре ответственному лицу.\n"
                "3. Используйте ближайший эвакуационный выход.\n"
                "4. Не пользуйтесь лифтом.\n"
                "5. После эвакуации следуйте указаниям ответственных лиц."
            ),
            created_by_id=admin.id,
            updated_by_id=admin.id,
            is_pinned=True,
        )
        refresh_material_search_text(material)
        db.add(material)
        db.commit()

    return admin_email, admin_password
