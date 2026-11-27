from datetime import datetime

import pytest
from pydantic import ValidationError

from agent.schemas import SalidaJSON


def valid_output():
    return {
        "reto": "propuesta_servicios",
        "repositorio": "propuesta_servicios",
        "commit": "",
        "inicio": "2026-11-27T00:00:00-04:00",
        "fin": "2026-11-27T00:01:00-04:00",
        "procesados": [{"archivo": "oferta.pdf", "hora": "2026-11-27T00:00:30-04:00"}],
        "ranking": ["oferta.pdf"],
    }


def test_salida_has_exact_keys_and_caracas_timezone():
    result = SalidaJSON.model_validate(valid_output())
    assert set(result.model_dump()) == set(valid_output())
    assert datetime.fromisoformat(result.inicio).utcoffset().total_seconds() == -4 * 3600


def test_salida_rejects_wrong_timezone():
    data = valid_output()
    data["fin"] = "2026-11-27T04:01:00Z"
    with pytest.raises(ValidationError):
        SalidaJSON.model_validate(data)


def test_salida_rejects_duplicate_ranking():
    data = valid_output()
    data["ranking"] = ["oferta.pdf", "oferta.pdf"]
    with pytest.raises(ValidationError):
        SalidaJSON.model_validate(data)


def test_salida_rejects_extra_keys():
    data = valid_output()
    data["extra"] = True
    with pytest.raises(ValidationError):
        SalidaJSON.model_validate(data)
