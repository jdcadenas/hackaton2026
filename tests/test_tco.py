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
