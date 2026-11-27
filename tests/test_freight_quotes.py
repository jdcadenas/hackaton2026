from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app import main
from app.db import AuditEvent, Base, Project, ProjectFile


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def test_saving_freight_quote_persists_provenance_and_invalidates_old_audit(monkeypatch):
    db = _session()
    project = Project(id="project-1", title="Compra", status="Revisión")
    proposal = ProjectFile(
        id="proposal-1",
        project_id=project.id,
        original_name="oferta.pdf",
        relative_path="uploads/proposal.enc",
        kind="propuesta",
        quality="verde",
        audit_json="{}",
        review_decision="aceptar",
    )
    db.add_all([project, proposal])
    db.commit()
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "carga", "role": "Carga"})

    response = main.save_freight_quote(
        request=object(),
        project_id=project.id,
        file_id=proposal.id,
        amount="1250.00",
        currency="VES",
        quote_date=date.today().isoformat(),
        source="Cotización Transportes",
        db=db,
    )

    db.refresh(proposal)
    db.refresh(project)
    assert response.status_code == 303
    assert str(proposal.freight_quote_amount) == "1250.00"
    assert proposal.freight_quote_currency == "VES"
    assert proposal.freight_quote_source == "Cotización Transportes"
    assert proposal.audit_json is None
    assert proposal.review_decision is None
    assert project.status == "Recepción"
    assert db.query(AuditEvent).filter_by(action="cotizacion_flete_actualizada").count() == 1
    db.close()


def test_init_db_adds_freight_quote_fields_to_legacy_schema(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY, title VARCHAR(200))")
        connection.exec_driver_sql(
            "CREATE TABLE project_files ("
            "id VARCHAR(36) PRIMARY KEY, project_id VARCHAR(36), original_name VARCHAR(255), "
            "relative_path VARCHAR(500), kind VARCHAR(20), quality VARCHAR(20), audit_json TEXT, "
            "review_decision VARCHAR(30), review_comment TEXT)"
        )
    monkeypatch.setattr(db_module, "engine", engine)

    db_module.init_db()

    names = {column["name"] for column in db_module.inspect(engine).get_columns("project_files")}
    assert {
        "uploaded_at",
        "freight_quote_amount",
        "freight_quote_currency",
        "freight_quote_date",
        "freight_quote_source",
    } <= names
    project_names = {column["name"] for column in db_module.inspect(engine).get_columns("projects")}
    assert {
        "awarded_proposal_id",
        "adjudication_reason",
        "closure_reason",
        "closed_at",
    } <= project_names
    assert "evaluation_runs" in db_module.inspect(engine).get_table_names()
    run_columns = {column["name"] for column in db_module.inspect(engine).get_columns("evaluation_runs")}
    assert {"results_json", "project_snapshot_json", "report_markdown"} <= run_columns
