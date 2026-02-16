import hashlib

from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    password: str
    email: EmailStr
    full_name: str | None = None


class UserPublic(BaseModel):
    username: str
    email: EmailStr
    full_name: str | None = None


class UserInDB(BaseModel):
    id: int
    username: str
    password_hash: str
    email: EmailStr
    full_name: str | None = None


_PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_password(raw_password: str) -> str:
    password_bytes = raw_password.encode("utf-8")
    if len(password_bytes) <= 72:
        return raw_password
    return hashlib.sha256(password_bytes).hexdigest()


def hash_password(raw_password: str) -> str:
    normalized = _normalize_password(raw_password)
    return _PWD_CONTEXT.hash(normalized)


def verify_password(raw_password: str, password_hash: str) -> bool:
    normalized = _normalize_password(raw_password)
    return _PWD_CONTEXT.verify(normalized, password_hash)