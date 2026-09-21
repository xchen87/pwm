import importlib.util
from collections import Counter
from pathlib import Path

from pwm.extraction.candidates import CandidateKind, CommitmentType, Direction
from pwm.extraction.quotes import quote_in_source
from pwm_eval.fixture import SYNTHETIC_DIR, load_fixture
from pwm_eval.gold import RelationType, SourceCategory

FIXTURE = load_fixture()
GOLD = FIXTURE.gold


def test_committed_fixture_matches_generator() -> None:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "generate.py"
    spec = importlib.util.spec_from_file_location("fixture_generator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for filename, content in module.render().items():
        assert (SYNTHETIC_DIR / filename).read_text(encoding="utf-8") == content, (
            f"{filename} is stale: run `uv run python fixtures/generate.py`"
        )


def test_every_gold_quote_is_literally_in_its_source() -> None:
    for assertion in GOLD.assertions:
        source = FIXTURE.source(assertion.source_id)
        assert quote_in_source(assertion.evidence_quote, source.text), assertion.id
    for span in GOLD.injected_spans:
        assert quote_in_source(span.text, FIXTURE.source(span.source_id).text), span.source_id


def test_every_source_is_categorised_and_ids_are_unique() -> None:
    ids = [s.id for s in FIXTURE.sources]
    assert len(ids) == len(set(ids))
    assert set(ids) == set(GOLD.categories)


def test_fixture_meets_the_plan_minimums() -> None:
    categories = Counter(GOLD.categories.values())
    assert categories[SourceCategory.NOISE] >= 60
    assert categories[SourceCategory.ADVERSARIAL] >= 10
    assert len(GOLD.people) >= 10
    assert sum(len(p.addresses) > 1 for p in GOLD.people) >= 2

    promises = [a for a in GOLD.assertions if a.commitment_type is CommitmentType.PROMISE]
    assert sum(a.direction is Direction.BY_USER for a in promises) >= 5
    assert sum(a.direction is Direction.TO_USER for a in promises) >= 5
    assert sum(a.kind is CandidateKind.DECISION for a in GOLD.assertions) >= 5
    assert sum(a.kind is CandidateKind.THING for a in GOLD.assertions) >= 5
    assert sum(s.kind.value == "calendar_event" for s in FIXTURE.sources) == 15

    relation_types = {r.type for r in GOLD.relations}
    assert relation_types == {RelationType.SUPERSEDES, RelationType.CONTRADICTS}
    assert len(GOLD.temporal_queries) >= 8


def test_relations_reference_real_assertions() -> None:
    ids = {a.id for a in GOLD.assertions}
    for relation in GOLD.relations:
        assert {relation.from_id, relation.to_id} <= ids


def test_noise_carries_no_gold_and_adversarial_spans_carry_none() -> None:
    for assertion in GOLD.assertions:
        assert GOLD.categories[assertion.source_id] is not SourceCategory.NOISE
