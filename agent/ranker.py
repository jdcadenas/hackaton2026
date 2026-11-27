from typing import List
from agent.schemas import ResultadoAuditoria

def rank_audits(audits: List[ResultadoAuditoria]) -> List[str]:
    # Keep one deterministic result per proposal filename.
    by_name = {}
    for audit in audits:
        by_name.setdefault(audit.propuesta.archivo, audit)
    unique_audits = list(by_name.values())
    validas = [a for a in unique_audits if not a.descartada]
    descartadas = [a for a in unique_audits if a.descartada]

    # Sort validas: -technical_score (descending score -> higher is better, so -score), then tco.total (ascending), then file name (ascending)
    validas.sort(key=lambda x: (-x.technical_score, x.tco.total if x.tco else 0.0, x.propuesta.archivo))
    
    # Sort descartadas: alphabetical by filename
    descartadas.sort(key=lambda x: x.propuesta.archivo)
    
    return [audit.propuesta.archivo for audit in validas + descartadas]
