import hashlib
import hmac
import logging
import time

import config

log = logging.getLogger("auth")


def issue(session_id: str, ttl_sec: int | None = None) -> str:
    """Mint a short-lived token. In production Laravel issues these with the same secret;
    this helper exists so localhost and the test suite do not need Laravel running."""
    exp = int(time.time()) + (ttl_sec if ttl_sec is not None else config.TOKEN_TTL_SEC)
    sig = _sign(session_id, exp)
    return f"{exp}.{sig}"


def verify(session_id: str, token: str) -> tuple[bool, str]:
    if not config.AUTH_SECRET:
        return True, "auth-disabled"
    if not token or "." not in token:
        return False, "malformed"

    exp_raw, _, sig = token.partition(".")
    try:
        exp = int(exp_raw)
    except ValueError:
        return False, "malformed"

    if exp < int(time.time()):
        return False, "expired"
    if not hmac.compare_digest(sig, _sign(session_id, exp)):
        return False, "bad-signature"
    return True, "ok"


def _sign(session_id: str, exp: int) -> str:
    return hmac.new(
        config.AUTH_SECRET.encode(),
        f"{session_id}:{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()
