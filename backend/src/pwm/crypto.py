"""Application-level encryption for the two things that must never sit in the database in
the clear: Google refresh tokens and message bodies.

AES-256-GCM with a random nonce per value, and the purpose bound in as associated data
(a token cannot be replayed as a body). The key comes from configuration, never from the
database, so a database dump alone reveals neither.

Format: `enc:v2:<key id>:<base64 nonce+ciphertext>`. The key id is the first 8 hex digits
of the key's SHA-256, so a value says which key sealed it. New values use PWM_DATA_KEY;
values sealed under a key listed in PWM_DATA_KEYS_OLD stay readable, which is what makes
rotation possible: add the old key to that list, set the new one, run `pwm.cli reseal`.

What this does not cover, on purpose: evidence quotes and extracted values are stored in
the clear, because they are queried and shown constantly. Encrypting bodies keeps the
bulk of someone's mail out of a database dump; it does not make a dump harmless.
"""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pwm.config import get_settings

PREFIX = "enc:"


class DataKeyMissing(RuntimeError):
    """PWM_DATA_KEY is not set, so nothing secret can be stored or read."""


class Undecryptable(ValueError):
    """The value was sealed with a key this server does not have, or has been altered."""


def _decode(encoded: str) -> bytes:
    key = base64.b64decode(encoded)
    if len(key) != 32:
        raise DataKeyMissing("a data key must be base64 of exactly 32 bytes")
    return key


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


def _current() -> bytes:
    encoded = get_settings().data_key
    if not encoded:
        raise DataKeyMissing("PWM_DATA_KEY is required to store tokens or message bodies")
    return _decode(encoded)


def _keys() -> dict[str, bytes]:
    settings = get_settings()
    keys = [
        _decode(k)
        for k in ([settings.data_key] if settings.data_key else []) + settings.data_keys_old
    ]
    if not keys:
        raise DataKeyMissing("PWM_DATA_KEY is required to read tokens or message bodies")
    return {key_id(k): k for k in keys}


def encrypt(plaintext: str, purpose: str) -> str:
    key, nonce = _current(), os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), purpose.encode())
    return f"enc:v2:{key_id(key)}:{base64.b64encode(nonce + sealed).decode()}"


def decrypt(value: str, purpose: str) -> str:
    parts = value.split(":", 3)
    if len(parts) != 4 or parts[0] != "enc" or parts[1] != "v2":
        raise Undecryptable("not an encrypted value")
    key = _keys().get(parts[2])
    if key is None:
        raise Undecryptable("sealed with a key this server does not have")
    raw = base64.b64decode(parts[3])
    try:
        return AESGCM(key).decrypt(raw[:12], raw[12:], purpose.encode()).decode("utf-8")
    except InvalidTag:
        raise Undecryptable("wrong purpose, or the value was modified") from None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def sealed_with_current_key(value: str) -> bool:
    return value.startswith(f"enc:v2:{key_id(_current())}:")
