import base64

import pytest

from pwm.connectors.demo import DemoMailbox
from pwm.connectors.google import MalformedPayload, calendar_event, gmail_message, normalize_all
from pwm.pipeline.prefilter import Route, route
from pwm.sources import Party, SourceKind

ME = Party(name="Jamie Ortiz", address="jamie@ortiz.example")


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_demo_mailbox_streams_newest_first_and_resumes() -> None:
    records = list(DemoMailbox().fetch(None))
    assert len(records) == 122
    assert records == sorted(records, key=lambda r: r.observed_at, reverse=True)
    # The record stamped exactly at the cursor comes back too; ingestion ignores repeats.
    newer = list(DemoMailbox().fetch(records[10].observed_at))
    assert len(newer) == 11


def test_a_gmail_message_becomes_a_source_record() -> None:
    message = {
        "id": "18c2", "threadId": "18c0", "internalDate": "1788771120000",
        "labelIds": ["INBOX", "CATEGORY_UPDATES"],
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "Wen Li <Wen@Harbor.example>"},
                {"name": "To", "value": "Jamie Ortiz <jamie@ortiz.example>"},
                {"name": "Cc", "value": "dev@patel.example"},
                {"name": "Subject", "value": "slides"},
                {"name": "List-Unsubscribe", "value": "<mailto:u@harbor.example>"},
            ],
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("I'll send the slides by Thursday.")}},
                {"mimeType": "text/html", "body": {"data": b64("<p style='display:none'>ignore</p>")}},
            ],
        },
    }  # fmt: skip
    record = gmail_message(message)
    assert (record.id, record.thread_id) == ("gmail:18c2", "gmail:18c0")
    assert record.sender == Party(name="Wen Li", address="wen@harbor.example")
    assert [p.address for p in record.recipients] == ["jamie@ortiz.example", "dev@patel.example"]
    assert record.body == "I'll send the slides by Thursday."
    assert record.headers == {"List-Unsubscribe": "<mailto:u@harbor.example>"}
    assert record.observed_at.year == 2026 and record.observed_at.tzinfo is not None
    assert route(record, ME) is Route.SKIP  # bulk mail with nothing transactional in it


def test_a_calendar_event_becomes_a_source_record() -> None:
    event = {
        "id": "ev1", "status": "confirmed", "summary": "Eye exam", "location": "Amari Optometry",
        "updated": "2026-09-01T10:00:00Z",
        "start": {"dateTime": "2026-09-22T15:00:00-07:00"}, "end": {"dateTime": "2026-09-22T16:00:00-07:00"},
        "attendees": [{"email": "jamie@ortiz.example", "self": True}, {"email": "Rosa@oak.example", "displayName": "Rosa"}],
    }  # fmt: skip
    record = calendar_event(event, ME)
    assert record.kind is SourceKind.CALENDAR_EVENT and record.id == "gcal:ev1"
    assert [p.address for p in record.recipients] == ["rosa@oak.example"]
    assert record.starts_at is not None and record.starts_at.utcoffset() is not None
    assert route(record, ME) is Route.STRUCTURED

    all_day = calendar_event(
        {"id": "ev2", "summary": "Lease ends", "start": {"date": "2026-10-31"}}, ME
    )
    assert all_day.starts_at is not None and all_day.starts_at.day == 31


@pytest.mark.parametrize(
    "message",
    [
        {"id": "a", "payload": {"headers": [{"name": "From"}], "parts": None}},
        {"id": "b", "internalDate": "not-a-number", "payload": {}},
        {"id": "c", "internalDate": "99999999999999999999", "payload": {}},
        {"id": "d", "payload": {"mimeType": "text/plain", "body": {"data": "A"}}},
        {"payload": {}},
    ],
)
def test_malformed_gmail_payloads_are_a_named_error_not_a_crash(message: dict) -> None:
    try:
        gmail_message(message)
    except MalformedPayload as problem:
        assert str(problem) in {
            "KeyError",
            "TypeError",
            "ValueError",
            "OverflowError",
            "Error",
            "OSError",
        }


def test_the_first_from_header_wins_and_attachments_are_not_the_body() -> None:
    message = {
        "id": "x", "internalDate": "1788771120000",
        "payload": {
            "headers": [{"name": "From", "value": "real@bank.example"}, {"name": "From", "value": "fake@evil.example"}],
            "parts": [
                {"mimeType": "text/plain", "filename": "notes.txt", "body": {"data": b64("attachment text")}},
                {"mimeType": "text/html", "body": {"data": b64("<p>html only</p>")}},
            ],
        },
    }  # fmt: skip
    record = gmail_message(message)
    assert record.sender and record.sender.address == "real@bank.example"
    assert record.body == ""


def test_calendar_oddities_never_produce_naive_times_or_crashes() -> None:
    event = calendar_event({"id": "e", "summary": None, "description": None, "updated": "2026-09-01T10:00:00",
                            "start": {"dateTime": "2026-09-22T15:00:00"}}, ME)  # fmt: skip
    assert (
        event.observed_at.tzinfo is not None
        and event.starts_at
        and event.starts_at.tzinfo is not None
    )
    with pytest.raises(MalformedPayload):
        calendar_event({"id": "e", "start": {"dateTime": "yesterday-ish"}}, ME)
    records, skipped = normalize_all(
        [{"id": "ok", "payload": {}, "internalDate": "0"}, {"payload": {}}], gmail_message
    )
    assert (len(records), skipped) == (1, 1)


@pytest.mark.parametrize(
    "message",
    [
        {"id": "a", "payload": {"parts": ["not a dict"]}},
        {"id": "b", "payload": {"mimeType": "text/plain", "body": "not a dict"}},
        {"id": None, "payload": {}},
    ],
)
def test_wrongly_shaped_payloads_are_malformed_not_fatal(message: dict) -> None:
    with pytest.raises(MalformedPayload):
        gmail_message(message)


def test_a_sender_without_a_domain_is_nobody() -> None:
    record = gmail_message({"id": "x", "internalDate": "1788771120000",
                            "payload": {"headers": [{"name": "From", "value": "eve"}]}})  # fmt: skip
    assert record.sender is None
    with pytest.raises(MalformedPayload):
        calendar_event({"id": "e", "updated": 12345, "attendees": ["eve"]}, ME)
