from enum import Enum
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FuenteEnum(str, Enum):
    pdf = "pdf"
    image = "image"
    excel = "excel"
    manual = "manual"


class ClausulaCategoria(str, Enum):
    flete = "flete"
    seguro = "seguro"
    traslado = "traslado"
    garantia = "garantia"
    recargo = "recargo"
    exclusion = "exclusion"
    software_trial = "software_trial"
    penalidad = "penalidad"
    otro = "otro"


class Evidencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archivo: str
    pagina: Optional[int] = None
    bbox: Optional[list[float]] = None
    url: Optional[str] = None
    confianza: float = Field(ge=0, le=1)


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descripcion: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    precio_unitario: Optional[float] = None
    subtotal: Optional[float] = None
    evidencia: Evidencia


class Clausula(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str
    categoria: ClausulaCategoria
    impacto_estimado_usd: Optional[float] = None
    evidencia: Evidencia


class TotalesDeclarados(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subtotal: Optional[float] = None
    impuestos: Optional[float] = None
    total: Optional[float] = None


class PropuestaExtraida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archivo: str
    fuente: FuenteEnum
    proveedor: Optional[str] = None
    ubicacion_proveedor: Optional[str] = None
    items: list[Item] = Field(default_factory=list)
    clausulas: list[Clausula] = Field(default_factory=list)
    totales_declarados: TotalesDeclarados = Field(default_factory=TotalesDeclarados)
    moneda: Optional[str] = None
    confianza_global: float = Field(default=0, ge=0, le=1)
    anomalias_ingesta: list[str] = Field(default_factory=list)


class TCOConcepto(BaseModel):
    concepto: str
    monto: float


class TCO(BaseModel):
    base: float
    flete: float
    recargos: float
    iva: float
    total: float
    desglose: list[TCOConcepto] = Field(default_factory=list)


class ResultadoAuditoria(BaseModel):
    propuesta: PropuestaExtraida
    descartada: bool = False
    motivos_descarte: list[str] = Field(default_factory=list)
    tco: Optional[TCO] = None
    technical_score: float = 0.0
    notas: str = ""


class ProcesadoItem(BaseModel):
    archivo: str
    hora: str

    @field_validator("hora")
    @classmethod
    def validate_hora(cls, value: str) -> str:
        _validate_caracas_timestamp(value)
        return value


class SalidaJSON(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reto: str = "propuesta_servicios"
    repositorio: str
    commit: str
    inicio: str
    fin: str
    procesados: list[ProcesadoItem] = Field(default_factory=list)
    ranking: list[str] = Field(default_factory=list)

    @field_validator("inicio", "fin")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        _validate_caracas_timestamp(value)
        return value

    @model_validator(mode="after")
    def validate_ranking(self) -> "SalidaJSON":
        if len(self.ranking) != len(set(self.ranking)):
            raise ValueError("ranking no puede contener archivos duplicados.")
        return self


def _validate_caracas_timestamp(value: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Debe ser una fecha ISO 8601.") from exc
    if parsed.utcoffset() != timedelta(hours=-4):
        raise ValueError("La fecha debe incluir el huso horario de Caracas (-04:00).")
