import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from app.crypto import decrypt_bytes, encrypt_bytes


def test_aes_gcm_round_trip_and_authenticates_associated_data(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode("ascii"))
    aad = b"project-file-123"
    encrypted = encrypt_bytes(b"confidential proposal", aad)

    assert decrypt_bytes(encrypted, aad) == b"confidential proposal"
    with pytest.raises(InvalidTag):
        decrypt_bytes(encrypted, b"wrong-file-id")


def test_aes_gcm_rejects_non_256_bit_key(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", base64.b64encode(os.urandom(16)).decode("ascii"))
    with pytest.raises(RuntimeError, match="32 bytes"):
        encrypt_bytes(b"content")
