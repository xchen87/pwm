from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.ask.answer import TemplateReasoner
from pwm.ask.facts import Fact
from pwm.ask.retrieval import Intent, detect_intent, retrieve
from pwm.config import get_settings
from pwm.db.models import Assertion, ReviewEvent, Source

TODAY = date(2026, 9, 12)


@pytest.fixture(autouse=True)
def demo_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWM_FIXED_NOW", "2026-09-12T09:00:00+00:00")
    assert get_settings().fixed_now is not None


def fact(id: str, **fields: object) -> Fact:
    base = {
        "kind": "commitment", "subject": "Alex", "predicate": "committed_to", "value": "send the deck",
        "evidence_quote": "I'll send the deck", "observed_at": datetime(2026, 9, 1, tzinfo=UTC),
        "direction": "by_user", "committed_to": "Wen Li",
    }  # fmt: skip
    return Fact(id=id, **{**base, **fields})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What did I promise Wen?", Intent.MY_COMMITMENTS),
        ("What is Wen supposed to send me?", Intent.OWED_TO_ME),
        ("Why did we decide to repair the roof?", Intent.DECISION),
        ("What deadlines do I have coming up?", Intent.DEADLINES),
        ("When is the eye exam?", Intent.WHEN),
        ("What was the quote originally?", Intent.HISTORY),
        ("What is Rosa's phone number?", Intent.LOOKUP),
    ],
)
def test_intents(question: str, intent: Intent) -> None:
    assert detect_intent(question) is intent


def test_direction_matters() -> None:
    mine = fact("1")
    theirs = fact("2", direction="to_user", committed_by="Wen Li", value="review the deck")
    assert [f.id for f in retrieve("What did I promise Wen?", [mine, theirs], TODAY).facts] == ["1"]
    assert [
        f.id for f in retrieve("What is Wen supposed to send me?", [mine, theirs], TODAY).facts
    ] == ["2"]


def test_a_question_about_something_never_seen_is_declined() -> None:
    policy = fact("1", kind="thing", subject="Auto insurance policy", predicate="annual_premium",
                  value="1284", evidence_quote="premium is $1,284", direction=None)  # fmt: skip
    retrieved = retrieve("When does my boat insurance renew?", [policy], TODAY)
    assert retrieved.facts == [] and "boat" in retrieved.unknown_terms
    answer = TemplateReasoner().answer("…", retrieved)
    assert not answer.grounded and answer.cited == [] and "boat" in answer.text


def test_superseded_facts_answer_only_questions_about_the_past() -> None:
    old = fact("old", kind="thing", subject="Kitchen", predicate="quote", value="18400",
               evidence_quote="quote is $18,400", superseded=True, direction=None)  # fmt: skip
    new = fact("new", kind="thing", subject="Kitchen", predicate="quote", value="19950",
               evidence_quote="revised total is $19,950", previous_value="18400", direction=None)  # fmt: skip
    assert [f.id for f in retrieve("What is the kitchen quote?", [old, new], TODAY).facts] == [
        "new"
    ]
    assert (
        retrieve("What was the kitchen quote originally?", [old, new], TODAY).facts[0].id == "old"
    )


def test_unconfirmed_evidence_is_hedged_and_confirmed_is_not() -> None:
    guess, sure = fact("1"), fact("2", is_fact=True, value="send the final deck")
    answer = TemplateReasoner().answer(
        "q", retrieve("What did I promise Wen?", [guess, sure], TODAY)
    )
    lines = answer.text.splitlines()[1:]
    assert sum(line.startswith("• Possibly:") for line in lines) == 1
    assert answer.caveat and "confirmed" in answer.caveat


def test_ask_over_the_api_cites_real_assertions(client: TestClient, session: Session) -> None:
    answer = client.post("/ask", json={"question": "What did I promise Tom?"}).json()
    assert answer["grounded"] and "Q3" in answer["cited"][0]["evidence_quote"]
    assert session.get(Assertion, answer["cited"][0]["assertion_id"]) is not None

    nothing = client.post("/ask", json={"question": "What did I promise Beatrice?"}).json()
    assert not nothing["grounded"] and nothing["cited"] == []
    planted = client.post("/ask", json={"question": "Did I agree to pay PayFast $500?"}).json()
    assert planted["cited"] == []
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_remember_then_ask_then_forget(client: TestClient, session: Session) -> None:
    memory = client.post(
        "/memories", json={"text": "The spare key is with Marguerite next door."}
    ).json()
    assert memory["review"] == "confirmed" and memory["origin"] == "user_stated"
    assert session.scalars(select(ReviewEvent.action)).all() == ["remember"]

    answer = client.post("/ask", json={"question": "Where is the spare key?"}).json()
    assert answer["grounded"] and "Marguerite" in answer["text"]
    assert any("spare key" in r["what"] for r in client.get("/home").json()["remembered"])

    assert client.delete(f"/memories/{memory['id']}").status_code == 200
    assert not client.post("/ask", json={"question": "Where is the spare key?"}).json()["grounded"]
    assert session.scalars(select(Source).where(Source.external_id.like("capture:%"))).all() == []
    assert client.delete(f"/memories/{memory['id']}").status_code == 404


def test_what_is_read_out_of_a_note_is_still_only_a_possibility(client: TestClient) -> None:
    client.post("/memories", json={"text": "Renew the car registration by October 20."})
    found = [
        i for i in client.get("/commitments").json() if "car registration" in i["evidence_quote"]
    ]
    assert found and found[0]["review"] == "unreviewed" and found[0]["due"] == "2026-10-20"


def test_blank_memories_are_refused(client: TestClient) -> None:
    assert client.post("/memories", json={"text": "  "}).status_code == 422


def test_possessives_and_curly_apostrophes_do_not_become_search_terms() -> None:
    from pwm.ask.retrieval import words

    assert words("What is Dana’s new phone number?") == words("What is Dana's new phone number?")
    assert "s" not in words("What is Dana’s number?") and "dana" in words("Dana’s")
