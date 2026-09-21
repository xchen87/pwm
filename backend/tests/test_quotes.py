from pwm.extraction.quotes import quote_in_source

SOURCE = "Re: Q3\nHi Tom,\n\nI’ll send you the Q3 numbers\nby Friday.\n"


def test_exact_quote_is_found() -> None:
    assert quote_in_source("send you the Q3 numbers", SOURCE)


def test_rewrapped_lines_and_curly_quotes_still_match() -> None:
    assert quote_in_source("I'll send you the Q3 numbers by Friday.", SOURCE)


def test_paraphrase_is_rejected() -> None:
    assert not quote_in_source("I will send the Q3 numbers on Friday", SOURCE)


def test_case_change_is_rejected() -> None:
    assert not quote_in_source("i'll send you the q3 numbers", SOURCE)


def test_empty_quote_is_rejected() -> None:
    assert not quote_in_source("   ", SOURCE)
