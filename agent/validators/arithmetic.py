from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import List, Tuple

from agent.schemas import ArithmeticAssessment, PropuestaExtraida


TOLERANCE = Decimal("0.01")
CENT = Decimal("0.01")


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _rounded(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def analyze_arithmetic(propuesta: PropuestaExtraida) -> ArithmeticAssessment:
    motivos: list[str] = []
    incomplete = False
    discrepant = False
    calculated_items_subtotal = Decimal("0")
    declared_items_subtotal = Decimal("0")
    can_calculate_items = bool(propuesta.items)
    can_sum_declared_items = bool(propuesta.items)

    for idx, item in enumerate(propuesta.items):
        quantity = _decimal(item.cantidad)
        unit_price = _decimal(item.precio_unitario)
        item_subtotal = _decimal(item.subtotal)
        if quantity is None or unit_price is None or item_subtotal is None:
            incomplete = True
            motivos.append(f"Ítem {idx + 1} ({item.descripcion}): faltan cantidad, precio unitario o subtotal.")
        if quantity is None or unit_price is None:
            can_calculate_items = False
        else:
            expected_subtotal = quantity * unit_price
            calculated_items_subtotal += expected_subtotal
            if item_subtotal is not None and abs(expected_subtotal - item_subtotal) > TOLERANCE:
                discrepant = True
                motivos.append(
                    f"Ítem {idx + 1} ({item.descripcion}): subtotal declarado {item_subtotal} "
                    f"no coincide con cantidad ({quantity}) * precio unitario ({unit_price}) "
                    f"= {expected_subtotal.quantize(CENT, rounding=ROUND_HALF_UP)}."
                )
        if item_subtotal is None:
            can_sum_declared_items = False
        else:
            declared_items_subtotal += item_subtotal

    totales = propuesta.totales_declarados
    declared_subtotal = _decimal(totales.subtotal)
    taxes = _decimal(totales.impuestos)
    declared_total = _decimal(totales.total)
    if not propuesta.items:
        incomplete = True
        motivos.append("No se identificaron ítems para verificar los cálculos.")
    if declared_subtotal is None:
        incomplete = True
        motivos.append("Falta el subtotal declarado.")
    elif can_sum_declared_items and abs(declared_items_subtotal - declared_subtotal) > TOLERANCE:
        discrepant = True
        motivos.append(
            f"Suma de subtotales de ítems ({declared_items_subtotal.quantize(CENT, rounding=ROUND_HALF_UP)}) "
            f"no coincide con subtotal declarado ({declared_subtotal})."
        )

    if declared_subtotal is None or taxes is None or declared_total is None:
        incomplete = True
        motivos.append("Faltan subtotal, impuestos o total declarado para verificar la suma.")
    else:
        calculated_total_from_declared = declared_subtotal + taxes
        if abs(calculated_total_from_declared - declared_total) > TOLERANCE:
            discrepant = True
            motivos.append(
                f"Subtotal ({declared_subtotal}) + impuestos ({taxes}) = "
                f"{calculated_total_from_declared.quantize(CENT, rounding=ROUND_HALF_UP)} "
                f"no coincide con total declarado ({declared_total})."
            )

    recalculated_subtotal = calculated_items_subtotal if can_calculate_items else None
    recalculated_total = (
        recalculated_subtotal + taxes
        if recalculated_subtotal is not None and taxes is not None
        else None
    )
    subtotal_delta = (
        recalculated_subtotal - declared_subtotal
        if recalculated_subtotal is not None and declared_subtotal is not None
        else None
    )
    total_delta = (
        recalculated_total - declared_total
        if recalculated_total is not None and declared_total is not None
        else None
    )
    status = "incompleto" if incomplete else "discrepancia" if discrepant else "cumple"

    return ArithmeticAssessment(
        estado=status,
        subtotal_items_calculado=_rounded(recalculated_subtotal),
        subtotal_items_declarado=_rounded(declared_items_subtotal) if can_sum_declared_items else None,
        subtotal_declarado=_rounded(declared_subtotal),
        diferencia_subtotal=_rounded(subtotal_delta),
        total_recalculado=_rounded(recalculated_total),
        total_declarado=_rounded(declared_total),
        diferencia_total=_rounded(total_delta),
        motivos=motivos,
    )


def validate_arithmetic(propuesta: PropuestaExtraida) -> Tuple[bool, List[str]]:
    assessment = analyze_arithmetic(propuesta)
    return assessment.estado == "cumple", assessment.motivos
