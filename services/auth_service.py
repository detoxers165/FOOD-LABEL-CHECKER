import hmac
import hashlib
import secrets
import jwt
from datetime import datetime
from schemas.auth import UserResponse

def generate_otp() -> str:
    return f"{secrets.randbelow(1000000):06d}"

def hash_otp(otp: str, secret: str) -> str:
    h = hmac.new(secret.encode('utf-8'), otp.encode('utf-8'), hashlib.sha256)
    return h.hexdigest()

def verify_otp(otp: str, otp_hash: str, secret: str) -> bool:
    expected_hash = hash_otp(otp, secret)
    return hmac.compare_digest(expected_hash, otp_hash)

def create_jwt(user_id: str, jti: str, exp: datetime, secret: str, algorithm: str) -> str:
    payload = {
        "sub": str(user_id),
        "jti": jti,
        "exp": exp
    }
    return jwt.encode(payload, secret, algorithm=algorithm)

def decode_jwt(token: str, secret: str, algorithm: str) -> dict:
    return jwt.decode(token, secret, algorithms=[algorithm])

def _format_dt(dt):
    if not dt or not isinstance(dt, datetime):
        return dt
    iso = dt.isoformat()
    if iso.endswith("+00:00"):
        return iso[:-6] + "Z"
    if not iso.endswith("Z"):
        return iso + "Z"
    return iso

def serialize_user(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        email_verified=user.get("email_verified", False),
        is_active=user.get("is_active", True),
        display_name=user.get("display_name"),
        created_at=_format_dt(user.get("created_at")),
        updated_at=_format_dt(user.get("updated_at")),
        last_login_at=_format_dt(user.get("last_login_at"))
    )
