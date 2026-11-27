from agent.schemas import Item
from agent.validators.compatibility import validate_compatibility
from tests.conftest import evidencia, propuesta


def test_compatibility_detects_cpu_board_socket_mismatch():
    items = [
        Item(descripcion="CPU Ryzen socket AM5", cantidad=1, unidad="u", precio_unitario=1, subtotal=1, evidencia=evidencia()),
        Item(descripcion="Placa base socket AM4 DDR4", cantidad=1, unidad="u", precio_unitario=1, subtotal=1, evidencia=evidencia()),
        Item(descripcion="Memoria RAM DDR4", cantidad=1, unidad="u", precio_unitario=1, subtotal=1, evidencia=evidencia()),
    ]
    valid, reasons = validate_compatibility(propuesta(items=items, subtotal=3, impuestos=0, total=3))
    assert not valid
    assert any("socket" in reason for reason in reasons)


def test_compatibility_detects_gpu_longer_than_case_clearance():
    items = [
        Item(descripcion="GPU RTX 320 mm", cantidad=1, unidad="u", precio_unitario=1, subtotal=1, evidencia=evidencia()),
        Item(descripcion="Gabinete máximo 300 mm", cantidad=1, unidad="u", precio_unitario=1, subtotal=1, evidencia=evidencia()),
    ]
    valid, reasons = validate_compatibility(propuesta(items=items, subtotal=2, impuestos=0, total=2))
    assert not valid
    assert any("excede" in reason for reason in reasons)
