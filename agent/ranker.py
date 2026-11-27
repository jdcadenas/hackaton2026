from typing import List
from agent.schemas import ResultadoAuditoria

def rank_audits(audits: List[ResultadoAuditoria]) -> List[str]:
    # Keep one deterministic result per proposal filename.
    by_name = {}
    for audit in audits:
        by_name.setdefault(audit.propuesta.archivo, audit)
    unique_audits = list(by_name.values())
    evaluadas = [a for a in unique_audits if not a.descartada]
    descartadas = [a for a in unique_audits if a.descartada]

    currencies = {audit.tco.moneda for audit in evaluadas if audit.tco and audit.tco.moneda}
    can_compare_raw_tco = len(currencies) <= 1 and not any(a.factibilidad_financiera for a in evaluadas)

    def comparable_cost(audit: ResultadoAuditoria) -> float:
        assessment = audit.factibilidad_financiera
        if assessment and assessment.estado != "no_concluyente" and assessment.tco_usd is not None:
            return assessment.tco_usd
        if can_compare_raw_tco and audit.tco:
            return audit.tco.total
        return float("inf")

    def requires_review(audit: ResultadoAuditoria) -> bool:
        assessment = audit.factibilidad_financiera
        return (
            audit.alcance_estado != "cumple"
            or (assessment is not None and assessment.estado == "no_concluyente")
        )

    confirmadas = [audit for audit in evaluadas if not requires_review(audit)]
    no_concluyentes = [audit for audit in evaluadas if requires_review(audit)]
    confirmadas.sort(
        key=lambda audit: (
            audit.factibilidad_financiera.estado == "sobre_presupuesto"
            if audit.factibilidad_financiera
            else False,
            -audit.technical_score,
            comparable_cost(audit),
            audit.propuesta.archivo,
        )
    )
    no_concluyentes.sort(
        key=lambda audit: (-audit.technical_score, comparable_cost(audit), audit.propuesta.archivo)
    )
    descartadas.sort(key=lambda x: x.propuesta.archivo)

    return [
        audit.propuesta.archivo
        for audit in confirmadas + no_concluyentes + descartadas
    ]
