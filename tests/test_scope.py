from agent.validators.scope import validate_scope
from tests.conftest import evidencia, propuesta
from agent.schemas import Item, ProjectRequirement, ProjectRequirements


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


def test_scope_uses_extracted_project_requirements_and_evidence():
    requirement = ProjectRequirements(
        archivo="requerimientos.pdf",
        requisitos=[
            ProjectRequirement(
                descripcion="Laptop para estudiante",
                cantidad=10,
                unidad="unidades",
                especificaciones=["16 GB RAM"],
                terminos_clave=["notebook"],
                evidencia=evidencia(),
            )
        ],
    )
    offer = propuesta(items=[
        Item(
            descripcion="Notebook 16GB RAM",
            cantidad=10,
            unidad="unidades",
            precio_unitario=100,
            subtotal=1000,
            evidencia=evidencia(),
        )
    ], subtotal=1000, impuestos=0, total=1000)
    assert validate_scope(offer, requirement) == (True, [])


def test_scope_rejects_missing_required_quantity():
    requirement = ProjectRequirements(
        archivo="requerimientos.pdf",
        requisitos=[
            ProjectRequirement(
                descripcion="Laptop para estudiante",
                cantidad=10,
                evidencia=evidencia(),
            )
        ],
    )
    offer = propuesta(items=[
        Item(
            descripcion="Laptop de estudiante",
            cantidad=5,
            unidad="unidades",
            precio_unitario=100,
            subtotal=500,
            evidencia=evidencia(),
        )
    ], subtotal=500, impuestos=0, total=500)
    valid, reasons = validate_scope(offer, requirement)
    assert not valid
    assert any("Cantidad insuficiente" in reason for reason in reasons)
