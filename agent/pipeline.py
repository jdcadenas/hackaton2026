import os
from typing import Callable, List, Optional, Tuple

from agent.errors import format_gemini_error
from agent.finance import assess_financial_feasibility, to_usd
from agent.extractor import extract_proposal
from agent.market.search_grounding import research_market_price
from agent.ranker import rank_audits
from agent.schemas import (
    MarketPriceReview,
    PriceSource,
    ProjectRequirements,
    PropuestaExtraida,
    ResultadoAuditoria,
)
from agent.status import EstadoDocumento
from agent.tco import calculate_tco
from agent.validators.arithmetic import analyze_arithmetic, validate_arithmetic
from agent.validators.compatibility import validate_compatibility
from agent.validators.injection import check_injection
from agent.validators.scope import validate_scope


ProgressCallback = Callable[[str, str], None]
SUPPORTED_EXTS = (".pdf", ".jpg", ".jpeg", ".png", ".xlsx")


def _proposal_files(lote_dir: str) -> list[str]:
    proposals_dir = os.path.join(lote_dir, "propuestas")
    if not os.path.isdir(proposals_dir):
        return []
    files = []
    for root, dirs, filenames in os.walk(proposals_dir):
        dirs.sort()
        for filename in sorted(filenames):
            if filename.lower().endswith(SUPPORTED_EXTS):
                files.append(os.path.join(root, filename))
    return files


def run_pipeline(
    lote_dir: str,
    api_key: Optional[str] = None,
    progress: Optional[ProgressCallback] = None,
    project_context: Optional[dict] = None,
    project_requirements: Optional[ProjectRequirements] = None,
    freight_quotes: Optional[dict[str, dict]] = None,
) -> Tuple[List[ResultadoAuditoria], List[str]]:
    files = _proposal_files(lote_dir)
    audits: List[ResultadoAuditoria] = []

    def report(stage: str, message: str) -> None:
        if progress:
            progress(stage, message)

    for file_path in files:
        filename = os.path.relpath(file_path, os.path.join(lote_dir, "propuestas"))
        report("extraccion", f"Extrayendo {filename}")
        try:
            proposal = extract_proposal(file_path, api_key=api_key)
        except Exception as exc:
            proposal = PropuestaExtraida(
                archivo=filename,
                fuente="pdf",
                anomalias_ingesta=[
                    f"Error inesperado durante la extracción: {format_gemini_error(exc)}"
                ],
            )
            proposal._estado_evaluacion = EstadoDocumento.NO_VERIFICADO
        proposal.archivo = filename
        extraction_status = proposal._estado_evaluacion
        if extraction_status in {
            EstadoDocumento.NO_VERIFICADO,
            EstadoDocumento.ERROR_API_503,
        }:
            message = "; ".join(proposal.anomalias_ingesta) or "No se pudo verificar el documento."
            report(
                extraction_status.value.lower(),
                f"{filename}: {message}",
            )
            audits.append(
                ResultadoAuditoria(
                    propuesta=proposal,
                    estado_documento=extraction_status,
                    alcance_estado="no_concluyente",
                    alcance_advertencias=[message],
                    notas=(
                        "Error temporal de Gemini; el documento puede reintentarse."
                        if extraction_status == EstadoDocumento.ERROR_API_503
                        else "Documento no verificado; requiere corregir el problema antes de evaluarlo."
                    ),
                )
            )
            continue

        reasons: list[str] = []
        arithmetic_assessment = analyze_arithmetic(proposal)
        extraction_failed = bool(proposal.anomalias_ingesta)
        if extraction_failed:
            reasons.extend(proposal.anomalias_ingesta)

        full_text = " ".join(
            [proposal.proveedor or ""]
            + [item.descripcion for item in proposal.items]
            + [clause.texto for clause in proposal.clausulas]
        )
        injection = check_injection(full_text)
        if injection.detected or any("Texto sospechoso transcrito literalmente" in issue for issue in proposal.anomalias_ingesta):
            reasons.append(f"Posible prompt injection detectado: {injection.matches or 'texto sospechoso en el documento'}")

        scope_status = "no_concluyente"
        scope_warnings: list[str] = []
        if not reasons:
            validators = [
                ("Aritmética", validate_arithmetic),
                *(
                    [("Alcance estándar", validate_scope)]
                    if project_requirements is None
                    else []
                ),
                ("Compatibilidad", validate_compatibility),
            ]
            for label, validator in validators:
                report("validacion", f"Validando {label.lower()}: {filename}")
                if validator is validate_scope:
                    is_valid, validator_reasons = validate_scope(proposal)
                    scope_status = "cumple" if is_valid else "incompleto"
                elif validator is validate_arithmetic:
                    is_valid = arithmetic_assessment.estado == "cumple"
                    validator_reasons = arithmetic_assessment.motivos
                else:
                    is_valid, validator_reasons = validator(proposal)
                if not is_valid:
                    reasons.extend(validator_reasons)
                    report("advertencia", f"{label} requiere atención en {filename}: {'; '.join(validator_reasons)}")
                    break
                report("validacion", f"{label} validada: {filename}")

            if project_requirements is not None:
                if not project_requirements.requisitos:
                    scope_status = "no_concluyente"
                    scope_warnings = project_requirements.advertencias or [
                        "No se extrajeron requisitos verificables del documento base."
                    ]
                elif any(
                    requirement.evidencia.pagina is None or requirement.evidencia.confianza < 0.75
                    for requirement in project_requirements.requisitos
                ):
                    scope_status = "no_concluyente"
                    scope_warnings = [
                        "La extracción de uno o más requisitos no tiene página o confianza suficiente; "
                        "el alcance requiere revisión humana."
                    ]
                    report("advertencia", f"Alcance requiere revisión manual en {filename}: {'; '.join(scope_warnings)}")
                else:
                    report("validacion", f"Comparando la propuesta con los requisitos del proyecto: {filename}")
                    is_valid, scope_warnings = validate_scope(proposal, project_requirements)
                    scope_status = "cumple" if is_valid else "incompleto"
                    if not is_valid:
                        reasons.extend(scope_warnings)
                        report("advertencia", f"Alcance incompleto en {filename}: {'; '.join(scope_warnings)}")
                    else:
                        report("validacion", f"Alcance del proyecto validado: {filename}")
        elif project_requirements is not None:
            scope_warnings = project_requirements.advertencias or [
                "No se verificó el alcance porque falló una validación previa."
            ]
            report("advertencia", f"Alcance no verificado en {filename}: {'; '.join(scope_warnings)}")

        discarded = bool(reasons)
        tco = None
        if proposal.totales_declarados.subtotal is not None:
            try:
                report("tco", f"Calculando total de propiedad (TCO): {filename}")
                destination = None
                if project_context:
                    destination = ", ".join(
                        value for value in (
                            project_context.get("execution_city"),
                            project_context.get("execution_state"),
                        ) if value
                    )
                tco = calculate_tco(
                    proposal,
                    destination=destination,
                    freight_quote=(freight_quotes or {}).get(filename),
                    bcv_rate=project_context.get("bcv_rate") if project_context else None,
                )
                for component in tco.desglose:
                    report(
                        "tco",
                        f"{filename}: {component.concepto} = {component.monto:.2f} {tco.moneda or 'moneda no identificada'}",
                    )
                for warning in tco.advertencias:
                    report("advertencia", f"{filename}: {warning}")
            except ValueError as exc:
                reasons.append(str(exc))
                discarded = True
                report("advertencia", f"No se pudo calcular el TCO de {filename}: {exc}")
        else:
            report("advertencia", f"No se calculó el TCO de {filename}: falta el subtotal declarado.")

        score = 0.0 if discarded else 100.0
        financial_assessment = None
        if project_context and project_context.get("budget_amount") is not None:
            financial_assessment = assess_financial_feasibility(
                tco=tco,
                proposal_currency=proposal.moneda,
                budget_amount=project_context["budget_amount"],
                budget_currency=project_context["budget_currency"],
                bcv_rate=project_context["bcv_rate"],
                bcv_date=project_context["bcv_date"],
                bcv_source=project_context["bcv_source"],
            )

        market_reviews: list[MarketPriceReview] = []
        if not discarded:
            report("mercado", f"Consultando precios con Google Search: {filename}")
            for item in proposal.items:
                if item.descripcion.strip():
                    report("mercado", f"Buscando precio de referencia para «{item.descripcion}» en {filename}")
                    research = research_market_price(item.descripcion, api_key=api_key)
                    proposed_usd = to_usd(
                        item.precio_unitario,
                        proposal.moneda,
                        project_context.get("bcv_rate") if project_context else None,
                    )
                    prices = research.precios_encontrados
                    if not prices:
                        market_status = "sin_datos"
                    elif proposed_usd is None:
                        market_status = "no_comparable"
                    elif research.confianza < 0.8:
                        market_status = "datos_insuficientes"
                    elif proposed_usd > max(price.precio_usd for price in prices):
                        market_status = "sobre_rango_observado"
                    elif proposed_usd > sum(price.precio_usd for price in prices) / len(prices):
                        market_status = "sobre_promedio_observado"
                    else:
                        market_status = "en_rango_o_menor"
                    average_price = (
                        sum(price.precio_usd for price in prices) / len(prices)
                        if prices
                        else None
                    )
                    market_reviews.append(
                        MarketPriceReview(
                            componente=item.descripcion,
                            precio_ofertado_usd=float(proposed_usd) if proposed_usd is not None else None,
                            minimo_mercado_usd=min((price.precio_usd for price in prices), default=None),
                            promedio_mercado_usd=average_price,
                            maximo_mercado_usd=max((price.precio_usd for price in prices), default=None),
                            confianza=research.confianza,
                            estado=market_status,
                            fuentes=[
                                PriceSource(
                                    url=price.url,
                                    precio_usd=price.precio_usd,
                                    fecha_consulta=price.fecha_consulta,
                                )
                                for price in prices
                            ],
                        )
                    )
                    report(
                        "mercado",
                        f"Búsqueda de «{item.descripcion}» finalizada: {len(prices)} referencia(s), "
                        f"estado {market_status.replace('_', ' ')}.",
                    )
        else:
            report("mercado", f"Se omitió la búsqueda de mercado para {filename} porque la propuesta fue descartada.")
        report("completado", f"Auditoría terminada: {filename}")
        audits.append(
            ResultadoAuditoria(
                propuesta=proposal,
                estado_documento=EstadoDocumento.COMPLETADO,
                descartada=discarded,
                motivos_descarte=reasons,
                aritmetica=arithmetic_assessment,
                tco=tco,
                factibilidad_financiera=financial_assessment,
                precios_mercado=market_reviews,
                alcance_estado=scope_status,
                alcance_advertencias=scope_warnings,
                technical_score=score,
                notas=(
                    "Descartada; revisar los motivos y su evidencia."
                    if discarded
                    else "Requiere revisión manual por resultados no concluyentes."
                    if scope_status != "cumple"
                    or (
                        financial_assessment
                        and financial_assessment.estado == "no_concluyente"
                    )
                    else "Validaciones determinísticas completadas."
                ),
            )
        )

    return audits, rank_audits(audits)
