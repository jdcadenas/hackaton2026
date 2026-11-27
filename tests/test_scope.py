from agent.validators.scope import validate_scope
from tests.conftest import evidencia, propuesta
from agent.schemas import Item


def test_scope_requires_eleven_equipment_peripherals_and_ups():
    items = [
        Item(descripcion="PC", cantidad=10, unidad="unidad", precio_unitario=1, subtotal=10, evidencia=evidencia()),
        Item(descripcion="Monitor teclado mouse UPS", cantidad=1, unidad="conjunto", precio_unitario=1, subtotal=1, evidencia=evidencia()),
    ]
    valid, reasons = validate_scope(propuesta(items=items, subtotal=11, impuestos=0, total=11))
    assert not valid
    assert any("al menos 11" in reason for reason in reasons)


def test_scope_accepts_complete_eleven_equipment_set():
    items = [
        Item(descripcion="PC", cantidad=11, unidad="unidad", precio_unitario=1, subtotal=11, evidencia=evidencia()),
        Item(descripcion="Monitor teclado mouse UPS", cantidad=11, unidad="conjunto", precio_unitario=1, subtotal=11, evidencia=evidencia()),
    ]
    assert validate_scope(propuesta(items=items, subtotal=22, impuestos=0, total=22))[0]
