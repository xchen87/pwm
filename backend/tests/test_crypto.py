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
    tampered = sealed[:-6] + ("AAAAAA" if not sealed.endswith("AAAAAA") else "BBBBBB")
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


def test_a_value_names_the_key_that_sealed_it_and_old_keys_still_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    old_key = os.environ["PWM_DATA_KEY"]
    sealed = crypto.encrypt("secret", "token")
    assert sealed.split(":")[2] == crypto.key_id(base64.b64decode(old_key))
    monkeypatch.setenv("PWM_DATA_KEY", base64.b64encode(os.urandom(32)).decode())
    monkeypatch.setenv("PWM_DATA_KEYS_OLD", json.dumps([old_key]))
    assert crypto.decrypt(sealed, "token") == "secret"
    assert not crypto.sealed_with_current_key(sealed)


def test_the_first_format_is_still_read_and_a_mistyped_old_key_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key = base64.b64decode(os.environ["PWM_DATA_KEY"])
    nonce = os.urandom(12)
    legacy = (
        "enc:v1:"
        + base64.b64encode(nonce + AESGCM(key).encrypt(nonce, b"old body", b"source-body")).decode()
    )
    assert crypto.decrypt(legacy, "source-body") == "old body"
    assert not crypto.sealed_with_current_key(legacy)

    monkeypatch.setenv(
        "PWM_DATA_KEYS_OLD", json.dumps(["not base64 !!", base64.b64encode(b"short").decode()])
    )
    assert crypto.decrypt(crypto.encrypt("x", "token"), "token") == "x"
    assert not issubclass(crypto.Undecryptable, ValueError)  # so no generic handler swallows it
