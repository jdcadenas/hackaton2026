from types import SimpleNamespace

from PIL import Image
from openpyxl import Workbook

from agent.extractor import extract_proposal
from agent.schemas import Evidencia, Item, PropuestaExtraida, TotalesDeclarados


def test_image_extraction_uses_gemini_json_schema(tmp_path, monkeypatch):
    path = tmp_path / "oferta.png"
    Image.new("RGB", (10, 10), "white").save(path)
    expected = PropuestaExtraida(
        archivo=path.name,
        fuente="image",
        proveedor="Proveedor de prueba",
        items=[
            Item(
                descripcion="Laptop",
                cantidad=1,
                precio_unitario=100,
                subtotal=100,
                evidencia=Evidencia(archivo=path.name, pagina=1, confianza=0.9),
            )
        ],
        totales_declarados=TotalesDeclarados(subtotal=100, impuestos=16, total=116),
        moneda="USD",
        confianza_global=0.9,
    )

    class FakeClient:
        def __enter__(self):
            self.models = self
            return self

        def __exit__(self, *_args):
            return False

        def generate_content(self, **kwargs):
            assert kwargs["model"] == "gemini-flash-latest"
            assert kwargs["config"].response_json_schema == PropuestaExtraida.model_json_schema()
            return SimpleNamespace(text=expected.model_dump_json())

    monkeypatch.setattr("agent.extractor.genai.Client", lambda **_kwargs: FakeClient())
    proposal = extract_proposal(str(path), api_key="test-key")

    assert proposal.proveedor == "Proveedor de prueba"
    assert proposal.totales_declarados.total == 116


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
