import base64
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


NONCE_SIZE = 12
TAG_SIZE = 16


def _encryption_key() -> bytes:
    configured = os.environ.get("APP_ENCRYPTION_KEY")
    if not configured:
        raise RuntimeError("Configura APP_ENCRYPTION_KEY como una clave Base64 de 32 bytes.")
    try:
        key = base64.b64decode(configured, validate=True)
    except ValueError as exc:
        raise RuntimeError("APP_ENCRYPTION_KEY no contiene Base64 válido.") from exc
    if len(key) != 32:
        raise RuntimeError("APP_ENCRYPTION_KEY debe decodificar exactamente a 32 bytes para AES-256.")
    return key


def encrypt_bytes(plaintext: bytes, associated_data: bytes = b"") -> bytes:
    nonce = os.urandom(NONCE_SIZE)
    encryptor = Cipher(algorithms.AES(_encryption_key()), modes.GCM(nonce)).encryptor()
    if associated_data:
        encryptor.authenticate_additional_data(associated_data)
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    return nonce + encryptor.tag + ciphertext


def decrypt_bytes(payload: bytes, associated_data: bytes = b"") -> bytes:
    if len(payload) < NONCE_SIZE + TAG_SIZE:
        raise ValueError("El archivo cifrado está truncado o no tiene formato AES-GCM.")
    nonce = payload[:NONCE_SIZE]
    tag = payload[NONCE_SIZE:NONCE_SIZE + TAG_SIZE]
    ciphertext = payload[NONCE_SIZE + TAG_SIZE:]
    decryptor = Cipher(algorithms.AES(_encryption_key()), modes.GCM(nonce, tag)).decryptor()
    if associated_data:
        decryptor.authenticate_additional_data(associated_data)
    return decryptor.update(ciphertext) + decryptor.finalize()
