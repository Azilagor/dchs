from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from app.database import Base

material_tags = Table(
    "material_tags",
    Base.metadata,
    Column("material_id", ForeignKey("materials.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), default="staff", nullable=False)  # admin, moderator, editor, staff
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    created_materials = relationship("Material", foreign_keys="Material.created_by_id", back_populates="created_by")
    updated_materials = relationship("Material", foreign_keys="Material.updated_by_id", back_populates="updated_by")

class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)

    materials = relationship("Material", back_populates="department")


class HeroSlide(Base):
    __tablename__ = "hero_slides"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    subtitle = Column(String(500), nullable=True)
    image_path = Column(String(1000), nullable=False)
    image_name = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)

    parent = relationship("Category", remote_side=[id], backref="children")
    materials = relationship("Material", back_populates="category")

class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, index=True, nullable=False)

    materials = relationship("Material", secondary=material_tags, back_populates="tags")

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    slug = Column(String(500), unique=True, index=True, nullable=False)
    material_type = Column(String(50), index=True, nullable=False)  # document, instruction, order, video, link, article, faq, template
    status = Column(String(50), index=True, default="draft", nullable=False)  # draft, review, published, archived
    visibility = Column(String(50), index=True, default="public", nullable=False)  # public, internal
    short_description = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    search_text = Column(Text, nullable=True)
    order_number = Column(String(100), nullable=True)
    is_pinned = Column(Boolean, default=False, nullable=False)
    views_count = Column(Integer, default=0, nullable=False)

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    category = relationship("Category", back_populates="materials")
    department = relationship("Department", back_populates="materials")
    created_by = relationship("User", foreign_keys=[created_by_id], back_populates="created_materials")
    updated_by = relationship("User", foreign_keys=[updated_by_id], back_populates="updated_materials")
    tags = relationship("Tag", secondary=material_tags, back_populates="materials")
    files = relationship("MaterialFile", back_populates="material", cascade="all, delete-orphan")
    links = relationship("MaterialLink", back_populates="material", cascade="all, delete-orphan")
    videos = relationship("MaterialVideo", back_populates="material", cascade="all, delete-orphan")
    versions = relationship("MaterialVersion", back_populates="material", cascade="all, delete-orphan", order_by="desc(MaterialVersion.version_number)")

class MaterialFile(Base):
    __tablename__ = "material_files"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    original_name = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    file_type = Column(String(100), nullable=True)
    size_bytes = Column(Integer, nullable=True)
    extracted_text = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    material = relationship("Material", back_populates="files")

class MaterialLink(Base):
    __tablename__ = "material_links"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    url = Column(String(1000), nullable=False)

    material = relationship("Material", back_populates="links")

class MaterialVideo(Base):
    __tablename__ = "material_videos"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=True)
    video_url = Column(String(1000), nullable=True)
    embed_url = Column(String(1000), nullable=True)
    video_file_path = Column(String(1000), nullable=True)

    material = relationship("Material", back_populates="videos")

class MaterialVersion(Base):
    __tablename__ = "material_versions"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("materials.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    short_description = Column(Text, nullable=True)
    changed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    material = relationship("Material", back_populates="versions")
    changed_by = relationship("User")
