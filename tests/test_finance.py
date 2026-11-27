from decimal import Decimal

from agent.finance import assess_financial_feasibility, normalize_currency, to_usd, to_ves
from agent.schemas import TCO


def test_currency_normalization_supports_usd_and_ves_markers():
    assert normalize_currency("USD") == "USD"
    assert normalize_currency("Bs. S") == "VES"
    assert normalize_currency("$") == "USD"
    assert normalize_currency("USD / VES") is None


def test_ves_budget_is_compared_to_usd_tco_using_recorded_bcv_rate():
    assessment = assess_financial_feasibility(
        tco=TCO(base=116, flete=0, recargos=0, iva=16, total=116, moneda="USD"),
        proposal_currency="USD",
        budget_amount="50000",
        budget_currency="VES",
        bcv_rate="50",
        bcv_date="2026-11-27",
        bcv_source="BCV",
    )
    assert assessment.estado == "dentro_presupuesto"
    assert assessment.presupuesto_usd == 1000
    assert assessment.diferencia_usd == 884
    assert assessment.tco_ves == 5800


def test_ves_offer_is_normalized_to_usd_and_marked_over_budget():
    assessment = assess_financial_feasibility(
        tco=TCO(base=50000, flete=0, recargos=0, iva=0, total=50000, moneda="VES"),
        proposal_currency="VES",
        budget_amount="900",
        budget_currency="USD",
        bcv_rate="50",
        bcv_date="2026-11-27",
        bcv_source="BCV",
    )
    assert assessment.estado == "sobre_presupuesto"
    assert assessment.tco_usd == 1000
    assert assessment.diferencia_usd == -100


def test_incomplete_tco_cannot_be_certified_as_within_budget():
    assessment = assess_financial_feasibility(
        tco=TCO(
            base=100,
            flete=0,
            recargos=0,
            iva=0,
            total=100,
            moneda="USD",
            completo=False,
            advertencias=["Flete pendiente"],
        ),
        proposal_currency="USD",
        budget_amount="200",
        budget_currency="USD",
        bcv_rate="50",
        bcv_date="2026-11-27",
        bcv_source="BCV",
    )
    assert assessment.estado == "no_concluyente"
    assert assessment.diferencia_usd is None


def test_conversion_rejects_unknown_currency_and_rounds_to_cents():
    assert to_usd("10", "EUR", "50") is None
    assert to_usd("1001", "VES", "50") == Decimal("20.02")
    assert to_ves("20.02", "50") == Decimal("1001.00")
