from agent.validators.arithmetic import validate_arithmetic
from tests.conftest import evidencia, propuesta
from agent.schemas import Item


def test_arithmetic_ok():
    assert validate_arithmetic(propuesta())[0]


def test_arithmetic_rejects_bad_item_total():
    offer = propuesta(items=[Item(
        descripcion="Equipo", cantidad=2, unidad="u", precio_unitario=10, subtotal=19, evidencia=evidencia()
    )], subtotal=19, impuestos=0, total=19)
    valid, reasons = validate_arithmetic(offer)
    assert not valid
    assert any("no coincide con cantidad" in reason for reason in reasons)


def test_arithmetic_rejects_declared_sum_mismatch():
    offer = propuesta(subtotal=101, impuestos=0, total=101)
    valid, reasons = validate_arithmetic(offer)
    assert not valid
    assert any("Suma de subtotales" in reason for reason in reasons)


def test_arithmetic_allows_one_cent_rounding():
    offer = propuesta(items=[Item(
        descripcion="Equipo", cantidad=3, unidad="u", precio_unitario=0.333, subtotal=1.00, evidencia=evidencia()
    )], subtotal=1.00, impuestos=0, total=1.00)
    assert validate_arithmetic(offer)[0]


def test_arithmetic_rejects_missing_amounts():
    offer = propuesta(subtotal=None, impuestos=None, total=None)
    valid, reasons = validate_arithmetic(offer)
    assert not valid
    assert any("Faltan subtotal" in reason for reason in reasons)
