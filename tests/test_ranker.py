from agent.schemas import ResultadoAuditoria, TCO
from agent.ranker import rank_audits
from tests.conftest import propuesta


def audit(name, discarded=False, score=0, total=100):
    result = ResultadoAuditoria(
        propuesta=propuesta(archivo=name),
        descartada=discarded,
        technical_score=score,
    )
    result.tco = TCO(base=total, flete=0, recargos=0, iva=0, total=total)
    return result


def test_ranker_places_valid_before_discarded():
    assert rank_audits([audit("bad.pdf", True), audit("ok.pdf", score=1)]) == ["ok.pdf", "bad.pdf"]


def test_ranker_breaks_score_ties_by_tco_then_name():
    assert rank_audits([
        audit("c.pdf", score=10, total=90),
        audit("b.pdf", score=10, total=80),
        audit("a.pdf", score=10, total=80),
    ]) == ["a.pdf", "b.pdf", "c.pdf"]


def test_ranker_prefers_higher_technical_score():
    assert rank_audits([audit("a.pdf", score=50, total=50), audit("b.pdf", score=80, total=90)]) == ["b.pdf", "a.pdf"]


def test_ranker_has_no_duplicate_names():
    assert rank_audits([audit("same.pdf", score=1), audit("same.pdf", discarded=True)]) == ["same.pdf"]
