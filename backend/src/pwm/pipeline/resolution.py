"""Stage 6: who is who. Code first; a model is only for cases these rules cannot settle.

An address becomes a person only when there is a direct relationship with the user:
they wrote to the user personally, the user wrote to them, or they share a calendar
event. List traffic and bulk senders do not create people.

Two addresses are linked only when the display names are compatible AND the newer
address identifies itself with the known person's surname in the message text. A
display name alone never merges identities (threat model T2), and nothing is ever
merged into the user. Links are recorded as inferred so the user can split them.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from pwm.pipeline.prefilter import Route, is_bulk, is_from_user, route
from pwm.pipeline.text import tokens, visible_text
from pwm.sources import Party, SourceKind, SourceRecord


class ResolvedIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    addresses: tuple[str, ...]
    source_ids: tuple[str, ...]
    # Addresses joined by inference rather than by exact match; the user can split these.
    inferred_links: tuple[str, ...] = ()


def is_user_lookalike(party: Party, user: Party) -> bool:
    same_name = bool(party.name and user.name and party.name.lower() == user.name.lower())
    return same_name and party.address.lower() != user.address.lower()


def _names_compatible(short: str, full: str) -> bool:
    a, b = short.replace(".", "").lower().split(), full.lower().split()
    if len(a) < 1 or len(b) < 2 or a[0] != b[0]:
        return False
    return len(a) == 1 or b[-1].startswith(a[-1]) or a[-1].startswith(b[-1])


def resolve_people(sources: Sequence[SourceRecord], user: Party) -> tuple[ResolvedIdentity, ...]:
    names: dict[str, str] = {}
    seen_in: dict[str, list[str]] = {}
    texts: dict[str, list[str]] = {}

    def note(party: Party, source: SourceRecord) -> None:
        address = party.address.lower()
        if address == user.address.lower() or is_user_lookalike(party, user):
            return
        if len(party.name or "") > len(names.get(address, "")):
            names[address] = party.name or ""
        names.setdefault(address, party.name or address)
        seen_in.setdefault(address, []).append(source.id)

    for source in sources:
        if source.kind is SourceKind.CALENDAR_EVENT or is_from_user(source, user):
            if source.kind is not SourceKind.USER_CAPTURE:
                for party in source.recipients:
                    note(party, source)
            continue
        addressed_to_user = any(
            p.address.lower() == user.address.lower() for p in source.recipients
        )
        direct = addressed_to_user and len(source.recipients) <= 5 and not is_bulk(source)
        if source.sender and direct and route(source, user) is not Route.SKIP:
            note(source.sender, source)
            texts.setdefault(source.sender.address.lower(), []).append(visible_text(source))

    clusters: dict[str, list[str]] = {address: [address] for address in names}
    inferred: dict[str, list[str]] = {}
    by_name_length = sorted(names, key=lambda a: len(names[a]), reverse=True)
    for address in by_name_length:
        if address not in clusters:
            continue
        for other in by_name_length:
            if other == address or other not in clusters or address not in clusters:
                continue
            full, short = names[address], names[other]
            surname = full.lower().split()[-1] if full.split() else ""
            self_identified = any(surname in tokens(text) for text in texts.get(other, []))
            if surname and _names_compatible(short, full) and self_identified:
                clusters[address].extend(clusters.pop(other))
                inferred.setdefault(address, []).append(other)

    return tuple(
        ResolvedIdentity(
            name=names[primary],
            addresses=tuple(members),
            source_ids=tuple(sid for member in members for sid in seen_in[member]),
            inferred_links=tuple(inferred.get(primary, ())),
        )
        for primary, members in clusters.items()
    )
