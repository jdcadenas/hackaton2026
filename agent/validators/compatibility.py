import re
from typing import List, Tuple

from agent.schemas import PropuestaExtraida


_SOCKETS = re.compile(r"\b(?:am[2345]|lga\s*\d{3,5}|s[rt]\d{3,5})\b", re.I)
_RAM_TYPES = re.compile(r"\bddr[45]\b", re.I)
_LENGTH = re.compile(r"\b(\d{2,3})\s*mm\b", re.I)
_WATTS = re.compile(r"\b(\d{2,4})\s*w\b", re.I)


def _first_number(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    return int(match.group(1)) if match else None


def validate_compatibility(propuesta: PropuestaExtraida) -> Tuple[bool, List[str]]:
    motivos = []
    descriptions = [item.descripcion for item in propuesta.items]
    cpu = next((text for text in descriptions if re.search(r"\b(cpu|procesador|ryzen|core\s*i[3579])\b", text, re.I)), "")
    board = next((text for text in descriptions if re.search(r"\b(placa|motherboard|tarjeta madre)\b", text, re.I)), "")
    memory = next((text for text in descriptions if re.search(r"\b(ram|memoria)\b", text, re.I)), "")
    gpu = next((text for text in descriptions if re.search(r"\b(gpu|tarjeta gráfica|tarjeta grafica|rtx|radeon)\b", text, re.I)), "")
    case = next((text for text in descriptions if re.search(r"\b(gabinete|case|chasis)\b", text, re.I)), "")
    psu = next((text for text in descriptions if re.search(r"\b(fuente|psu)\b", text, re.I)), "")
    ups = next((text for text in descriptions if re.search(r"\b(ups|no-break|nobreak)\b", text, re.I)), "")

    cpu_sockets, board_sockets = _SOCKETS.findall(cpu), _SOCKETS.findall(board)
    if cpu_sockets and board_sockets and not set(map(str.lower, cpu_sockets)) & set(map(str.lower, board_sockets)):
        motivos.append(f"Incompatibilidad de socket: CPU ({cpu_sockets[0]}) y placa ({board_sockets[0]}).")

    memory_types, board_memory_types = _RAM_TYPES.findall(memory), _RAM_TYPES.findall(board)
    if memory_types and board_memory_types and not set(map(str.lower, memory_types)) & set(map(str.lower, board_memory_types)):
        motivos.append(f"Incompatibilidad de memoria: RAM ({memory_types[0]}) y placa ({board_memory_types[0]}).")

    gpu_length, case_clearance = _first_number(_LENGTH, gpu), _first_number(_LENGTH, case)
    if gpu_length and case_clearance and gpu_length > case_clearance:
        motivos.append(f"La GPU mide {gpu_length} mm y excede los {case_clearance} mm del gabinete.")

    psu_watts = _first_number(_WATTS, psu)
    explicit_load = sum(
        (_first_number(_WATTS, text) or 0) * (item.cantidad or 1)
        for item, text in zip(propuesta.items, descriptions)
        if text not in (psu, ups)
    )
    if psu_watts and explicit_load and psu_watts < explicit_load:
        motivos.append(f"Fuente insuficiente: {psu_watts} W frente a una carga explícita de {explicit_load:g} W.")

    ups_watts = _first_number(_WATTS, ups)
    if ups_watts and explicit_load and ups_watts < explicit_load:
        motivos.append(f"UPS insuficiente: {ups_watts} W frente a una carga explícita de {explicit_load:g} W.")

    is_valid = len(motivos) == 0
    return is_valid, motivos
