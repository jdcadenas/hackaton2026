from typing import Any

from agent.finance import to_usd
from agent.ranker import rank_audits
from agent.schemas import ResultadoAuditoria
from agent.validators.arithmetic import analyze_arithmetic


def build_financial_report(records: list[Any]) -> dict[str, Any]:
    audited = []
    for record in records:
        if not record.audit_json:
            continue
        audit = ResultadoAuditoria.model_validate_json(record.audit_json)
        if audit.aritmetica is None:
            audit.aritmetica = analyze_arithmetic(audit.propuesta)
        audited.append((record, audit))
    ranking = rank_audits([audit for _, audit in audited])
    rank_by_name = {filename: position for position, filename in enumerate(ranking, start=1)}

    def eligible(audit: ResultadoAuditoria) -> bool:
        arithmetic = audit.aritmetica or analyze_arithmetic(audit.propuesta)
        financial = audit.factibilidad_financiera
        return bool(
            not audit.descartada
            and arithmetic.estado == "cumple"
            and audit.alcance_estado == "cumple"
            and audit.tco
            and audit.tco.completo
            and financial
            and financial.estado == "dentro_presupuesto"
            and financial.tco_usd is not None
        )

    candidates = [audit for _, audit in audited if eligible(audit)]
    candidates.sort(
        key=lambda audit: (
            audit.factibilidad_financiera.tco_usd,
            -audit.technical_score,
            audit.propuesta.archivo,
        )
    )
    recommended = candidates[0] if candidates else None
    recommendation = None
    if recommended:
        financial = recommended.factibilidad_financiera
        tco = recommended.tco
        assert financial is not None and tco is not None
        recommendation = {
            "archivo": recommended.propuesta.archivo,
            "proveedor": recommended.propuesta.proveedor or "Proveedor no identificado",
            "tco_usd": financial.tco_usd,
            "diferencia_usd": financial.diferencia_usd,
            "justificacion": (
                "Cumple las validaciones aritméticas y de alcance, tiene TCO completo, "
                f"queda dentro del presupuesto y presenta el menor TCO entre las opciones elegibles "
                f"({financial.tco_usd:.2f} USD)."
            ),
            "advertencias": _market_alerts(recommended),
        }

    rows_by_name: dict[str, dict[str, Any]] = {}
    for record, audit in audited:
        arithmetic = audit.aritmetica or analyze_arithmetic(audit.propuesta)
        data = audit.model_dump(mode="json")
        rank = rank_by_name.get(record.original_name)
        market_alerts = _market_alerts(audit)
        recalculated_tco = _recalculated_tco(audit, arithmetic)
        data["aritmetica"] = arithmetic.model_dump(mode="json")
        data["tco_recalculado"] = recalculated_tco
        data["posicion"] = rank
        data["dictamen_informe"] = _decision(
            audit,
            rank,
            recommended,
            arithmetic.estado,
            market_alerts,
        )
        data["alertas_mercado_informe"] = market_alerts
        rows_by_name[record.original_name] = {
            "file": record,
            "audit": data,
            "aritmetica": data["aritmetica"],
            "tco_recalculado": recalculated_tco,
            "dictamen": data["dictamen_informe"],
            "alertas_mercado": market_alerts,
            "posicion": rank,
            "recomendada": bool(recommended and recommended.propuesta.archivo == record.original_name),
        }

    pending = [
        {"file": record, "audit": None, "aritmetica": None, "dictamen": "Pendiente de evaluación",
         "alertas_mercado": [], "posicion": None, "recomendada": False}
        for record in records
        if record.original_name not in rows_by_name
    ]
    report_rows = sorted(
        rows_by_name.values(),
        key=lambda row: (row["posicion"] is None, row["posicion"] or 0, row["file"].original_name),
    ) + pending

    return {
        "rows": report_rows,
        "recommendation": recommendation,
        "ranking": ranking,
        "evaluated_count": len(audited),
        "proposal_count": len(records),
        "recommendation_missing": recommended is None,
    }


def _recalculated_tco(
    audit: ResultadoAuditoria,
    arithmetic: Any,
) -> dict[str, Any]:
    tco = audit.tco
    recalculated_invoice = arithmetic.total_recalculado
    if tco is None or recalculated_invoice is None:
        return {
            "total": None,
            "usd": None,
            "diferencia_presupuesto_usd": None,
            "moneda": audit.propuesta.moneda,
            "completo": False,
        }
    estimated_surcharge_tax = sum(
        line.monto
        for line in tco.desglose
        if line.concepto == "Impuestos estimados sobre recargos"
    )
    total = recalculated_invoice + tco.flete + tco.recargos + estimated_surcharge_tax
    financial = audit.factibilidad_financiera
    rate = financial.tasa_bcv_ves_por_usd if financial else None
    usd = to_usd(total, audit.propuesta.moneda, rate)
    budget_difference_usd = (
        financial.presupuesto_usd - float(usd)
        if financial and financial.presupuesto_usd is not None and usd is not None
        else None
    )
    return {
        "total": round(total, 2),
        "usd": float(usd) if usd is not None else None,
        "diferencia_presupuesto_usd": budget_difference_usd,
        "moneda": audit.propuesta.moneda,
        "completo": tco.completo and arithmetic.estado == "cumple",
    }


def _market_alerts(audit: ResultadoAuditoria) -> list[dict[str, Any]]:
    alerts = []
    for market in audit.precios_mercado:
        average = market.promedio_mercado_usd
        offered = market.precio_ofertado_usd
        if (
            average is None
            or average <= 0
            or offered is None
            or market.confianza < 0.8
            or offered <= average
        ):
            continue
        alerts.append(
            {
                "componente": market.componente,
                "ofertado_usd": offered,
                "promedio_usd": average,
                "sobreprecio_pct": (offered / average - 1) * 100,
                "confianza": market.confianza,
                "fuentes": [source.model_dump(mode="json") for source in market.fuentes],
            }
        )
    return alerts


def _decision(
    audit: ResultadoAuditoria,
    rank: int | None,
    recommended: ResultadoAuditoria | None,
    arithmetic_status: str,
    market_alerts: list[dict[str, Any]],
) -> str:
    if audit.descartada:
        base = "Descartada por validaciones: " + "; ".join(audit.motivos_descarte)
    elif arithmetic_status != "cumple":
        base = "No recomendada: aritmética " + arithmetic_status + "; revisar la conciliación mostrada."
    elif audit.alcance_estado != "cumple":
        base = "No recomendada: alcance " + audit.alcance_estado.replace("_", " ") + "; requiere revisión."
    elif audit.tco is None or not audit.tco.completo:
        warnings = audit.tco.advertencias if audit.tco else ["no se pudo calcular el TCO"]
        base = "No recomendada: TCO no concluyente. " + "; ".join(warnings)
    elif audit.factibilidad_financiera is None:
        base = "No recomendada: falta evaluación financiera en USD."
    elif audit.factibilidad_financiera.estado == "sobre_presupuesto":
        excess = abs(audit.factibilidad_financiera.diferencia_usd or 0)
        base = f"No recomendada: excede el presupuesto en {excess:.2f} USD."
    elif audit.factibilidad_financiera.estado == "no_concluyente":
        base = "No recomendada: factibilidad financiera no concluyente. " + "; ".join(
            audit.factibilidad_financiera.advertencias
        )
    elif recommended and recommended.propuesta.archivo != audit.propuesta.archivo:
        chosen = recommended.factibilidad_financiera
        own = audit.factibilidad_financiera
        assert chosen is not None and chosen.tco_usd is not None and own.tco_usd is not None
        difference = own.tco_usd - chosen.tco_usd
        cost_details = []
        if audit.tco.flete > 0:
            cost_details.append(f"incluye {audit.tco.flete:.2f} {audit.tco.moneda or ''} de flete")
        if audit.tco.recargos > 0:
            cost_details.append(f"incluye {audit.tco.recargos:.2f} {audit.tco.moneda or ''} en recargos")
        detail = "; " + ", ".join(cost_details) if cost_details else ""
        base = (
            f"Posición {rank}: TCO ajustado {own.tco_usd:.2f} USD, "
            f"{difference:.2f} USD por encima de la recomendada {recommended.propuesta.archivo}{detail}."
        )
    else:
        base = f"Recomendada en la posición {rank}."

    if market_alerts:
        alert = market_alerts[0]
        base += (
            f" Alerta no automática: {alert['componente']} está "
            f"{alert['sobreprecio_pct']:.1f}% sobre el promedio observado "
            f"({alert['promedio_usd']:.2f} USD; confianza {alert['confianza']:.2f})."
        )
    return base


def render_markdown(project: Any, report: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")

    lines = [
        f"# Informe de análisis y factibilidad financiera — {project.title}",
        "",
        f"- **Destino:** {project.execution_city or 'No indicado'}, {project.execution_state or 'No indicado'}",
        f"- **Presupuesto:** {project.budget_amount if project.budget_amount is not None else 'No indicado'} "
        f"{project.budget_currency or ''} (impuestos incluidos)",
        f"- **BCV:** {project.bcv_rate or 'No indicada'} VES/USD · {project.bcv_date or '—'} · {project.bcv_source or '—'}",
        "",
        "## Propuesta recomendada",
        "",
    ]
    recommendation = report["recommendation"]
    if recommendation:
        lines.extend(
            [
                f"**{cell(recommendation['archivo'])} — {cell(recommendation['proveedor'])}**",
                "",
                recommendation["justificacion"],
                f"TCO: {recommendation['tco_usd']:.2f} USD; saldo de presupuesto (TCO declarado ajustado): "
                f"{recommendation['diferencia_usd']:.2f} USD.",
            ]
        )
        for warning in recommendation["advertencias"]:
            lines.append(f"- Alerta de mercado: {cell(warning['componente'])} está "
                         f"{warning['sobreprecio_pct']:.1f}% sobre el promedio observado.")
    else:
        lines.append("No se emite recomendación: ninguna propuesta satisface todos los criterios verificables.")
    lines.extend(
        [
            "",
            "## Comparación de propuestas",
            "",
            "| Puesto | Propuesta | Subtotal declarado | Total declarado | Subtotal recalculado | Diferencia total aritmética | Flete | Recargos | TCO recalculado | TCO recalculado USD | TCO declarado ajustado USD | Saldo presupuesto recalculado USD | Saldo presupuesto declarado USD | Alcance | Dictamen |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in report["rows"]:
        audit = row["audit"] or {}
        proposal = audit.get("propuesta", {})
        totals = proposal.get("totales_declarados", {})
        arithmetic = audit.get("aritmetica") or {}
        tco = audit.get("tco") or {}
        recalculated_tco = audit.get("tco_recalculado") or {}
        financial = audit.get("factibilidad_financiera") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    cell(row["posicion"]),
                    cell(row["file"].original_name),
                    cell(totals.get("subtotal")),
                    cell(totals.get("total")),
                    cell(arithmetic.get("subtotal_items_calculado")),
                    cell(arithmetic.get("diferencia_total")),
                    cell(tco.get("flete")),
                    cell(tco.get("recargos")),
                    cell(recalculated_tco.get("total")),
                    cell(recalculated_tco.get("usd")),
                    cell(financial.get("tco_usd")),
                    cell(recalculated_tco.get("diferencia_presupuesto_usd")),
                    cell(financial.get("diferencia_usd")),
                    cell(audit.get("alcance_estado")),
                    cell(row["dictamen"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Dictámenes y evidencia", ""])
    for row in report["rows"]:
        lines.extend([f"### {cell(row['file'].original_name)}", "", row["dictamen"], ""])
        audit = row["audit"] or {}
        arithmetic = audit.get("aritmetica") or {}
        if arithmetic.get("motivos"):
            lines.extend(["Conciliación aritmética:", *[f"- {cell(reason)}" for reason in arithmetic["motivos"]], ""])
        tco = audit.get("tco") or {}
        if tco.get("desglose"):
            lines.append(f"Desglose TCO ({cell(tco.get('moneda'))}):")
            lines.extend(
                f"- {cell(line['concepto'])}: {cell(line['monto'])}"
                for line in tco["desglose"]
            )
            lines.append("")
        lines.extend(f"Advertencia TCO: {cell(warning)}" for warning in tco.get("advertencias", []))
        financial = audit.get("factibilidad_financiera") or {}
        lines.extend(
            f"Advertencia financiera: {cell(warning)}"
            for warning in financial.get("advertencias", [])
        )
        for alert in row["alertas_mercado"]:
            lines.append(
                f"Alerta de mercado: {cell(alert['componente'])}, {alert['sobreprecio_pct']:.1f}% "
                f"sobre el promedio de {alert['promedio_usd']:.2f} USD."
            )
            lines.extend(f"- Fuente: {cell(source['url'])} ({source['fecha_consulta']})" for source in alert["fuentes"])
            lines.append("")
    lines.append(
        "Las diferencias aritméticas se muestran como conciliación; no se corrige silenciosamente la oferta. "
        "Las alertas de mercado son indicativas y no causan descarte automático."
    )
    return "\n".join(lines) + "\n"
