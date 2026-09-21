from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from pwm.db.models import Assertion, AssertionRelation


def inferred(client: TestClient) -> dict:
    for person in client.get("/people").json():
        for identifier in person["identifiers"]:
            if identifier["link"] == "inferred":
                return {**identifier, "person": person["name"]}
    raise AssertionError("no inferred link in the fixture")


def test_people_lists_inferred_links_for_the_user_to_judge(client: TestClient) -> None:
    people = client.get("/people").json()
    links = {i["address"]: i["link"] for p in people for i in p["identifiers"]}
    assert links["priya.n@example.com"] == "exact"
    assert links["priya@natarajan-design.example"] == "inferred"
    assert all("examp1e" not in address for address in links)


def test_confirming_a_link_lets_the_second_address_speak_for_the_person(
    client: TestClient, session: Session
) -> None:
    from pwm.extraction.candidates import Candidate, CandidateKind, Origin
    from pwm.extraction.interface import ExtractionRequest, ExtractionResult, TriageResult
    from pwm.pipeline.heuristic import HeuristicExtractor

    class AlsoReadsTheChangeOfPlan(HeuristicExtractor):
        """The stand-in misses Priya's "change of plan"; a better extractor would not."""

        def extract(self, request: ExtractionRequest) -> ExtractionResult:
            found = super().extract(request)
            if request.source.id != "e_mom_3":
                return found
            extra = Candidate(
                source_id="e_mom_3", kind=CandidateKind.EVENT, subject="Mom's 70th", predicate="date",
                value="2026-09-27T18:00", origin=Origin.SOURCE_EXPLICIT,
                evidence_quote="Luca's can only give us the back room on Sunday the 27th at 6pm",
            )  # fmt: skip
            return ExtractionResult(candidates=(*found.candidates, extra))

    class ReadsEverything:
        """The stand-in triager also drops that message; this test is about identity."""

        version = "test-triage"

        def is_relevant(self, request: ExtractionRequest) -> TriageResult:
            return TriageResult(relevant=True)

    import pwm.api.people as people_api

    original = people_api.build_stages
    people_api.build_stages = lambda: (ReadsEverything(), AlsoReadsTheChangeOfPlan())  # type: ignore[assignment]
    try:
        link = next(
            i for p in client.get("/people").json() for i in p["identifiers"]
            if i["address"] == "priya@natarajan-design.example"
        )  # fmt: skip
        # Before: Priya's second address may only dispute the Saturday plan.
        from pwm.db.models import User
        from pwm.pipeline.store import process_user

        user = session.scalars(select(User)).one()
        process_user(session, user, ReadsEverything(), AlsoReadsTheChangeOfPlan())
        saturday = session.scalars(select(Assertion).where(Assertion.value == "2026-09-26")).one()
        assert saturday.superseded_by_id is None

        assert client.post(f"/people/identifiers/{link['id']}/confirm").status_code == 200
        session.refresh(saturday)
        sunday = session.get_one(Assertion, saturday.superseded_by_id)
        assert sunday.source.external_id == "e_mom_3"
        kinds = session.scalars(
            select(AssertionRelation.type).where(AssertionRelation.to_id == saturday.id)
        ).all()
        assert "supersedes" in kinds
    finally:
        people_api.build_stages = original  # type: ignore[assignment]


def test_rejecting_a_link_makes_it_a_separate_person_for_good(client: TestClient) -> None:
    link = inferred(client)
    assert (
        client.post(
            f"/people/identifiers/{link['id']}/split", json={"name": "Someone else"}
        ).status_code
        == 200
    )
    people = {
        p["name"]: [i["address"] for i in p["identifiers"]] for p in client.get("/people").json()
    }
    assert people["Someone else"] == [link["address"]]
    assert link["address"] not in people[link["person"]]
    assert (
        client.post(f"/people/identifiers/{link['id']}/split", json={"name": ""}).status_code == 422
    )
