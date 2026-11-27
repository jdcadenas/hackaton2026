import os
from typing import Callable, List, Optional, Tuple

from agent.extractor import extract_proposal
from agent.market.search_grounding import research_market_price
from agent.ranker import rank_audits
from agent.schemas import PropuestaExtraida, ResultadoAuditoria
from agent.tco import calculate_tco
from agent.validators.arithmetic import validate_arithmetic
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
                anomalias_ingesta=[f"Error inesperado durante la extracción: {exc}"],
            )
        proposal.archivo = filename

        reasons: list[str] = []
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

        if not reasons:
            report("validacion", f"Validando aritmética, alcance y compatibilidad: {filename}")
            for validator in (validate_arithmetic, validate_scope, validate_compatibility):
                is_valid, validator_reasons = validator(proposal)
                if not is_valid:
                    reasons.extend(validator_reasons)
                    break

        discarded = bool(reasons)
        tco = None
        if proposal.totales_declarados.subtotal is not None:
            try:
                tco = calculate_tco(proposal)
            except ValueError as exc:
                reasons.append(str(exc))
                discarded = True

        score = 0.0 if discarded else 100.0
        if not discarded:
            report("mercado", f"Consultando precios con Google Search: {filename}")
            for item in proposal.items:
                if item.descripcion.strip():
                    research_market_price(item.descripcion, api_key=api_key)
        report("completado", f"Auditoría terminada: {filename}")
        audits.append(
            ResultadoAuditoria(
                propuesta=proposal,
                descartada=discarded,
                motivos_descarte=reasons,
                tco=tco,
                technical_score=score,
                notas="Validaciones determinísticas completadas." if not discarded else "Descartada; revisar los motivos y su evidencia.",
            )
        )

    return audits, rank_audits(audits)
