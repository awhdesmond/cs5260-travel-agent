import os
import bcrypt
import jwt

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.repository import get_db_pool

router = APIRouter()

JWT_SECRET = os.environ.get("JWT_SECRET", "")
ALGORITHM = "HS256"

_ADMIN_UUID = "00000000-0000-4000-a000-000000000001"  # Fixed; matches V4 migration


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str


def _issue_token(user_id: str, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",
        "exp": datetime.now(tz=timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest) -> AuthResponse:
    """
    Authenticate an existing user. Returns JWT on success.
    """
    pool = get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, password_hash FROM users WHERE email = %s",
                (body.email,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    db_user_id, db_email, stored_hash = row

    if not bcrypt.checkpw(body.password.encode("utf-8"), stored_hash.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return AuthResponse(
        token=_issue_token(str(db_user_id), db_email),
        user_id=str(db_user_id),
        email=db_email,
    )
