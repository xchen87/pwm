from email.message import EmailMessage

import pytest

from pwm_eval.gold import SourceCategory
from pwm_eval.golden import build_assertion, label, to_source


def message() -> EmailMessage:
    mail = EmailMessage()
    mail["From"] = "Casey Doe <casey@example.com>"
    mail["To"] = "me@example.com"
    mail["Subject"] = "Invoice"
    mail["Date"] = "Mon, 07 Sep 2026 09:12:00 +0000"
    mail["List-Unsubscribe"] = "<mailto:u@example.com>"
    mail.set_content("I'll send the invoice by Friday.\n")
    return mail


def test_mbox_message_becomes_a_source_record() -> None:
    source = to_source(message(), 3)
    assert source.id == "golden_00003"
    assert source.sender and source.sender.address == "casey@example.com"
    assert source.headers == {"List-Unsubscribe": "<mailto:u@example.com>"}
    assert "invoice by Friday" in source.body


def test_label_with_a_paraphrased_quote_is_rejected() -> None:
    source = to_source(message(), 0)
    with pytest.raises(ValueError, match="not in the message"):
        build_assertion(source, 1, "commitment", "I will send the invoice on Friday", {})


def test_labelling_session_produces_gold() -> None:
    answers = iter(
        [
            "s",
            "commitment",
            "send the invoice",
            "promise",
            "to_user",
            "2026-09-11",
            "I'll send the invoice by Friday.",
            "",
            "me@example.com",
        ]
    )
    gold = label([to_source(message(), 0)], ask=lambda _prompt: next(answers))
    assert gold.categories == {"golden_00000": SourceCategory.SIGNAL}
    assert len(gold.assertions) == 1
    assert gold.assertions[0].due is not None
