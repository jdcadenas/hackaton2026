from typing import List
from agent.schemas import PropuestaExtraida, TCO, TCOConcepto, ClausulaCategoria

def calculate_tco(propuesta: PropuestaExtraida) -> TCO:
    base = propuesta.totales_declarados.subtotal
    if base is None:
        raise ValueError("No se puede calcular el TCO sin subtotal declarado.")
    desglose: List[TCOConcepto] = [
        TCOConcepto(concepto="Subtotal base declarado", monto=base)
    ]
    
    flete = 0.0
    recargos = 0.0
    
    ubicacion = (propuesta.ubicacion_proveedor or "").lower()
    fuera_de_caracas = bool(ubicacion) and "caracas" not in ubicacion
    
    # Check clauses for flete, recargo, etc.
    flete_incluido = True
    for clausula in propuesta.clausulas:
        c_text = clausula.texto.lower()
        if clausula.categoria == ClausulaCategoria.flete or "flete" in c_text or "transporte" in c_text or "envío" in c_text:
            if "no incluye" in c_text or "sin flete" in c_text or "por cuenta del cliente" in c_text:
                flete_incluido = False
        
        if clausula.categoria == ClausulaCategoria.recargo or "recargo" in c_text:
            monto_rec = clausula.impacto_estimado_usd
            if monto_rec is None:
                import re

                percentage = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:%|por ciento)", c_text)
                monto_rec = base * float(percentage.group(1).replace(",", ".")) / 100 if percentage else 0.0
            recargos += monto_rec
            desglose.append(TCOConcepto(concepto=f"Recargo: {clausula.texto[:40]}", monto=monto_rec))
            
    if not flete_incluido and fuera_de_caracas:
        flete = 580.0
        desglose.append(TCOConcepto(concepto="Flete de referencia (Maracaibo -> Caracas)", monto=flete))
    elif not flete_incluido and not ubicacion:
        desglose.append(TCOConcepto(concepto="Flete no cuantificado: ubicación del proveedor no indicada", monto=0.0))
        
    subtotal_con_adicionales = base + flete + recargos
    
    # IVA 16% por defecto
    iva = subtotal_con_adicionales * 0.16
    desglose.append(TCOConcepto(concepto="IVA (16%)", monto=iva))
    
    total = subtotal_con_adicionales + iva
    
    return TCO(
        base=base,
        flete=flete,
        recargos=recargos,
        iva=iva,
        total=total,
        desglose=desglose
    )
