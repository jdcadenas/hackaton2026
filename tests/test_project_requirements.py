from types import SimpleNamespace

from agent.project_requirements import extract_project_requirements
from agent.schemas import Evidencia, ProjectRequirement, ProjectRequirements


def test_project_pdf_extraction_uses_schema_and_preserves_page_evidence(tmp_path, monkeypatch):
    pdf_path = tmp_path / "requerimientos.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    expected = ProjectRequirements(
        requisitos=[
            ProjectRequirement(
                descripcion="Laptop empresarial",
                cantidad=10,
                unidad="unidades",
                especificaciones=["16 GB RAM"],
                terminos_clave=["notebook"],
                evidencia=Evidencia(archivo="model-output.pdf", pagina=3, confianza=0.9),
            )
        ]
    )

    class FakeClient:
        def __enter__(self):
            self.models = self
            return self

        def __exit__(self, *_args):
            return False

        def generate_content(self, **kwargs):
            assert kwargs["model"] == "gemini-flash-latest"
            assert kwargs["config"].response_json_schema == ProjectRequirements.model_json_schema()
            return SimpleNamespace(text=expected.model_dump_json())

    monkeypatch.setattr("agent.project_requirements.genai.Client", lambda **_kwargs: FakeClient())
    result = extract_project_requirements(str(pdf_path), api_key="test-key")

    assert result.archivo == "requerimientos.pdf"
    assert result.requisitos[0].descripcion == "Laptop empresarial"
    assert result.requisitos[0].evidencia.pagina == 3


def test_project_pdf_extraction_reports_missing_gemini_key(tmp_path, monkeypatch):
    pdf_path = tmp_path / "requerimientos.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    result = extract_project_requirements(str(pdf_path))

    assert result.requisitos == []
    assert any("Falta GEMINI_API_KEY" in warning for warning in result.advertencias)
