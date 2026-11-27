import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Generator

from sqlalchemy import DateTime, Float, ForeignKey, Numeric, String, Text, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


DATA_DIR = Path(os.environ.get("APP_DATA_DIR", "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}")
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Recepción", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    execution_city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    execution_state: Mapped[str | None] = mapped_column(String(120), nullable=True)
    budget_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    budget_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    bcv_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    bcv_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bcv_source: Mapped[str | None] = mapped_column(String(300), nullable=True)
    requirements_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    files: Mapped[list["ProjectFile"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="project")


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )
    quality: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    audit_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[Project] = relationship(back_populates="files")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    project: Mapped[Project] = relationship(back_populates="audit_events")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    additions = {
        "execution_city": "VARCHAR(120)",
        "execution_state": "VARCHAR(120)",
        "budget_amount": "NUMERIC(18, 2)",
        "budget_currency": "VARCHAR(3)",
        "requirements_json": "TEXT",
    }
    with engine.begin() as connection:
        existing = {column["name"] for column in inspect(connection).get_columns("projects")}
        for column, sql_type in additions.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE projects ADD COLUMN {column} {sql_type}"))
        file_columns = {column["name"] for column in inspect(connection).get_columns("project_files")}
        if "uploaded_at" not in file_columns:
            connection.execute(text("ALTER TABLE project_files ADD COLUMN uploaded_at TIMESTAMP"))


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
