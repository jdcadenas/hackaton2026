import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

from agent.schemas import FinancialAssessment, TCO


CENT = Decimal("0.01")
SUPPORTED_CURRENCIES = {"USD", "VES"}


def normalize_currency(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()
    compact = re.sub(r"[^A-Z$]", "", text)
    has_ves = any(token in compact for token in ("VES", "BS", "BOLIVAR"))
    has_usd = any(token in compact for token in ("USD", "US$", "DOLAR")) or "$" in text
    if has_ves and has_usd:
        return None
    if has_ves:
        return "VES"
    if has_usd:
        return "USD"
    return None


def _decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def to_usd(amount: object, currency: Optional[str], bcv_rate: object) -> Optional[Decimal]:
    value = _decimal(amount)
    code = normalize_currency(currency)
    rate = _decimal(bcv_rate)
    if value is None or value < 0:
        return None
    if code == "USD":
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    if code == "VES" and rate is not None and rate > 0:
        return (value / rate).quantize(CENT, rounding=ROUND_HALF_UP)
    return None


def to_ves(amount_usd: object, bcv_rate: object) -> Optional[Decimal]:
    amount = _decimal(amount_usd)
    rate = _decimal(bcv_rate)
    if amount is None or amount < 0 or rate is None or rate <= 0:
        return None
    return (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)


def assess_financial_feasibility(
    tco: Optional[TCO],
    proposal_currency: Optional[str],
    budget_amount: object,
    budget_currency: str,
    bcv_rate: object,
    bcv_date: str,
    bcv_source: str,
) -> FinancialAssessment:
    warnings: list[str] = []
    budget_usd = to_usd(budget_amount, budget_currency, bcv_rate)
    if budget_usd is None:
        warnings.append("No se pudo convertir el presupuesto a USD con la moneda y tasa BCV indicadas.")

    currency = normalize_currency(proposal_currency)
    proposal_usd = to_usd(tco.total, currency, bcv_rate) if tco and currency else None
    if not currency:
        warnings.append("No se identificó con certeza la moneda de la propuesta.")
    if proposal_usd is None:
        warnings.append("No se pudo normalizar el TCO de la propuesta a USD.")
    if tco:
        warnings.extend(tco.advertencias)
        if not tco.completo:
            warnings.append("El TCO es parcial; no se puede certificar la factibilidad financiera.")
    else:
        warnings.append("No se pudo calcular el TCO de la propuesta.")

    if budget_usd is None or proposal_usd is None or not tco or not tco.completo:
        status = "no_concluyente"
        difference = None
    else:
        difference = (budget_usd - proposal_usd).quantize(CENT, rounding=ROUND_HALF_UP)
        status = "dentro_presupuesto" if difference >= 0 else "sobre_presupuesto"

    proposal_ves = to_ves(proposal_usd, bcv_rate) if proposal_usd is not None else None
    return FinancialAssessment(
        estado=status,
        moneda_propuesta=currency,
        tco_propuesta=round(tco.total, 2) if tco else None,
        tco_usd=float(proposal_usd) if proposal_usd is not None else None,
        tco_ves=float(proposal_ves) if proposal_ves is not None else None,
        presupuesto_original=float(_decimal(budget_amount) or 0),
        moneda_presupuesto=normalize_currency(budget_currency) or budget_currency,
        presupuesto_usd=float(budget_usd) if budget_usd is not None else None,
        diferencia_usd=float(difference) if difference is not None else None,
        tasa_bcv_ves_por_usd=float(_decimal(bcv_rate) or 0),
        tasa_bcv_fecha=bcv_date,
        tasa_bcv_fuente=bcv_source,
        advertencias=list(dict.fromkeys(warnings)),
    )
