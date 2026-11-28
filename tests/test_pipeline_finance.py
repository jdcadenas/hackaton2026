from types import SimpleNamespace

from agent.pipeline import run_pipeline
from agent.schemas import (
    Clausula,
    ClausulaCategoria,
    Evidencia,
    Item,
    ProjectRequirement,
    ProjectRequirements,
    PropuestaExtraida,
    TotalesDeclarados,
)
from agent.status import EstadoDocumento
from tests.conftest import evidencia, propuesta


def test_pipeline_persists_bcv_budget_and_market_comparisons(tmp_path, monkeypatch):
    proposal_dir = tmp_path / "propuestas"
    proposal_dir.mkdir()
    (proposal_dir / "oferta.pdf").write_bytes(b"fixture")
    evidence = Evidencia(archivo="oferta.pdf", pagina=1, confianza=0.9)
    offer = PropuestaExtraida(
        archivo="oferta.pdf",
        fuente="pdf",
        proveedor="Acme",
        ubicacion_proveedor="Caracas",
        moneda="USD",
        items=[
            Item(
                descripcion="Laptop empresarial 16GB",
                cantidad=1,
                unidad="unidad",
                precio_unitario=120,
                subtotal=120,
                evidencia=evidence,
            )
        ],
        clausulas=[
            Clausula(
                texto="No incluye flete",
                categoria=ClausulaCategoria.flete,
                evidencia=evidence,
            )
        ],
        totales_declarados=TotalesDeclarados(subtotal=120, impuestos=19.2, total=139.2),
    )
    monkeypatch.setattr("agent.pipeline.extract_proposal", lambda *_args, **_kwargs: offer)
    monkeypatch.setattr(
        "agent.pipeline.research_market_price",
        lambda *_args, **_kwargs: SimpleNamespace(
            confianza=0.8,
            precios_encontrados=[
                SimpleNamespace(url="https://shop.example/1", precio_usd=80, fecha_consulta="2026-11-27"),
                SimpleNamespace(url="https://shop.example/2", precio_usd=90, fecha_consulta="2026-11-27"),
                SimpleNamespace(url="https://shop.example/3", precio_usd=100, fecha_consulta="2026-11-27"),
            ],
        ),
    )
    requirements = ProjectRequirements(
        archivo="requerimientos.pdf",
        requisitos=[
            ProjectRequirement(
                descripcion="Laptop empresarial",
                cantidad=1,
                evidencia=Evidencia(archivo="requerimientos.pdf", pagina=2, confianza=0.9),
            )
        ],
    )
    context = {
        "execution_city": "Caracas",
        "execution_state": "Distrito Capital",
        "budget_amount": "10000",
        "budget_currency": "VES",
        "bcv_rate": 50,
        "bcv_date": "2026-11-27",
        "bcv_source": "BCV",
    }
    trace = []

    audits, _ = run_pipeline(
        str(tmp_path),
        progress=lambda stage, message: trace.append((stage, message)),
        project_context=context,
        project_requirements=requirements,
        freight_quotes={
            "oferta.pdf": {
                "amount": "25",
                "currency": "USD",
                "date": "2026-11-27",
                "source": "Cotización Transportes",
            }
        },
    )

    audit = audits[0]
    assert audit.factibilidad_financiera.estado == "dentro_presupuesto"
    assert audit.factibilidad_financiera.tco_usd == 164.2
    assert audit.tco.flete == 25
    assert audit.factibilidad_financiera.tasa_bcv_ves_por_usd == 50
    assert audit.precios_mercado[0].estado == "sobre_rango_observado"
    assert len(audit.precios_mercado[0].fuentes) == 3
    assert audit.alcance_estado == "cumple"
    assert {"extraccion", "validacion", "tco", "mercado", "completado"} <= {
        stage for stage, _ in trace
    }
    assert any("Cotización Transportes" in message and "25.00 USD" in message for _, message in trace)


def test_pipeline_does_not_discard_on_low_confidence_project_requirements(tmp_path, monkeypatch):
    proposal_dir = tmp_path / "propuestas"
    proposal_dir.mkdir()
    (proposal_dir / "oferta.pdf").write_bytes(b"fixture")
    offer = propuesta(items=[
        Item(
            descripcion="Laptop empresarial",
            cantidad=1,
            unidad="unidad",
            precio_unitario=100,
            subtotal=100,
            evidencia=evidencia(),
        )
    ], subtotal=100, impuestos=16, total=116)
    monkeypatch.setattr("agent.pipeline.extract_proposal", lambda *_args, **_kwargs: offer)
    monkeypatch.setattr(
        "agent.pipeline.research_market_price",
        lambda *_args, **_kwargs: SimpleNamespace(confianza=0.1, precios_encontrados=[]),
    )
    requirements = ProjectRequirements(
        archivo="requerimientos.pdf",
        requisitos=[
            ProjectRequirement(
                descripcion="Laptop empresarial",
                evidencia=Evidencia(archivo="requerimientos.pdf", pagina=None, confianza=0.5),
            )
        ],
    )

    audits, _ = run_pipeline(str(tmp_path), project_requirements=requirements)

    assert not audits[0].descartada
    assert audits[0].alcance_estado == "no_concluyente"
    assert audits[0].alcance_advertencias


def test_pipeline_keeps_api_503_proposal_retryable_and_out_of_ranking(tmp_path, monkeypatch):
    proposal_dir = tmp_path / "propuestas"
    proposal_dir.mkdir()
    (proposal_dir / "oferta.pdf").write_bytes(b"fixture")
    failed_proposal = PropuestaExtraida(
        archivo="oferta.pdf",
        fuente="pdf",
        anomalias_ingesta=["Gemini no disponible: 503 UNAVAILABLE"],
    )
    failed_proposal._estado_evaluacion = EstadoDocumento.ERROR_API_503
    monkeypatch.setattr("agent.pipeline.extract_proposal", lambda *_args, **_kwargs: failed_proposal)

    audits, ranking = run_pipeline(str(tmp_path))

    assert audits[0].estado_documento == EstadoDocumento.ERROR_API_503
    assert not audits[0].descartada
    assert ranking == []
