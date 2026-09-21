import base64

from pwm.connectors.demo import DemoMailbox
from pwm.connectors.google import calendar_event, gmail_message
from pwm.pipeline.prefilter import Route, route
from pwm.sources import Party, SourceKind

ME = Party(name="Jamie Ortiz", address="jamie@ortiz.example")


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def test_demo_mailbox_streams_newest_first_and_resumes() -> None:
    records = list(DemoMailbox().fetch(None))
    assert len(records) == 122
    assert records == sorted(records, key=lambda r: r.observed_at, reverse=True)
    newer = list(DemoMailbox().fetch(records[10].observed_at))
    assert len(newer) == 10


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
