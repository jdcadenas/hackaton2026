from types import SimpleNamespace

from google.genai.errors import ClientError, ServerError

import agent.project_requirements as project_requirements_module
from agent.project_requirements import extract_project_requirements
from agent.schemas import Evidencia, ProjectRequirement, ProjectRequirements
from agent.status import EstadoDocumento


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
            assert kwargs["model"] == "gemini-3.8-flash"
            assert kwargs["config"].response_json_schema == ProjectRequirements.model_json_schema()
            return SimpleNamespace(text=expected.model_dump_json())

    monkeypatch.setattr("agent.project_requirements.genai.Client", lambda **_kwargs: FakeClient())
    result = extract_project_requirements(str(pdf_path), api_key="test-key")

    assert result.archivo == "requerimientos.pdf"
    assert result.requisitos[0].descripcion == "Laptop empresarial"
    assert result.requisitos[0].evidencia.pagina == 3


def test_project_pdf_extraction_retries_unavailable_then_uses_fallback(tmp_path, monkeypatch):
    pdf_path = tmp_path / "requerimientos.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    expected = ProjectRequirements(
        requisitos=[
            ProjectRequirement(
                descripcion="Laptop",
                evidencia=Evidencia(archivo=pdf_path.name, pagina=1, confianza=0.9),
            )
        ]
    )
    model_calls = []
    sleep_delays = []

    class FakeClient:
        def __enter__(self):
            self.models = self
            return self

        def __exit__(self, *_args):
            return False

        def generate_content(self, **kwargs):
            model_calls.append(kwargs["model"])
            if kwargs["model"] == "gemini-3.8-flash":
                raise ServerError(503, {"error": {"status": "UNAVAILABLE"}})
            return SimpleNamespace(text=expected.model_dump_json())

    monkeypatch.setattr("agent.project_requirements.genai.Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(project_requirements_module.time, "sleep", sleep_delays.append)
    monkeypatch.setattr(
        project_requirements_module.random,
        "uniform",
        lambda lower, upper: (lower + upper) / 2,
    )

    result = extract_project_requirements(str(pdf_path), api_key="test-key")

    assert model_calls == ["gemini-3.8-flash"] * 5 + ["models/gemini-3.5-flash-lite"]
    assert sleep_delays == [2, 4, 8, 16]
    assert result.requisitos[0].descripcion == "Laptop"
    assert any("modelo alternativo" in warning for warning in result.advertencias)


def test_project_pdf_extraction_does_not_fallback_on_non_503_error(tmp_path, monkeypatch):
    pdf_path = tmp_path / "requerimientos.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    model_calls = []

    class FakeClient:
        def __enter__(self):
            self.models = self
            return self

        def __exit__(self, *_args):
            return False

        def generate_content(self, **kwargs):
            model_calls.append(kwargs["model"])
            raise ClientError(401, {"error": {"status": "UNAUTHENTICATED"}})

    monkeypatch.setattr("agent.project_requirements.genai.Client", lambda **_kwargs: FakeClient())

    result = extract_project_requirements(str(pdf_path), api_key="test-key")

    assert model_calls == ["gemini-3.8-flash"]
    assert result.requisitos == []
    assert "401" in result.advertencias[0]


def test_project_pdf_extraction_marks_unverified_if_fallback_fails(tmp_path, monkeypatch):
    pdf_path = tmp_path / "requerimientos.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    model_calls = []

    class FakeClient:
        def __enter__(self):
            self.models = self
            return self

        def __exit__(self, *_args):
            return False

        def generate_content(self, **kwargs):
            model_calls.append(kwargs["model"])
            raise ServerError(503, {"error": {"status": "UNAVAILABLE"}})

    monkeypatch.setattr("agent.project_requirements.genai.Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(project_requirements_module.time, "sleep", lambda _delay: None)

    result = extract_project_requirements(str(pdf_path), api_key="test-key")

    assert model_calls == ["gemini-3.8-flash"] * 5 + ["models/gemini-3.5-flash-lite"]
    assert result.requisitos == []
    assert result._estado_evaluacion == EstadoDocumento.ERROR_API_503
    assert "falló el modelo alternativo" in result.advertencias[0]


def test_project_pdf_extraction_reports_missing_gemini_key(tmp_path, monkeypatch):
    pdf_path = tmp_path / "requerimientos.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    result = extract_project_requirements(str(pdf_path))

    assert result.requisitos == []
    assert result._estado_evaluacion == EstadoDocumento.NO_VERIFICADO
    assert any("Falta GEMINI_API_KEY" in warning for warning in result.advertencias)
