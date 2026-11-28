import asyncio
import csv
import io
import json
import threading
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from agent.schemas import FinancialAssessment, ProjectRequirements, ResultadoAuditoria, TCO
from agent.status import EstadoDocumento
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
        evaluation_status=EstadoDocumento.COMPLETADO.value,
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
    assert proposal_record.evaluation_status == EstadoDocumento.PENDIENTE.value
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


def test_evaluation_start_preserves_completed_proposals_and_retry_status(monkeypatch):
    db = _session()
    project = Project(
        id="project-retry",
        title="Compra",
        status="Revisión",
        execution_city="Caracas",
        execution_state="Distrito Capital",
        budget_amount=500,
        budget_currency="USD",
        bcv_rate=50,
        bcv_date=date.today().isoformat(),
        bcv_source="BCV",
    )
    project_document = ProjectFile(
        id="requirements-retry",
        project_id=project.id,
        original_name="requerimientos.pdf",
        relative_path="requirements.enc",
        kind="proyecto",
        evaluation_status=EstadoDocumento.COMPLETADO.value,
    )
    completed = [
        _proposal(project.id, "proposal-done-1", "completada-1.pdf", "aceptar"),
        _proposal(project.id, "proposal-done-2", "completada-2.pdf", "observar"),
    ]
    retryable = _proposal(project.id, "proposal-retry", "fallida.pdf")
    retryable.evaluation_status = EstadoDocumento.ERROR_API_503.value
    retryable.audit_json = None
    completed_audits = {record.id: record.audit_json for record in completed}
    db.add_all([project, project_document, *completed, retryable])
    db.commit()
    monkeypatch.setattr(main, "_user", lambda _request: {"username": "carga", "role": "Carga"})
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    page_response = main.project_page(request, project.id, "evaluacion", db)
    assert b"Reintentar pendientes por error de servidor" in page_response.body

    class NoopThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon

        def start(self):
            pass

    monkeypatch.setattr(threading, "Thread", NoopThread)

    response = asyncio.run(
        main.evaluate_stream(
            request=object(),
            project_id=project.id,
            db=db,
        )
    )

    assert response.media_type == "text/event-stream"
    assert {record.id: record.audit_json for record in completed} == completed_audits
    assert all(record.evaluation_status == EstadoDocumento.COMPLETADO.value for record in completed)
    assert retryable.evaluation_status == EstadoDocumento.ERROR_API_503.value
    assert retryable.audit_json is None
    run = db.query(EvaluationRun).filter_by(project_id=project.id).one()
    assert run.status == "running"
    snapshot = json.loads(run.project_snapshot_json)
    assert {item["evaluation_status"] for item in snapshot["proposals"]} == {
        EstadoDocumento.COMPLETADO.value,
        EstadoDocumento.ERROR_API_503.value,
    }
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
    proposal_record.evaluation_status = EstadoDocumento.PENDIENTE.value
    failed_record = _proposal(project.id, "proposal-6-failed", "fallida.pdf")
    failed_record.evaluation_status = EstadoDocumento.ERROR_API_503.value
    failed_record.audit_json = None
    completed_record = _proposal(project.id, "proposal-6-completed", "oferta-completada.pdf", "aceptar")
    completed_record.evaluation_status = EstadoDocumento.COMPLETADO.value
    completed_audit_json = completed_record.audit_json
    run = EvaluationRun(
        id="run-6",
        project_id=project.id,
        run_number=1,
        status="running",
        project_snapshot_json=json.dumps(main._project_snapshot(project)),
    )
    db.add_all([project, project_file, proposal_record, failed_record, completed_record, run])
    db.commit()
    (tmp_path / "requirements.enc").write_bytes(b"encrypted")
    (tmp_path / proposal_record.relative_path).parent.mkdir(parents=True)
    (tmp_path / proposal_record.relative_path).write_bytes(b"encrypted")
    (tmp_path / failed_record.relative_path).write_bytes(b"encrypted")
    monkeypatch.setattr(main, "SessionLocal", lambda: Session(engine))
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "decrypt_bytes", lambda *_args: b"document")
    monkeypatch.setattr(
        main,
        "extract_project_requirements",
        lambda _path: ProjectRequirements(archivo="requerimientos.pdf"),
    )
    audit = ResultadoAuditoria.model_validate_json(_audit_json("oferta.pdf"))
    failed_audit = ResultadoAuditoria.model_validate_json(_audit_json("fallida.pdf"))
    failed_audit.estado_documento = EstadoDocumento.ERROR_API_503
    failed_audit.notas = "Error temporal de Gemini."
    processed_files = []
    audits_by_name = {
        "oferta.pdf": audit,
        "fallida.pdf": failed_audit,
    }

    def fake_run_pipeline(lote_dir, **_kwargs):
        filenames = [path.name for path in (Path(lote_dir) / "propuestas").iterdir()]
        processed_files.extend(filenames)
        document_audits = [audits_by_name[filename] for filename in filenames]
        return document_audits, [audit.propuesta.archivo for audit in document_audits]

    monkeypatch.setattr(main, "run_pipeline", fake_run_pipeline)

    main._evaluate(project.id, run.id, lambda *_args: None)
    db.refresh(project)
    db.refresh(proposal_record)
    db.refresh(failed_record)
    db.refresh(completed_record)
    db.refresh(run)

    archived_results = json.loads(run.results_json)
    assert project.status == "Revisión"
    assert run.status == "completed"
    assert run.completed_at is not None
    archived_by_id = {result["file_id"]: result for result in archived_results}
    assert archived_by_id[proposal_record.id]["original_name"] == "oferta.pdf"
    assert json.loads(archived_by_id[proposal_record.id]["audit_json"])["propuesta"]["archivo"] == "oferta.pdf"
    assert proposal_record.audit_json == archived_by_id[proposal_record.id]["audit_json"]
    assert proposal_record.evaluation_status == EstadoDocumento.COMPLETADO.value
    assert failed_record.evaluation_status == EstadoDocumento.ERROR_API_503.value
    assert not ResultadoAuditoria.model_validate_json(failed_record.audit_json).descartada
    assert completed_record.audit_json == completed_audit_json
    assert completed_record.review_decision == "aceptar"
    assert completed_record.evaluation_status == EstadoDocumento.COMPLETADO.value
    assert set(processed_files) == {"oferta.pdf", "fallida.pdf"}
    assert run.requirements_json is not None
    assert "- **Ejecución:** #1" in run.report_markdown
    db.close()
