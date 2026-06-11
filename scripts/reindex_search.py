import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import joinedload

from app.database import SessionLocal, ensure_runtime_schema
from app.models import Material
from app.search_index import refresh_file_extracted_text, refresh_material_search_text


def main():
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        materials = (
            db.query(Material)
            .options(
                joinedload(Material.category),
                joinedload(Material.department),
                joinedload(Material.tags),
                joinedload(Material.files),
                joinedload(Material.links),
                joinedload(Material.videos),
            )
            .all()
        )
        for material in materials:
            for file in material.files:
                refresh_file_extracted_text(file)
            refresh_material_search_text(material)
        db.commit()
        print(f"Reindexed materials: {len(materials)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
