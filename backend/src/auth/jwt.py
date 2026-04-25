import os
import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "authenticated"

# auto_error=False enables custom error messages
http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(http_bearer)) -> dict:
    """
    Extract and verify JWT. Returns decoded payload with sub, email, aud, exp.
    Raises HTTPException 401 if token is missing, invalid, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_secret = os.environ.get("JWT_SECRET", "")

    try:
        payload = jwt.decode(
            credentials.credentials,
            jwt_secret,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
