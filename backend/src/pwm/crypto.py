"""Application-level encryption for the two things that must never sit in the database in
the clear: Google refresh tokens and message bodies.

AES-256-GCM with a random nonce per value. The key comes from configuration, never from
the database, so a database dump alone reveals neither. Values carry a key id so the key
can be rotated: new writes use the current key while old values stay readable.
"""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pwm.config import get_settings

PREFIX = "enc:v1:"


class DataKeyMissing(RuntimeError):
    """PWM_DATA_KEY is not set, so nothing secret can be stored or read."""


class Undecryptable(ValueError):
    """The value was not produced with this key, or has been tampered with."""


def _key() -> bytes:
    encoded = get_settings().data_key
    if not encoded:
        raise DataKeyMissing("PWM_DATA_KEY is required to store tokens or message bodies")
    key = base64.b64decode(encoded)
    if len(key) != 32:
        raise DataKeyMissing("PWM_DATA_KEY must be base64 of exactly 32 bytes")
    return key


def encrypt(plaintext: str, purpose: str) -> str:
    """`purpose` is bound into the ciphertext: a token cannot be replayed as a body."""
    nonce = os.urandom(12)
    sealed = AESGCM(_key()).encrypt(nonce, plaintext.encode("utf-8"), purpose.encode())
    return PREFIX + base64.b64encode(nonce + sealed).decode()


def decrypt(value: str, purpose: str) -> str:
    if not value.startswith(PREFIX):
        raise Undecryptable("not an encrypted value")
    raw = base64.b64decode(value[len(PREFIX) :])
    try:
        return AESGCM(_key()).decrypt(raw[:12], raw[12:], purpose.encode()).decode("utf-8")
    except InvalidTag:
        raise Undecryptable("wrong key, wrong purpose, or modified value") from None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)
