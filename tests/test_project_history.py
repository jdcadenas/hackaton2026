import asyncio
import csv
import io
import json
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from agent.schemas import FinancialAssessment, ProjectRequirements, ResultadoAuditoria, TCO
from app import main
from app.db import AuditEvent, Base, EvaluationRun, Project, ProjectFile
from tests.conftest import propuesta


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return Session(engine)


def _audit_json(filename: str) -> str:
    offer = propuesta(archivo=filename)
    return ResultadoAuditoria(
        propuesta=offer,
        alcance_estado="cumple",
        tco=TCO(
            base=116,
            flete=0,
            recargos=0,
            iva=16,
            total=116,
            moneda="USD",
            completo=True,
        ),
        factibilidad_financiera=FinancialAssessment(
            estado="dentro_presupuesto",
            moneda_propuesta="USD",
            tco_propuesta=116,
            tco_usd=116,
            tco_ves=5800,
            presupuesto_original=500,
            moneda_presupuesto="USD",
            presupuesto_usd=500,
            diferencia_usd=384,
            tasa_bcv_ves_por_usd=50,
            tasa_bcv_fecha="2026-11-27",
            tasa_bcv_fuente="BCV",
        ),
    ).model_dump_json()


def _proposal(project_id: str, file_id: str, filename: str, decision: str | None = None) -> ProjectFile:
    return ProjectFile(
        id=file_id,
        project_id=project_id,
        original_name=filename,
        relative_path=f"uploads/{file_id}.enc",
        kind="propuesta",
        audit_json=_audit_json(filename),
        review_decision=decision,
    )


def test_archived_report_uses_immutable_project_and_audit_snapshot(monkeypatch):
    db = _session()
    project = Project(
        id="project-1",
        title="Compra original",
        status="Revisión",
        execution_city="Caracas",
        execution_state="Distrito Capital",
        budget_amount=500,
        budget_currency="USD",
        bcv_rate=50,
        bcv_date="2026-11-27",
        bcv_source="BCV",
    )
    proposal_record = _proposal(project.id, "proposal-1", "oferta.pdf")
    audit_json = proposal_record.audit_json
    run = EvaluationRun(
        id="run-1",
        project_id=project.id,
        run_number=1,
        status="completed",
        started_at=datetime(2026, 11, 27, 8, tzinfo=timezone.utc),
        completed_at=datetime(2026, 11, 27, 8, 1, tzinfo=timezone.utc),
        project_snapshot_json=json.dumps(
            {
                "id": project.id,
                "title": project.title,
                "execution_city": "Caracas",
                "execution_state": "Distrito Capital",
                "budget_amount": 500,
                "budget_currency": "USD",
                "bcv_rate": 50,
                "bcv_date": "2026-11-27",
                "bcv_source": "BCV",
            }
        ),
        results_json=json.dumps(
            [
                {
                    "file_id": proposal_record.id,
                    "original_name": proposal_record.original_name,
                    "audit_json": audit_json,
                    "review_decision": None,
                    "review_comment": None,
                }
            ]
        ),
        report_markdown="# Archived report\n",
    )
    db.add_all([project, proposal_record, run])
    db.commit()

    project.execution_city = "Maracaibo"
    project.budget_amount = 99
    proposal_record.audit_json = None
    db.commit()

    report_project, records, report_run, _ = main._report_source(db, project, run.id)
    report = main.build_financial_report(records)
    markdown = main.render_markdown(report_project, report)

    assert report_run.run_number == 1
    assert report_project.execution_city == "Caracas"
    assert report_project.budget_amount == 500
    assert records[0].audit_json == audit_json
    assert report["rows"][0]["audit"]["propuesta"]["archivo"] == "oferta.pdf"
    assert "**Ejecución:** #1" in markdown
    assert "Caracas, Distrito Capital" in markdown
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "aprobador", "role": "Aprobador"})
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    report_response = main.report_page(request, project.id, run.id, db)
    markdown_response = main.report_markdown(request, project.id, run.id, db)
    csv_response = main.report_csv(request, project.id, run.id, db)
    history_response = main.project_page(request, project.id, "revision", db)

    async def read_stream(response):
        chunks = [chunk async for chunk in response.body_iterator]
        return "".join(chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk for chunk in chunks)

    csv_rows = list(csv.reader(io.StringIO(asyncio.run(read_stream(csv_response)))))
    assert b"Informe hist" in report_response.body
    assert markdown_response.body == b"# Archived report\n"
    assert b"Historial de evaluaciones" in history_response.body
    assert b"Ver informe" in history_response.body
    assert len(csv_rows[0]) == len(csv_rows[1])
    assert csv_rows[1][0] == "1"
    assert csv_rows[1][3] == "Caracas"
    db.close()


def test_invalidating_current_evaluation_does_not_delete_run_snapshot():
    db = _session()
    project = Project(id="project-2", title="Compra", status="Revisión")
    proposal_record = _proposal(project.id, "proposal-2", "oferta.pdf", "aceptar")
    run = EvaluationRun(
        id="run-2",
        project_id=project.id,
        run_number=1,
        status="completed",
        project_snapshot_json=json.dumps({"id": project.id, "title": project.title}),
        results_json=json.dumps(
            [{
                "file_id": proposal_record.id,
                "original_name": proposal_record.original_name,
                "audit_json": proposal_record.audit_json,
                "review_decision": "aceptar",
                "review_comment": None,
            }]
        ),
    )
    db.add_all([project, proposal_record, run])
    db.commit()
    original_snapshot = run.results_json

    main._invalidate_evaluations(db, project, actor="carga", reason="Actualización de datos.")
    db.commit()
    db.refresh(proposal_record)
    db.refresh(run)

    assert proposal_record.audit_json is None
    assert proposal_record.review_decision is None
    assert run.results_json == original_snapshot
    assert project.status == "Recepción"
    db.close()


def test_commit_stage_requires_a_review_decision_for_every_proposal(monkeypatch):
    db = _session()
    project = Project(id="project-3", title="Compra", status="Revisión")
    proposals = [
        _proposal(project.id, "proposal-3a", "a.pdf"),
        _proposal(project.id, "proposal-3b", "b.pdf"),
    ]
    run = EvaluationRun(
        id="run-3",
        project_id=project.id,
        run_number=1,
        status="completed",
        project_snapshot_json="{}",
        results_json="[]",
    )
    db.add_all([project, *proposals, run])
    db.commit()
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "aprobador", "role": "Aprobador"})

    with pytest.raises(HTTPException) as error:
        main.transition_project(
            request=object(),
            project_id=project.id,
            target_status="Comité",
            reason="Presentar al comité",
            db=db,
        )

    assert error.value.status_code == 409
    for record in proposals:
        record.review_decision = "aceptar"
    response = main.transition_project(
        request=object(),
        project_id=project.id,
        target_status="Comité",
        reason="Presentar al comité",
        db=db,
    )

    assert response.status_code == 303
    assert project.status == "Comité"
    assert db.query(AuditEvent).filter_by(action="estado_cambiado").count() == 1
    db.close()


def test_adjudication_and_closure_require_valid_reasons(monkeypatch):
    db = _session()
    project = Project(id="project-4", title="Compra", status="Comité")
    accepted = _proposal(project.id, "proposal-4", "elegible.pdf", "aceptar")
    db.add_all([project, accepted])
    db.commit()
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "aprobador", "role": "Aprobador"})

    awarded = main.transition_project(
        request=object(),
        project_id=project.id,
        target_status="Adjudicado",
        reason="Mejor opción evaluada",
        awarded_proposal_id=accepted.id,
        db=db,
    )
    assert awarded.status_code == 303
    assert project.status == "Adjudicado"
    assert project.awarded_proposal_id == accepted.id

    with pytest.raises(HTTPException) as error:
        main.transition_project(
            request=object(),
            project_id=project.id,
            target_status="Cerrado",
            reason="Cierre",
            closure_reason="",
            db=db,
        )
    assert error.value.status_code == 400

    closed = main.transition_project(
        request=object(),
        project_id=project.id,
        target_status="Cerrado",
        reason="Proceso concluido",
        closure_reason="Contrato emitido y compra concluida",
        db=db,
    )
    assert closed.status_code == 303
    assert project.status == "Cerrado"
    assert project.closure_reason == "Contrato emitido y compra concluida"
    assert project.closed_at is not None
    db.close()


def test_award_rejects_proposals_without_review_acceptance(monkeypatch):
    db = _session()
    project = Project(id="project-5", title="Compra", status="Comité")
    proposal_record = _proposal(project.id, "proposal-5", "sin-aceptacion.pdf")
    db.add_all([project, proposal_record])
    db.commit()
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "aprobador", "role": "Aprobador"})

    with pytest.raises(HTTPException) as error:
        main.transition_project(
            request=object(),
            project_id=project.id,
            target_status="Adjudicado",
            reason="Selección",
            awarded_proposal_id=proposal_record.id,
            db=db,
        )

    assert error.value.status_code == 409
    assert project.status == "Comité"
    db.close()


def test_committee_can_close_without_adjudication(monkeypatch):
    db = _session()
    project = Project(id="project-7", title="Compra", status="Comité")
    db.add(project)
    db.commit()
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "aprobador", "role": "Aprobador"})

    response = main.transition_project(
        request=object(),
        project_id=project.id,
        target_status="Cerrado",
        reason="No hubo ofertas elegibles",
        closure_reason="Proceso desierto",
        db=db,
    )

    assert response.status_code == 303
    assert project.status == "Cerrado"
    assert project.awarded_proposal_id is None
    assert project.closure_reason == "Proceso desierto"
    db.close()


def test_startup_recovers_interrupted_evaluation(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    project = Project(id="project-8", title="Compra", status="Evaluación")
    run = EvaluationRun(
        id="run-8",
        project_id=project.id,
        run_number=1,
        status="running",
        project_snapshot_json="{}",
    )
    db.add_all([project, run])
    db.commit()
    monkeypatch.setattr(main, "SessionLocal", lambda: Session(engine))

    main._recover_interrupted_evaluations()
    db.refresh(project)
    db.refresh(run)

    assert project.status == "Recepción"
    assert run.status == "failed"
    assert "interrumpió" in run.error
    assert db.query(AuditEvent).filter_by(action="evaluacion_interrumpida").count() == 1
    db.close()


def test_evaluate_persists_run_snapshot_and_advances_project(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    today = date.today().isoformat()
    project = Project(
        id="project-6",
        title="Compra",
        status="Evaluación",
        execution_city="Caracas",
        execution_state="Distrito Capital",
        budget_amount=500,
        budget_currency="USD",
        bcv_rate=50,
        bcv_date=today,
        bcv_source="BCV",
    )
    project_file = ProjectFile(
        id="requirements-6",
        project_id=project.id,
        original_name="requerimientos.pdf",
        relative_path="requirements.enc",
        kind="proyecto",
    )
    proposal_record = _proposal(project.id, "proposal-6", "oferta.pdf")
    run = EvaluationRun(
        id="run-6",
        project_id=project.id,
        run_number=1,
        status="running",
        project_snapshot_json=json.dumps(main._project_snapshot(project)),
    )
    db.add_all([project, project_file, proposal_record, run])
    db.commit()
    (tmp_path / "requirements.enc").write_bytes(b"encrypted")
    (tmp_path / proposal_record.relative_path).parent.mkdir(parents=True)
    (tmp_path / proposal_record.relative_path).write_bytes(b"encrypted")
    monkeypatch.setattr(main, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "decrypt_bytes", lambda *_args: b"document")
    monkeypatch.setattr(
        main,
        "extract_project_requirements",
        lambda _path: ProjectRequirements(archivo="requerimientos.pdf"),
    )
    audit = ResultadoAuditoria.model_validate_json(_audit_json("oferta.pdf"))
    monkeypatch.setattr(main, "run_pipeline", lambda *_args, **_kwargs: ([audit], ["oferta.pdf"]))

    main._evaluate(project.id, run.id, lambda *_args: None)
    db.refresh(project)
    db.refresh(proposal_record)
    db.refresh(run)

    archived_results = json.loads(run.results_json)
    assert project.status == "Revisión"
    assert run.status == "completed"
    assert run.completed_at is not None
    assert archived_results[0]["file_id"] == proposal_record.id
    assert json.loads(archived_results[0]["audit_json"])["propuesta"]["archivo"] == "oferta.pdf"
    assert proposal_record.audit_json == archived_results[0]["audit_json"]
    assert run.requirements_json is not None
    assert "- **Ejecución:** #1" in run.report_markdown
    db.close()
