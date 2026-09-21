"""Turning a raw message into the text its author actually wrote."""

import re

from pwm.sources import SourceRecord

_REPLY_HEADER = re.compile(r"^On .{5,200} wrote:\s*$")
_FORWARD_MARKER = re.compile(r"^-{2,}\s*(Original|Forwarded) [Mm]essage\s*-{2,}")
# Text a recipient would never see is a classic carrier for injected instructions.
_OPEN_TAG = re.compile(r"<([a-zA-Z][\w-]*)\b([^>]*)>")
_HIDING_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(\.0+)?\s*(;|$|[\"'])|"
    r"font-size\s*:\s*[0-2](\.\d+)?\s*(px|pt|em|%)?\s*(;|$|[\"'])|"
    r"(max-)?(height|width)\s*:\s*0\s*(px)?\s*(;|$|[\"'])|"
    r"(?<![-\w])color\s*:\s*(#fff(fff)?\b|white\b|transparent\b|rgba\([^)]*,\s*0\s*\))",
    re.IGNORECASE,
)
_HIDDEN_ATTRIBUTE = re.compile(
    r"(^|\s)(hidden|aria-hidden\s*=\s*[\"']?true)(\s|=|$|[\"'])", re.IGNORECASE
)
_SUSPICIOUS = re.compile(
    r"ignore (all )?(previous|prior) instructions|\bAI assistant\b|\bany AI\b|"
    r"automated system processing|</?system>|\bassistant:",
    re.IGNORECASE,
)


def _hides(attributes: str) -> bool:
    return bool(_HIDING_STYLE.search(attributes) or _HIDDEN_ATTRIBUTE.search(attributes))


def _end_of_element(body: str, name: str, start: int) -> int:
    """Index just past the tag that closes the element opened before `start`, counting
    nested elements of the same name. An unclosed element hides everything after it."""
    tag = re.compile(rf"<(/?){re.escape(name)}\b[^>]*>", re.IGNORECASE)
    depth, position = 1, start
    while found := tag.search(body, position):
        depth += -1 if found[1] else 1
        position = found.end()
        if depth == 0:
            return position
    return len(body)


def strip_hidden_markup(body: str) -> str:
    """Remove elements styled so that a human reader would not see them, with their contents.

    Deliberately conservative about what it touches: everything outside a hidden element
    is left byte-for-byte as it was, so evidence quotes still match the source.
    """
    kept: list[str] = []
    position = 0
    while found := _OPEN_TAG.search(body, position):
        if not _hides(found[2]):
            kept.append(body[position : found.end()])
            position = found.end()
            continue
        kept.append(body[position : found.start()])
        position = _end_of_element(body, found[1], found.end())
    kept.append(body[position:])
    return "".join(kept)


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
