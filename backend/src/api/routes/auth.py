import os
import bcrypt
import jwt

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.db.repository import get_db_pool
from src.utils.jwt import JWT_ALGORITHM, JWT_AUDIENCE, ENV_JWT_SECRET


router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user_id: str
    email: str


ExceptionInvalidCredentials = HTTPException(status_code=401, detail="Invalid credentials")

def _issue_token(user_id: str, email: str) -> str:
    jwt_secret = os.environ.get(ENV_JWT_SECRET, "")

    expiry = datetime.now(tz=timezone.utc) + timedelta(hours=24)
    payload = {
        "sub": user_id,
        "email": email,
        "aud": JWT_AUDIENCE,
        "exp": expiry,
    }
    return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest) -> LoginResponse:
    """
    Authenticate an existing user. Returns JWT on success.
    """
    pool = get_db_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    with pool.connection() as conn:
        with conn.cursor() as cur:
            q = "SELECT id, email, password_hash FROM users WHERE email = %s"
            cur.execute(q, (body.email,))
            row = cur.fetchone()

    if row is None:
        raise ExceptionInvalidCredentials

    db_user_id, db_email, stored_hash = row

    if not bcrypt.checkpw(body.password.encode("utf-8"), stored_hash.encode("utf-8")):
        raise ExceptionInvalidCredentials

    return LoginResponse(
        token=_issue_token(str(db_user_id), db_email),
        user_id=str(db_user_id),
        email=db_email,
    )
