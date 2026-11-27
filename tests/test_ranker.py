from agent.schemas import FinancialAssessment, ResultadoAuditoria, TCO
from agent.ranker import rank_audits
from tests.conftest import propuesta


def audit(name, discarded=False, score=0, total=100):
    result = ResultadoAuditoria(
        propuesta=propuesta(archivo=name),
        descartada=discarded,
        technical_score=score,
    )
    result.tco = TCO(base=total, flete=0, recargos=0, iva=0, total=total)
    return result


def test_ranker_places_valid_before_discarded():
    assert rank_audits([audit("bad.pdf", True), audit("ok.pdf", score=1)]) == ["ok.pdf", "bad.pdf"]


def test_ranker_breaks_score_ties_by_tco_then_name():
    assert rank_audits([
        audit("c.pdf", score=10, total=90),
        audit("b.pdf", score=10, total=80),
        audit("a.pdf", score=10, total=80),
    ]) == ["a.pdf", "b.pdf", "c.pdf"]


def test_ranker_prefers_higher_technical_score():
    assert rank_audits([audit("a.pdf", score=50, total=50), audit("b.pdf", score=80, total=90)]) == ["b.pdf", "a.pdf"]


def test_ranker_has_no_duplicate_names():
    assert rank_audits([audit("same.pdf", score=1), audit("same.pdf", discarded=True)]) == ["same.pdf"]


def test_ranker_places_fully_assessed_before_inconclusive_audits():
    confirmed = audit("confirmed.pdf", score=100)
    confirmed.alcance_estado = "cumple"
    confirmed.factibilidad_financiera = FinancialAssessment(
        estado="dentro_presupuesto",
        presupuesto_original=100,
        moneda_presupuesto="USD",
        presupuesto_usd=100,
        tasa_bcv_ves_por_usd=50,
        tasa_bcv_fecha="2026-01-01",
        tasa_bcv_fuente="BCV",
    )
    inconclusive = audit("inconclusive.pdf", score=100)

    assert rank_audits([inconclusive, confirmed]) == ["confirmed.pdf", "inconclusive.pdf"]


def test_ranker_prefers_within_budget_audits():
    within_budget = audit("within.pdf", score=100)
    over_budget = audit("over.pdf", score=100)
    for result, state in (
        (within_budget, "dentro_presupuesto"),
        (over_budget, "sobre_presupuesto"),
    ):
        result.alcance_estado = "cumple"
        result.factibilidad_financiera = FinancialAssessment(
            estado=state,
            presupuesto_original=100,
            moneda_presupuesto="USD",
            presupuesto_usd=100,
            tasa_bcv_ves_por_usd=50,
            tasa_bcv_fecha="2026-01-01",
            tasa_bcv_fuente="BCV",
        )

    assert rank_audits([over_budget, within_budget]) == ["within.pdf", "over.pdf"]
