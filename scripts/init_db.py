import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.bootstrap import ensure_seed_data
from app.database import Base, SessionLocal, engine

Base.metadata.create_all(bind=engine)


def main():
    db = SessionLocal()
    try:
        admin_email, admin_password = ensure_seed_data(db)
        print("База данных инициализирована")
        print(f"Админ: {admin_email}")
        print(f"Пароль: {admin_password}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
