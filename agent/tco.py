import re
from decimal import Decimal, InvalidOperation
from typing import List, Optional

from agent.finance import normalize_currency, to_usd, to_ves
from agent.schemas import ClausulaCategoria, PropuestaExtraida, TCO, TCOConcepto


_PERCENTAGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|por ciento)", re.I)
_INVOICE_BASE_TERMS = ("factura", "monto facturado", "importe facturado")


def _convert_freight_quote(
    quote: dict,
    proposal_currency: Optional[str],
    bcv_rate: object,
) -> Optional[float]:
    try:
        amount = Decimal(str(quote.get("amount")))
    except (InvalidOperation, ValueError):
        return None
    quote_currency = normalize_currency(quote.get("currency"))
    if not amount.is_finite() or amount < 0 or not quote_currency or not proposal_currency:
        return None
    if quote_currency == proposal_currency:
        return float(amount)
    amount_usd = to_usd(amount, quote_currency, bcv_rate)
    if amount_usd is None:
        return None
    if proposal_currency == "USD":
        return float(amount_usd)
    amount_ves = to_ves(amount_usd, bcv_rate)
    return float(amount_ves) if amount_ves is not None else None


def calculate_tco(
    propuesta: PropuestaExtraida,
    destination: Optional[str] = None,
    freight_quote: Optional[dict] = None,
    bcv_rate: object = None,
) -> TCO:
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
    freight = 0.0
    surcharge_tax = 0.0
    surcharge_clause_seen = False
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
            surcharge_clause_seen = True
            percentage = _PERCENTAGE.search(text)
            if percentage:
                base_amount = invoice_total if any(term in text for term in _INVOICE_BASE_TERMS) else float(subtotal)
                percentage_value = float(percentage.group(1).replace(",", "."))
                amount = base_amount * percentage_value / 100
                base_label = "total de factura" if base_amount == invoice_total and "factura" in text else "subtotal"
                surcharge_label = (
                    f"Recargo {percentage_value:g}% sobre {base_label} "
                    f"({base_amount:.2f} {currency or ''})"
                )
            else:
                amount_usd = clause.impacto_estimado_usd
                amount = (
                    float(amount_usd)
                    if amount_usd is not None and currency == "USD"
                    else float(to_ves(amount_usd, bcv_rate))
                    if amount_usd is not None and currency == "VES" and to_ves(amount_usd, bcv_rate) is not None
                    else None
                )
                surcharge_label = f"Recargo declarado: {clause.texto[:40]}"
            if amount is None:
                complete = False
                warnings.append(f"No se pudo cuantificar el recargo: {clause.texto}")
                continue
            surcharges += float(amount)
            breakdown.append(TCOConcepto(concepto=surcharge_label, monto=float(amount)))
            if surcharge_tax_rate is not None:
                surcharge_tax += float(amount) * surcharge_tax_rate
            else:
                complete = False
                warnings.append("No se puede determinar el impuesto aplicable a los recargos adicionales.")

    if not surcharge_clause_seen:
        breakdown.append(TCOConcepto(concepto="No se detectaron recargos cuantificables", monto=0.0))

    freight_already_included = freight_status is True
    if freight_quote and freight_already_included:
        breakdown.append(TCOConcepto(concepto="Flete incluido en el total declarado (sin cargo adicional)", monto=0.0))
        warnings.append("La propuesta declara el flete incluido; se ignoró la cotización adicional para evitar duplicarlo.")
    elif freight_already_included:
        breakdown.append(TCOConcepto(concepto="Flete incluido en el total declarado", monto=0.0))
    elif freight_quote:
        quote_source = str(freight_quote.get("source") or "").strip()
        quote_date = str(freight_quote.get("date") or "").strip()
        quote_amount = _convert_freight_quote(freight_quote, currency, bcv_rate)
        if not quote_source or not quote_date or quote_amount is None:
            complete = False
            warnings.append("La cotización de flete está incompleta o no se pudo convertir a la moneda de la propuesta.")
        else:
            freight = quote_amount
            breakdown.append(
                TCOConcepto(
                    concepto=f"Flete cotizado adicional ({quote_date}; fuente: {quote_source})",
                    monto=freight,
                )
            )
    elif freight_status is False:
        complete = False
        destination_label = destination or "destino del proyecto"
        warnings.append(f"El flete está excluido y no hay una cotización verificable hasta {destination_label}.")
    elif freight_status is None and destination:
        complete = False
        warnings.append(
            f"No se indicó si el flete está incluido ni hay una cotización adicional para la ruta "
            f"{propuesta.ubicacion_proveedor or 'origen no indicado'} → {destination}."
        )

    if surcharge_tax:
        breakdown.append(TCOConcepto(concepto="Impuestos estimados sobre recargos", monto=surcharge_tax))
    if not currency:
        complete = False
        warnings.append("No se identificó la moneda de la propuesta.")

    total = invoice_total + freight + surcharges + surcharge_tax
    return TCO(
        base=float(subtotal),
        flete=freight,
        recargos=surcharges,
        iva=declared_tax + surcharge_tax,
        total=total,
        moneda=currency,
        completo=complete,
        advertencias=list(dict.fromkeys(warnings)),
        desglose=breakdown,
    )
