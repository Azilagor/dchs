from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass


def ensure_runtime_schema():
    required_columns = {
        "materials": {
            "search_text": "TEXT",
        },
        "material_files": {
            "extracted_text": "TEXT",
        },
        "categories": {
            "featured_on_home": "BOOLEAN DEFAULT 0",
        },
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        for table_name, columns in required_columns.items():
            existing = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in columns.items():
                if column_name not in existing:
                    connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
