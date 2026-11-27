from agent.schemas import (
    Clausula,
    ClausulaCategoria,
    Evidencia,
    FuenteEnum,
    Item,
    PropuestaExtraida,
    TotalesDeclarados,
)


def evidencia():
    return Evidencia(archivo="oferta.pdf", pagina=1, confianza=0.95)


def propuesta(
    items=None,
    clauses=None,
    subtotal=100.0,
    impuestos=16.0,
    total=116.0,
    archivo="oferta.pdf",
    location="Caracas",
):
    return PropuestaExtraida(
        archivo=archivo,
        fuente=FuenteEnum.pdf,
        proveedor="Proveedor",
        ubicacion_proveedor=location,
        items=items if items is not None else [
            Item(
                descripcion="Equipo",
                cantidad=1,
                unidad="unidad",
                precio_unitario=100,
                subtotal=100,
                evidencia=evidencia(),
            )
        ],
        clausulas=clauses or [],
        totales_declarados=TotalesDeclarados(subtotal=subtotal, impuestos=impuestos, total=total),
    )


def clausula(text, category=ClausulaCategoria.otro, impact=None):
    return Clausula(texto=text, categoria=category, impacto_estimado_usd=impact, evidencia=evidencia())
