from openpyxl import Workbook

from agent.extractor import extract_proposal


def test_xlsx_extraction_closes_workbook_and_does_not_invent_rows(tmp_path):
    path = tmp_path / "oferta.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Descripción", "Cantidad", "Unidad", "Precio unitario", "Subtotal"])
    sheet.append(["Equipo con datos", 1, "unidad", 125, 125])
    workbook.save(path)

    proposal = extract_proposal(str(path))

    assert len(proposal.items) == 1
    assert proposal.items[0].subtotal == 125
    assert proposal.totales_declarados.subtotal is None
    path.unlink()
    assert not path.exists()
