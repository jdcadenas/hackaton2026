import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Generator

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from agent.status import EstadoDocumento


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
    awarded_proposal_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    adjudication_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    files: Mapped[list["ProjectFile"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="project")
    evaluation_runs: Mapped[list["EvaluationRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


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
    evaluation_status: Mapped[str] = mapped_column(
        String(24),
        default=EstadoDocumento.PENDIENTE.value,
        server_default=EstadoDocumento.PENDIENTE.value,
        nullable=False,
    )
    audit_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    freight_quote_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    freight_quote_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    freight_quote_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    freight_quote_source: Mapped[str | None] = mapped_column(String(500), nullable=True)
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


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        UniqueConstraint("project_id", "run_number", name="uq_evaluation_run_project_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    project_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    requirements_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    results_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    ranking_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[Project] = relationship(back_populates="evaluation_runs")


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    additions = {
        "execution_city": "VARCHAR(120)",
        "execution_state": "VARCHAR(120)",
        "budget_amount": "NUMERIC(18, 2)",
        "budget_currency": "VARCHAR(3)",
        "requirements_json": "TEXT",
        "awarded_proposal_id": "VARCHAR(36)",
        "adjudication_reason": "TEXT",
        "closure_reason": "TEXT",
        "closed_at": "TIMESTAMP",
    }
    with engine.begin() as connection:
        existing = {column["name"] for column in inspect(connection).get_columns("projects")}
        for column, sql_type in additions.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE projects ADD COLUMN {column} {sql_type}"))
        file_columns = {column["name"] for column in inspect(connection).get_columns("project_files")}
        file_additions = {
            "uploaded_at": "TIMESTAMP",
            "freight_quote_amount": "NUMERIC(18, 2)",
            "freight_quote_currency": "VARCHAR(3)",
            "freight_quote_date": "VARCHAR(10)",
            "freight_quote_source": "VARCHAR(500)",
            "evaluation_status": f"VARCHAR(24) NOT NULL DEFAULT '{EstadoDocumento.PENDIENTE.value}'",
        }
        added_evaluation_status = "evaluation_status" not in file_columns
        for column, sql_type in file_additions.items():
            if column not in file_columns:
                connection.execute(text(f"ALTER TABLE project_files ADD COLUMN {column} {sql_type}"))
        if added_evaluation_status:
            connection.execute(
                text(
                    "UPDATE project_files SET evaluation_status = 'COMPLETADO' "
                    "WHERE (kind = 'propuesta' AND audit_json IS NOT NULL) "
                    "OR (kind = 'proyecto' AND project_id IN "
                    "(SELECT id FROM projects WHERE requirements_json IS NOT NULL))"
                )
            )
        run_columns = {column["name"] for column in inspect(connection).get_columns("evaluation_runs")}
        if "report_markdown" not in run_columns:
            connection.execute(text("ALTER TABLE evaluation_runs ADD COLUMN report_markdown TEXT"))


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
