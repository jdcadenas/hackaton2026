from enum import Enum


class EstadoDocumento(str, Enum):
    PENDIENTE = "PENDIENTE"
    COMPLETADO = "COMPLETADO"
    NO_VERIFICADO = "NO_VERIFICADO"
    ERROR_API_503 = "ERROR_API_503"
