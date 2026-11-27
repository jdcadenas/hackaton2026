from types import SimpleNamespace

from agent.schemas import (
    ArithmeticAssessment,
    FinancialAssessment,
    MarketPriceReview,
    PriceSource,
    ResultadoAuditoria,
    TCO,
)
from app.financial_report import build_financial_report, render_markdown
from tests.conftest import evidencia, propuesta


def _audit(name, subtotal, freight=0, budget=500, scope="cumple", discarded=False, market=None):
    tax = subtotal * 0.16
    offer = propuesta(
        archivo=name,
        items=[{
            "descripcion": "Equipo",
            "cantidad": 1,
            "unidad": "unidad",
            "precio_unitario": subtotal,
            "subtotal": subtotal,
            "evidencia": evidencia(),
        }],
        subtotal=subtotal,
        impuestos=tax,
        total=subtotal + tax,
    )
    result = ResultadoAuditoria(
        propuesta=offer,
        descartada=discarded,
        motivos_descarte=["Discrepancia aritmética."] if discarded else [],
        alcance_estado=scope,
        technical_score=100 if not discarded else 0,
        aritmetica=ArithmeticAssessment(
            estado="discrepancia" if discarded else "cumple",
            subtotal_items_calculado=subtotal,
            subtotal_items_declarado=subtotal,
            subtotal_declarado=subtotal,
            diferencia_subtotal=0,
            total_recalculado=subtotal + tax,
            total_declarado=subtotal + tax,
            diferencia_total=0,
            motivos=["Subtotal de ítem no coincide."] if discarded else [],
        ),
        tco=TCO(
            base=subtotal,
            flete=freight,
            recargos=0,
            iva=tax,
            total=subtotal + tax + freight,
            moneda="USD",
            completo=True,
        ),
        factibilidad_financiera=FinancialAssessment(
            estado="dentro_presupuesto" if subtotal + tax + freight <= budget else "sobre_presupuesto",
            moneda_propuesta="USD",
            tco_propuesta=subtotal + tax + freight,
            tco_usd=subtotal + tax + freight,
            tco_ves=(subtotal + tax + freight) * 50,
            presupuesto_original=budget,
            moneda_presupuesto="USD",
            presupuesto_usd=budget,
            diferencia_usd=budget - subtotal - tax - freight,
            tasa_bcv_ves_por_usd=50,
            tasa_bcv_fecha="2026-11-27",
            tasa_bcv_fuente="BCV",
        ),
        precios_mercado=market or [],
    )
    return result


def _record(name, audit):
    return SimpleNamespace(
        id=name,
        original_name=name,
        audit_json=audit.model_dump_json() if audit else None,
    )


def test_report_recommends_lowest_eligible_tco_and_explains_market_premium():
    market = MarketPriceReview(
        componente="Equipo",
        precio_ofertado_usd=100,
        minimo_mercado_usd=40,
        promedio_mercado_usd=50,
        maximo_mercado_usd=60,
        confianza=0.9,
        estado="sobre_rango_observado",
        fuentes=[PriceSource(url="https://market.example/item", precio_usd=50, fecha_consulta="2026-11-27")],
    )
    cheaper = _audit("mejor.pdf", subtotal=100, market=[market])
    costlier = _audit("otra.pdf", subtotal=150, freight=20)

    report = build_financial_report([_record("otra.pdf", costlier), _record("mejor.pdf", cheaper)])

    assert report["recommendation"]["archivo"] == "mejor.pdf"
    assert report["recommendation"]["advertencias"][0]["sobreprecio_pct"] == 100
    assert [row["file"].original_name for row in report["rows"]] == ["mejor.pdf", "otra.pdf"]
    assert "Posición 2" in report["rows"][1]["dictamen"]
    assert "20.00 USD de flete" in report["rows"][1]["dictamen"]


def test_report_does_not_recommend_incomplete_or_discarded_proposals():
    incomplete = _audit("incompleta.pdf", subtotal=100, scope="no_concluyente")
    discarded = _audit("descartada.pdf", subtotal=80, discarded=True)

    report = build_financial_report([
        _record("incompleta.pdf", incomplete),
        _record("descartada.pdf", discarded),
    ])

    assert report["recommendation"] is None
    assert "alcance no concluyente" in report["rows"][0]["dictamen"]
    assert "Discrepancia aritmética." in report["rows"][1]["dictamen"]


def test_report_distinguishes_declared_and_recalculated_budget_balance():
    audit = _audit("discrepante.pdf", subtotal=100)
    audit.propuesta.items[0].precio_unitario = 150
    audit.aritmetica = None

    report = build_financial_report([_record("discrepante.pdf", audit)])
    row = report["rows"][0]

    assert report["recommendation"] is None
    assert row["tco_recalculado"]["diferencia_presupuesto_usd"] == 334
    assert row["audit"]["factibilidad_financiera"]["diferencia_usd"] == 384


def test_markdown_export_contains_recommendation_matrix_and_disclaimers():
    report_data = build_financial_report([_record("mejor.pdf", _audit("mejor.pdf", subtotal=100))])
    project = SimpleNamespace(
        title="Compra de equipos",
        execution_city="Caracas",
        execution_state="Distrito Capital",
        budget_amount=500,
        budget_currency="USD",
        bcv_rate=50,
        bcv_date="2026-11-27",
        bcv_source="BCV",
    )

    markdown = render_markdown(project, report_data)

    assert "## Propuesta recomendada" in markdown
    assert "## Comparación de propuestas" in markdown
    assert "Subtotal recalculado" in markdown
    assert "Saldo presupuesto recalculado USD" in markdown
    assert "no se corrige silenciosamente" in markdown
    table_lines = [line for line in markdown.splitlines() if line.startswith("|")]
    assert len(table_lines[0].split("|")) == len(table_lines[2].split("|"))
