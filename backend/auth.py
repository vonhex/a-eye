"""HMAC-signed cookie sessions for A-Eye authentication.

No external dependencies — uses Python stdlib only.
Signing key is derived from the password (salted PBKDF2), so changing the
password automatically invalidates all existing sessions.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import lru_cache
from pathlib import Path

SESSION_TTL = 30 * 24 * 3600  # 30 days in seconds
COOKIE_NAME = "aeye_session"


_KDF_ITERATIONS = 600_000


def _server_secret() -> bytes:
    """Random per-install secret kept in the data dir (created on first use, mode 0600).

    Used as the PBKDF2 salt so a stolen session cookie cannot be brute-forced
    offline back to the password without also having this file.
    """
    from backend.config import get_settings

    path = Path(get_settings().data_dir) / ".session_secret"
    try:
        secret = path.read_bytes()
        if len(secret) >= 32:
            return secret
    except OSError:
        pass
    secret = secrets.token_bytes(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(secret)
    return secret


@lru_cache(maxsize=8)
def _derive_key(password: str) -> bytes:
    """Derive the cookie signing key from the password with salted PBKDF2-SHA256.

    Cached: the derivation is deliberately slow and runs once per password.
    """
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), _server_secret(), _KDF_ITERATIONS)


def create_session(username: str, password: str) -> str:
    """Create a signed session cookie value.

    Returns a base64-encoded string: payload.signature
    """
    key = _derive_key(password)
    payload = json.dumps({
        "user": username,
        "exp": int(time.time()) + SESSION_TTL,
    }).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii")
    sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_session(cookie_value: str, username: str, password: str) -> bool:
    """Verify a signed session cookie.

    Returns True only if the signature is valid, the user matches,
    and the session hasn't expired.
    """
    try:
        parts = cookie_value.split(".", 1)
        if len(parts) != 2:
            return False
        payload_b64, sig = parts

        key = _derive_key(password)
        expected_sig = hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected_sig):
            return False

        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("user") != username:
            return False
        if payload.get("exp", 0) < time.time():
            return False

        return True
    except Exception:
        return False
