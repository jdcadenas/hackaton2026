from typing import List, Tuple
from agent.schemas import PropuestaExtraida

TOLERANCE = 0.01

def validate_arithmetic(propuesta: PropuestaExtraida) -> Tuple[bool, List[str]]:
    motivos = []

    calc_subtotal = 0.0
    for idx, item in enumerate(propuesta.items):
        if item.cantidad is None or item.precio_unitario is None or item.subtotal is None:
            motivos.append(f"Ítem {idx + 1} ({item.descripcion}): faltan cantidad, precio unitario o subtotal.")
            continue
        expected_sub = item.cantidad * item.precio_unitario
        if abs(expected_sub - item.subtotal) > TOLERANCE:
            motivos.append(f"Ítem {idx+1} ({item.descripcion}): subtotal declarado {item.subtotal} no coincide con cantidad ({item.cantidad}) * precio_unitario ({item.precio_unitario}) = {expected_sub}")
        calc_subtotal += item.subtotal

    totales = propuesta.totales_declarados
    if totales.subtotal is None:
        motivos.append("Falta el subtotal declarado.")
    elif abs(calc_subtotal - totales.subtotal) > TOLERANCE:
        motivos.append(f"Suma de subtotales de ítems ({calc_subtotal}) no coincide con subtotal declarado ({totales.subtotal})")

    if totales.subtotal is None or totales.impuestos is None or totales.total is None:
        motivos.append("Faltan subtotal, impuestos o total declarado para verificar la suma.")
    else:
        calc_total = totales.subtotal + totales.impuestos
        if abs(calc_total - totales.total) > TOLERANCE:
            motivos.append(f"Subtotal ({totales.subtotal}) + impuestos ({totales.impuestos}) = {calc_total} no coincide con total declarado ({totales.total})")

    is_valid = len(motivos) == 0
    return is_valid, motivos
