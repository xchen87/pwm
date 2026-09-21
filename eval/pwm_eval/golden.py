"""Label a real mailbox locally to build the golden set (AGENT.md Task 0.6).

Input is an mbox file, for example from Google Takeout. Output goes to ./golden/, which
is gitignored. Message content never leaves this machine through this tool, and only
scores, never content, are recorded when the golden set is evaluated.

Run:  uv run python -m pwm_eval.golden path/to/mail.mbox [--limit 200]
Then: uv run python -m pwm_eval.run --fixture golden
"""

import argparse
import json
import mailbox
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from email.message import Message
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path

from pwm.extraction.candidates import CandidateKind, CommitmentType, Direction, Origin
from pwm.extraction.quotes import quote_in_source
from pwm.sources import Party, SourceKind, SourceRecord
from pwm_eval.gold import Gold, GoldAssertion, SourceCategory

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "golden"
KEPT_HEADERS = ("List-Unsubscribe", "Precedence", "Auto-Submitted")


def plain_text(message: Message) -> str:
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if part.get_content_type() == "text/plain":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    return ""


def parties(message: Message, *headers: str) -> tuple[Party, ...]:
    values = [str(v) for h in headers for v in message.get_all(h, [])]
    return tuple(Party(name=n or None, address=a) for n, a in getaddresses(values) if a)


def to_source(message: Message, index: int) -> SourceRecord:
    try:
        observed = parsedate_to_datetime(str(message["Date"]))
    except (TypeError, ValueError):
        observed = datetime.fromtimestamp(0, UTC)
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=UTC)
    senders = parties(message, "From")
    return SourceRecord(
        id=f"golden_{index:05d}",
        kind=SourceKind.EMAIL,
        observed_at=observed,
        thread_id=str(message.get("X-GM-THRID") or message.get("Subject", "")),
        sender=senders[0] if senders else None,
        recipients=parties(message, "To", "Cc"),
        subject=str(message.get("Subject", "")),
        body=plain_text(message),
        headers={h: str(message[h]) for h in KEPT_HEADERS if message.get(h)},
        provider_labels=tuple(filter(None, str(message.get("X-Gmail-Labels", "")).split(","))),
    )


def read_mbox(path: Path, limit: int) -> Iterator[SourceRecord]:
    for index, message in enumerate(mailbox.mbox(str(path))):
        if index >= limit:
            return
        yield to_source(message, index)


def build_assertion(
    source: SourceRecord, number: int, kind: str, quote: str, fields: dict[str, str]
) -> GoldAssertion:
    """Validate one label. The quote must be literally present, exactly as in production."""
    if not quote_in_source(quote, source.text):
        raise ValueError("that quote is not in the message; copy it exactly")
    due = fields.get("due")
    return GoldAssertion(
        id=f"{source.id}_a{number}",
        source_id=source.id,
        kind=CandidateKind(kind),
        subject=fields.get("subject", ""),
        predicate=fields.get("predicate", ""),
        value=fields.get("value", ""),
        evidence_quote=quote,
        origin=Origin(fields.get("origin", Origin.SOURCE_EXPLICIT)),
        commitment_type=CommitmentType(fields["type"]) if fields.get("type") else None,
        direction=Direction(fields["direction"]) if fields.get("direction") else None,
        due=date.fromisoformat(due) if due else None,
    )


def label(sources: list[SourceRecord], ask: Callable[[str], str] = input) -> Gold:
    categories: dict[str, SourceCategory] = {}
    assertions: list[GoldAssertion] = []
    for position, source in enumerate(sources, start=1):
        print(f"\n{'=' * 80}\n[{position}/{len(sources)}] {source.sender} | {source.subject}\n")
        print(source.body[:3000])
        answer = ask("\n(s)ignal, (a)utomated signal, (n)oise, (q)uit > ").strip().lower()
        if answer == "q":
            break
        categories[source.id] = {
            "s": SourceCategory.SIGNAL,
            "a": SourceCategory.AUTOMATED_SIGNAL,
        }.get(answer, SourceCategory.NOISE)
        while categories[source.id] is not SourceCategory.NOISE:
            kind = ask("add: commitment / decision / event / thing / person, or Enter > ").strip()
            if not kind:
                break
            fields = {"value": ask("  what (short) > ").strip()}
            if kind == CandidateKind.COMMITMENT:
                fields["type"] = ask("  promise / deadline > ").strip()
                fields["direction"] = ask("  by_user / to_user / between_others > ").strip()
                fields["due"] = ask("  due YYYY-MM-DD or Enter > ").strip()
            try:
                quote = ask("  exact quote > ")
                assertions.append(build_assertion(source, len(assertions) + 1, kind, quote, fields))
            except ValueError as problem:
                print(f"  not saved: {problem}")
    user = Party(name=None, address=ask("your email address > ").strip())
    return Gold(
        as_of=datetime.now(UTC).date(),
        user=user,
        categories=categories,
        assertions=tuple(assertions),
        relations=(),
        people=(),
        temporal_queries=(),
        injected_spans=(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mbox", type=Path)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    sources = list(read_mbox(args.mbox, args.limit))
    gold = label(sources)
    labelled = [s for s in sources if s.id in gold.categories]

    GOLDEN_DIR.mkdir(exist_ok=True)
    (GOLDEN_DIR / "sources.json").write_text(
        json.dumps([s.model_dump(mode="json") for s in labelled], indent=2), encoding="utf-8"
    )
    (GOLDEN_DIR / "gold.json").write_text(
        json.dumps(gold.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    print(f"\nsaved {len(labelled)} labelled messages to {GOLDEN_DIR} (gitignored)")


if __name__ == "__main__":
    main()
