from typing import List, Tuple
from agent.schemas import PropuestaExtraida

def validate_scope(propuesta: PropuestaExtraida) -> Tuple[bool, List[str]]:
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
