"""WI-E1 (audit v0.3.2): auth.verify()/issue() had zero unit tests despite gating every
/suggest, /stream, and /portfolios call."""
import config

import auth


def test_verify_with_empty_auth_secret_is_disabled(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "")
    assert auth.verify("session-a", "anything") == (True, "auth-disabled")


def test_verify_rejects_token_without_dot(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    assert auth.verify("session-a", "no-dot-here") == (False, "malformed")


def test_verify_rejects_empty_token(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    assert auth.verify("session-a", "") == (False, "malformed")


def test_verify_rejects_expired_token(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    token = auth.issue("session-a", ttl_sec=-10)  # already expired
    assert auth.verify("session-a", token) == (False, "expired")


def test_verify_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    exp_raw = auth.issue("session-a").split(".")[0]
    tampered = f"{exp_raw}.notarealsignature"
    assert auth.verify("session-a", tampered) == (False, "bad-signature")


def test_verify_rejects_token_signed_for_different_session(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    token = auth.issue("session-a")
    assert auth.verify("session-b", token) == (False, "bad-signature")


def test_issue_then_verify_round_trip_with_custom_ttl(monkeypatch):
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    token = auth.issue("session-a", ttl_sec=60)
    assert auth.verify("session-a", token) == (True, "ok")


def test_issue_with_zero_ttl_is_immediately_expired(monkeypatch):
    # auth.py truncates time.time() to whole seconds - issue() and verify() called back to
    # back can land in the SAME integer second, in which case exp == now and the code's
    # strict `<` comparison would NOT flag it as expired yet. Freezing time removes that
    # timing race so the ttl_sec=0 boundary is tested deterministically, one second later.
    monkeypatch.setattr(config, "AUTH_SECRET", "test-secret")
    frozen = [1_800_000_000]
    monkeypatch.setattr(auth.time, "time", lambda: frozen[0])
    token = auth.issue("session-a", ttl_sec=0)
    frozen[0] += 1  # advance the clock by 1s - a ttl_sec=0 token must be dead by then
    assert auth.verify("session-a", token) == (False, "expired")
