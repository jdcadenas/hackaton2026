import pytest

from agent.schemas import ClausulaCategoria
from agent.tco import calculate_tco
from tests.conftest import clausula, propuesta


def test_tco_without_hidden_costs():
    result = calculate_tco(propuesta())
    assert result.flete == 0
    assert result.recargos == 0
    assert result.total == pytest.approx(116)


def test_tco_does_not_invent_freight_when_quotation_is_missing():
    offer = propuesta(
        location="Maracaibo",
        clauses=[clausula("No incluye flete", ClausulaCategoria.flete)],
    )
    result = calculate_tco(offer, destination="Caracas, Distrito Capital")
    assert result.flete == 0
    assert result.total == pytest.approx(116)
    assert not result.completo
    assert any("cotización verificable" in warning for warning in result.advertencias)


def test_tco_parses_fifty_percent_surcharge():
    offer = propuesta(clauses=[clausula("Recargo 50%", ClausulaCategoria.recargo)])
    result = calculate_tco(offer)
    assert result.recargos == 50
    assert result.total == pytest.approx(174)


def test_tco_calculates_surcharge_on_declared_invoice_total_when_clause_says_so():
    offer = propuesta(clauses=[
        clausula("Recargo de 50% sobre el valor de la factura", ClausulaCategoria.recargo)
    ])

    result = calculate_tco(offer)

    assert result.recargos == pytest.approx(58)
    assert result.total == pytest.approx(183.28)
    assert "total de factura" in result.desglose[2].concepto


@pytest.mark.parametrize(
    ("quote", "bcv_rate"),
    [
        ({"amount": "25", "currency": "USD", "date": "2026-11-27", "source": "Cotización Transportes"}, None),
        ({"amount": "1250", "currency": "VES", "date": "2026-11-27", "source": "Cotización Transportes"}, 50),
    ],
)
def test_tco_adds_verified_freight_quote_in_proposal_currency(quote, bcv_rate):
    offer = propuesta(
        location="Maracaibo, Zulia",
        clauses=[clausula("No incluye flete", ClausulaCategoria.flete)],
    )

    result = calculate_tco(
        offer,
        destination="Caracas, Distrito Capital",
        freight_quote=quote,
        bcv_rate=bcv_rate,
    )

    assert result.flete == pytest.approx(25)
    assert result.total == pytest.approx(141)
    assert result.completo
    assert "Cotización Transportes" in result.desglose[-1].concepto


def test_tco_does_not_double_count_freight_declared_included():
    offer = propuesta(clauses=[clausula("Flete incluido", ClausulaCategoria.flete)])
    quote = {"amount": "25", "currency": "USD", "date": "2026-11-27", "source": "Transportes"}

    result = calculate_tco(offer, freight_quote=quote)

    assert result.flete == 0
    assert result.total == pytest.approx(116)
    assert any("se ignoró la cotización" in warning for warning in result.advertencias)


def test_tco_breakdown_reconciles_to_total():
    offer = propuesta(
        location="Valencia",
        clauses=[
            clausula("No incluye flete", ClausulaCategoria.flete),
            clausula("Recargo 10%", ClausulaCategoria.recargo),
        ],
    )
    result = calculate_tco(offer, destination="Caracas")
    assert sum(line.monto for line in result.desglose) == pytest.approx(result.total)
