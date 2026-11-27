import re
import unicodedata
from typing import List, Optional

from agent.finance import normalize_currency
from agent.schemas import ClausulaCategoria, PropuestaExtraida, TCO, TCOConcepto


_PERCENTAGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por ciento)", re.I)


def _normalized_location(value: Optional[str]) -> str:
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _same_city_state(supplier: Optional[str], destination: str) -> bool:
    supplier_parts = [_normalized_location(part) for part in (supplier or "").split(",") if part.strip()]
    destination_parts = [_normalized_location(part) for part in destination.split(",") if part.strip()]
    if not supplier_parts or not destination_parts or supplier_parts[0] != destination_parts[0]:
        return False
    if len(destination_parts) > 1:
        return len(supplier_parts) > 1 and supplier_parts[1] == destination_parts[1]
    return True


def calculate_tco(propuesta: PropuestaExtraida, destination: Optional[str] = None) -> TCO:
    subtotal = propuesta.totales_declarados.subtotal
    taxes = propuesta.totales_declarados.impuestos
    declared_total = propuesta.totales_declarados.total
    if subtotal is None:
        raise ValueError("No se puede calcular el TCO sin subtotal declarado.")

    currency = normalize_currency(propuesta.moneda)
    complete = True
    warnings: list[str] = []
    breakdown: List[TCOConcepto] = [TCOConcepto(concepto="Subtotal declarado", monto=float(subtotal))]

    if declared_total is not None:
        invoice_total = float(declared_total)
        declared_tax = float(taxes) if taxes is not None else max(invoice_total - float(subtotal), 0.0)
        included_other = invoice_total - float(subtotal) - declared_tax
        if included_other > 0.01:
            breakdown.append(TCOConcepto(concepto="Otros cargos incluidos en el total declarado", monto=included_other))
    elif taxes is not None:
        declared_tax = float(taxes)
        invoice_total = float(subtotal) + declared_tax
        breakdown.append(TCOConcepto(concepto="Impuestos declarados", monto=declared_tax))
    else:
        declared_tax = 0.0
        invoice_total = float(subtotal)
        complete = False
        warnings.append("La propuesta no declara total final ni impuestos; el TCO es un subtotal parcial.")
    if declared_total is not None and taxes is None and declared_tax > 0:
        breakdown.append(TCOConcepto(concepto="Impuestos/cargos incluidos, no desglosados", monto=declared_tax))
    elif declared_total is not None and taxes is not None and declared_tax:
        breakdown.append(TCOConcepto(concepto="Impuestos declarados incluidos en el total", monto=declared_tax))

    surcharges = 0.0
    surcharge_tax = 0.0
    surcharge_tax_rate = float(taxes) / float(subtotal) if taxes is not None and float(subtotal) > 0 else None
    freight_status: Optional[bool] = None

    for clause in propuesta.clausulas:
        text = clause.texto.lower()
        is_freight = (
            clause.categoria in {ClausulaCategoria.flete, ClausulaCategoria.traslado}
            or any(term in text for term in ("flete", "transporte", "envío", "envio"))
        )
        if is_freight:
            if any(term in text for term in ("no incluye", "sin flete", "por cuenta del cliente", "no incluido")):
                freight_status = False
            elif any(term in text for term in ("incluye flete", "flete incluido", "transporte incluido", "envío incluido", "envio incluido")):
                freight_status = True

        if clause.categoria == ClausulaCategoria.recargo or "recargo" in text:
            amount = clause.impacto_estimado_usd if currency == "USD" else None
            if amount is None:
                percentage = _PERCENTAGE.search(text)
                if percentage:
                    amount = float(subtotal) * float(percentage.group(1).replace(",", ".")) / 100
            if amount is None:
                complete = False
                warnings.append(f"No se pudo cuantificar el recargo: {clause.texto}")
                continue
            surcharges += float(amount)
            breakdown.append(TCOConcepto(concepto=f"Recargo: {clause.texto[:40]}", monto=float(amount)))
            if surcharge_tax_rate is not None:
                surcharge_tax += float(amount) * surcharge_tax_rate
            else:
                complete = False
                warnings.append("No se puede determinar el impuesto aplicable a los recargos adicionales.")

    if freight_status is False:
        complete = False
        destination_label = destination or "destino del proyecto"
        warnings.append(f"El flete está excluido y no hay una cotización verificable hasta {destination_label}.")
    elif freight_status is None and destination:
        if not _same_city_state(propuesta.ubicacion_proveedor, destination):
            complete = False
            warnings.append(
                f"No se confirmó si el precio incluye entrega desde "
                f"{propuesta.ubicacion_proveedor or 'una ubicación no indicada'} hasta {destination}."
            )

    if surcharge_tax:
        breakdown.append(TCOConcepto(concepto="Impuestos estimados sobre recargos", monto=surcharge_tax))
    if not currency:
        complete = False
        warnings.append("No se identificó la moneda de la propuesta.")

    total = invoice_total + surcharges + surcharge_tax
    return TCO(
        base=float(subtotal),
        flete=0.0,
        recargos=surcharges,
        iva=declared_tax + surcharge_tax,
        total=total,
        moneda=currency,
        completo=complete,
        advertencias=list(dict.fromkeys(warnings)),
        desglose=breakdown,
    )
