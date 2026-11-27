import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from fastapi import Request


ROLES = {"Carga", "Revisor", "Aprobador", "Solo lectura"}
COOKIE_NAME = "propuesta_session"
SESSION_TTL_SECONDS = 8 * 60 * 60


def _users() -> dict:
    raw = os.environ.get("APP_USERS_JSON", "")
    if not raw:
        return {}
    users = json.loads(raw)
    if not isinstance(users, dict):
        raise RuntimeError("APP_USERS_JSON debe ser un objeto JSON indexado por usuario.")
    for username, entry in users.items():
        if not isinstance(entry, dict) or not entry.get("password") or entry.get("role") not in ROLES:
            raise RuntimeError(f"Cuenta inválida en APP_USERS_JSON: {username!r}.")
    return users


def authenticate(username: str, password: str) -> Optional[dict]:
    entry = _users().get(username)
    if entry and hmac.compare_digest(str(entry["password"]), password):
        return {"username": username, "role": entry["role"]}
    return None


def _secret() -> bytes:
    secret = os.environ.get("APP_SESSION_SECRET")
    if not secret:
        raise RuntimeError("Configura APP_SESSION_SECRET antes de iniciar la aplicación.")
    return secret.encode("utf-8")


def create_session(user: dict) -> str:
    payload = {
        "username": user["username"],
        "role": user["role"],
        "exp": int(time.time()) + SESSION_TTL_SECONDS,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def current_user(request: Request) -> Optional[dict]:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(_secret(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["exp"] < time.time() or payload["role"] not in ROLES:
            return None
        return {"username": payload["username"], "role": payload["role"]}
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
