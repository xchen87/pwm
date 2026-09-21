"""Mechanical evidence-quote verification.

A candidate whose quote is not literally present in its source is dropped. This is
the cheapest guard against hallucinated facts.
"""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def normalize(text: str) -> str:
    """Normalize for comparison: unicode form, curly quotes, and runs of whitespace.

    Email bodies are re-wrapped in transit, so whitespace is not significant.
    Wording, punctuation, and case are.
    """
    text = unicodedata.normalize("NFKC", text).translate(_QUOTE_MARKS)
    return _WHITESPACE.sub(" ", text).strip()


def quote_in_source(quote: str, source_text: str) -> bool:
    normalized = normalize(quote)
    return bool(normalized) and normalized in normalize(source_text)
