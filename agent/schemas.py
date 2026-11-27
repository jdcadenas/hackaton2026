from enum import Enum
from datetime import datetime, timedelta
from typing import Literal, Optional

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
    moneda: Optional[str] = None
    completo: bool = True
    advertencias: list[str] = Field(default_factory=list)
    desglose: list[TCOConcepto] = Field(default_factory=list)


class PriceSource(BaseModel):
    url: str
    precio_usd: float
    fecha_consulta: str


class MarketPriceReview(BaseModel):
    componente: str
    precio_ofertado_usd: Optional[float] = None
    minimo_mercado_usd: Optional[float] = None
    maximo_mercado_usd: Optional[float] = None
    confianza: float = Field(ge=0, le=1)
    estado: Literal[
        "sobre_rango_observado",
        "en_rango_o_menor",
        "datos_insuficientes",
        "sin_datos",
        "no_comparable",
    ]
    fuentes: list[PriceSource] = Field(default_factory=list)


class FinancialAssessment(BaseModel):
    estado: Literal["dentro_presupuesto", "sobre_presupuesto", "no_concluyente"]
    moneda_propuesta: Optional[str] = None
    tco_propuesta: Optional[float] = None
    tco_usd: Optional[float] = None
    tco_ves: Optional[float] = None
    presupuesto_original: float
    moneda_presupuesto: str
    presupuesto_usd: Optional[float] = None
    diferencia_usd: Optional[float] = None
    tasa_bcv_ves_por_usd: float
    tasa_bcv_fecha: str
    tasa_bcv_fuente: str
    advertencias: list[str] = Field(default_factory=list)


class ProjectRequirement(BaseModel):
    descripcion: str
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    especificaciones: list[str] = Field(default_factory=list)
    terminos_clave: list[str] = Field(default_factory=list)
    evidencia: Evidencia


class ProjectRequirements(BaseModel):
    archivo: str = ""
    requisitos: list[ProjectRequirement] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)


class ResultadoAuditoria(BaseModel):
    propuesta: PropuestaExtraida
    descartada: bool = False
    motivos_descarte: list[str] = Field(default_factory=list)
    tco: Optional[TCO] = None
    factibilidad_financiera: Optional[FinancialAssessment] = None
    precios_mercado: list[MarketPriceReview] = Field(default_factory=list)
    alcance_estado: Literal["cumple", "incompleto", "no_concluyente"] = "no_concluyente"
    alcance_advertencias: list[str] = Field(default_factory=list)
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
