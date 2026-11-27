import re
import unicodedata
from typing import List, Tuple
from agent.schemas import ProjectRequirements, PropuestaExtraida


_STOPWORDS = {"con", "del", "las", "los", "para", "por", "una", "uno", "que", "de", "la", "el", "y"}


def _tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return {
        token for token in re.findall(r"[a-z0-9]+", normalized)
        if token not in _STOPWORDS and len(token) > 1
    }


def _validate_project_requirements(
    propuesta: PropuestaExtraida,
    requirements: ProjectRequirements,
) -> Tuple[bool, List[str]]:
    reasons = []
    for requirement in requirements.requisitos:
        required_tokens = _tokens(requirement.descripcion + " " + " ".join(requirement.especificaciones))
        keyword_sets = [_tokens(term) for term in requirement.terminos_clave if _tokens(term)]
        numeric_tokens = set(re.findall(r"\d+(?:[.,]\d+)?", " ".join(requirement.especificaciones)))
        matches = []
        for item in propuesta.items:
            offered_tokens = _tokens(item.descripcion)
            offered_numbers = set(re.findall(r"\d+(?:[.,]\d+)?", item.descripcion))
            overlap = len(required_tokens & offered_tokens) / max(len(required_tokens), 1)
            keyword_match = any(
                len(keywords & offered_tokens) / max(len(keywords), 1) >= 0.5
                for keywords in keyword_sets
            )
            if (overlap >= 0.5 or keyword_match) and numeric_tokens.issubset(offered_numbers):
                matches.append(item)

        if not matches:
            reasons.append(
                f"No se encontró evidencia suficiente para el requisito «{requirement.descripcion}» "
                f"(PDF, pág. {requirement.evidencia.pagina or 'no identificada'})."
            )
            continue

        if requirement.cantidad is not None:
            supplied = sum(item.cantidad or 0 for item in matches)
            if supplied < requirement.cantidad:
                reasons.append(
                    f"Cantidad insuficiente para «{requirement.descripcion}»: "
                    f"{supplied:g} de {requirement.cantidad:g}."
                )
    return not reasons, reasons


def validate_scope(
    propuesta: PropuestaExtraida,
    requirements: ProjectRequirements | None = None,
) -> Tuple[bool, List[str]]:
    if requirements is not None:
        return _validate_project_requirements(propuesta, requirements)

    motivos = []
    
    total_equipos_computo = 0
    has_ups = False
    has_perifericos = False
    
    for item in propuesta.items:
        desc = item.descripcion.lower()
        # Check for computers / laptops / workstations
        if any(w in desc for w in ["computadora", "pc", "laptop", "equipo", "estación", "workstation", "desktop", "cpu"]):
            total_equipos_computo += item.cantidad or 0
        if "ups" in desc or "respaldo" in desc or "no-break" in desc:
            has_ups = True
        if any(w in desc for w in ["periférico", "teclado", "mouse", "ratón", "monitor", "pantalla", "combo"]):
            has_perifericos = True
            
    if total_equipos_computo < 11:
        motivos.append(f"Alcance insuficiente: se detectaron {total_equipos_computo} equipos de cómputo (se requieren al menos 11: 10 estudiantes + 1 docente).")
        
    if not has_ups:
        motivos.append("Alcance incompleto: no se detectó UPS obligatorio en la propuesta.")

    if not has_perifericos:
        motivos.append("Alcance incompleto: no se detectaron periféricos (por ejemplo, monitor, teclado o mouse).")

    is_valid = len(motivos) == 0
    return is_valid, motivos
