import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import jwt


@dataclass(frozen=True)
class JwtSettings:
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15


def get_jwt_settings() -> JwtSettings:
    secret_key = os.getenv("JWT_SECRET_KEY")
    if not secret_key:
        raise RuntimeError("JWT_SECRET_KEY is not set")
    expire_minutes = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    return JwtSettings(secret_key=secret_key, access_token_expire_minutes=expire_minutes)


def create_access_token(subject: str, user_id: int) -> str:
    settings = get_jwt_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "uid": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
