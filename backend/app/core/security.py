from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from itsdangerous import URLSafeSerializer, BadSignature

_ph = PasswordHasher()
_SALT = "session"


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError):
        return False


def sign_session(user_id: str, secret: str) -> str:
    return URLSafeSerializer(secret, salt=_SALT).dumps(user_id)


def read_session(token: str, secret: str) -> str | None:
    try:
        return URLSafeSerializer(secret, salt=_SALT).loads(token)
    except BadSignature:
        return None
