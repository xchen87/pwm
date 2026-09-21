import base64
import os

import pytest

from pwm import crypto


@pytest.fixture(autouse=True)
def key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWM_DATA_KEY", base64.b64encode(os.urandom(32)).decode())


def test_round_trip_and_a_fresh_nonce_every_time() -> None:
    first, second = (
        crypto.encrypt("1//refresh-token", "token"),
        crypto.encrypt("1//refresh-token", "token"),
    )
    assert first != second and "refresh-token" not in first
    assert crypto.decrypt(first, "token") == crypto.decrypt(second, "token") == "1//refresh-token"


def test_a_value_cannot_be_used_for_another_purpose_or_altered() -> None:
    sealed = crypto.encrypt("secret body", "body")
    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(sealed, "token")
    tampered = sealed[:-4] + ("AAAA" if not sealed.endswith("AAAA") else "BBBB")
    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(tampered, "body")


def test_another_key_cannot_read_it(monkeypatch: pytest.MonkeyPatch) -> None:
    sealed = crypto.encrypt("secret", "token")
    monkeypatch.setenv("PWM_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    with pytest.raises(crypto.Undecryptable):
        crypto.decrypt(sealed, "token")


def test_without_a_key_nothing_is_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PWM_DATA_KEY")
    with pytest.raises(crypto.DataKeyMissing):
        crypto.encrypt("secret", "token")
    monkeypatch.setenv("PWM_DATA_KEY", base64.b64encode(b"too short").decode())
    with pytest.raises(crypto.DataKeyMissing):
        crypto.encrypt("secret", "token")
