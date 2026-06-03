from app.core.security import (
    hash_password,
    verify_password,
    sign_session,
    read_session,
)

SECRET = "test-secret"


def test_hash_and_verify_roundtrip():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert verify_password("hunter2", h) is True
    assert verify_password("wrong", h) is False


def test_session_sign_and_read_roundtrip():
    token = sign_session("user-id-123", SECRET)
    assert read_session(token, SECRET) == "user-id-123"


def test_read_session_rejects_tampered_token():
    token = sign_session("user-id-123", SECRET)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert read_session(tampered, SECRET) is None


def test_read_session_rejects_wrong_secret():
    token = sign_session("user-id-123", SECRET)
    assert read_session(token, "other-secret") is None
