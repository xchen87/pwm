"""Turning a raw message into the text its author actually wrote."""

import re

from pwm.sources import SourceRecord

_REPLY_HEADER = re.compile(r"^On .{5,200} wrote:\s*$")
_FORWARD_MARKER = re.compile(r"^-{2,}\s*(Original|Forwarded) [Mm]essage\s*-{2,}")
# Text a recipient would never see is a classic carrier for injected instructions.
_HIDDEN_ELEMENT = re.compile(
    r"<(\w+)\b[^>]*style\s*=\s*[\"'][^\"']*(display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)"
    r"[^\"']*[\"'][^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_SUSPICIOUS = re.compile(
    r"ignore (all )?(previous|prior) instructions|\bAI assistant\b|\bany AI\b|"
    r"automated system processing|</?system>|\bassistant:",
    re.IGNORECASE,
)


def strip_hidden_markup(body: str) -> str:
    return _HIDDEN_ELEMENT.sub("", body)


def strip_quoted_replies(body: str) -> str:
    """Drop text quoted from earlier messages: it belongs to its original author."""
    kept: list[str] = []
    for line in body.splitlines():
        if _FORWARD_MARKER.match(line):
            break
        if line.lstrip().startswith(">") or _REPLY_HEADER.match(line.strip()):
            continue
        kept.append(line)
    return "\n".join(kept)


def visible_body(source: SourceRecord) -> str:
    return strip_quoted_replies(strip_hidden_markup(source.body)).strip()


def visible_text(source: SourceRecord) -> str:
    # The blank line keeps the subject a paragraph of its own, so it never fuses with
    # the first sentence of the body.
    return f"{source.subject}\n\n{visible_body(source)}".strip()


def looks_like_injection(text: str) -> bool:
    return bool(_SUSPICIOUS.search(text))


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def similarity(a: str, b: str) -> float:
    """Jaccard similarity on word tokens."""
    left, right = tokens(a), tokens(b)
    return len(left & right) / len(left | right) if left and right else 0.0
