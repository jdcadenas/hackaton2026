import math
from typing import Any


def _retry_delay_seconds(value: Any) -> int | None:
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            retry_delay = current.get("retryDelay")
            if isinstance(retry_delay, str) and retry_delay.endswith("s"):
                try:
                    seconds = math.ceil(float(retry_delay[:-1]))
                except ValueError:
                    seconds = 0
                if seconds > 0:
                    return seconds
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return None


def _format_duration(seconds: int) -> str:
    days, seconds = divmod(seconds, 86_400)
    hours, seconds = divmod(seconds, 3_600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if days:
        parts.append(f"{days} d")
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} min")
    if seconds and not days:
        parts.append(f"{seconds} s")
    return " ".join(parts) or "menos de 1 s"


def format_gemini_error(error: Exception) -> str:
    code = getattr(error, "code", None)
    status = getattr(error, "status", None)

    if code == 429 or status == "RESOURCE_EXHAUSTED":
        delay = _retry_delay_seconds(getattr(error, "details", None))
        if delay:
            return (
                "Gemini agotó la cuota disponible (HTTP 429). "
                f"Google recomienda volver a intentar en {_format_duration(delay)}. "
                "Revisa también el plan y los límites de uso."
            )
        return (
            "Gemini agotó la cuota disponible (HTTP 429). "
            "Espera a que se restablezca o revisa el plan y los límites de uso."
        )
    if code == 503 or status == "UNAVAILABLE":
        return "Gemini no está disponible temporalmente (HTTP 503). Inténtalo de nuevo más tarde."
    if code == 404 or status == "NOT_FOUND":
        return "El modelo de Gemini no está disponible para esta cuenta (HTTP 404)."
    if code in {401, 403}:
        return f"Gemini rechazó la autenticación (HTTP {code}). Verifica la clave y los permisos."
    if code is not None:
        label = f" ({status})" if status else ""
        return f"Gemini devolvió un error HTTP {code}{label}. Revisa la configuración y los límites de uso."
    return str(error)
