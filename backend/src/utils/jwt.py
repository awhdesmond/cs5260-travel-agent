import os
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


ENV_JWT_SECRET= "JWT_SECRET"

JWT_ALGORITHM = "HS256"
JWT_AUDIENCE = "authenticated"

JWT_ERR_MSG_MISSING = "Bearer token required"
JWT_ERR_MSG_EXPIRED = "Token has expired"
JWT_ERR_MSG_INVALID = "Invalid token"


http_bearer = HTTPBearer(auto_error=False)


async def get_current_user(creds: HTTPAuthorizationCredentials = Depends(http_bearer)) -> dict:
    """
    Extract and verify JWT. Returns decoded payload with sub, email, aud, exp.

    Raises HTTPException 401 if token is missing, invalid, or expired.
    """
    jwt_secret = os.environ.get(ENV_JWT_SECRET, "")
    jwt_headers = {"WWW-Authenticate": "Bearer"}

    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers=jwt_headers,
            detail=JWT_ERR_MSG_MISSING,
        )

    try:
        payload = jwt.decode(
            creds.credentials,
            jwt_secret,
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
        )
        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers=jwt_headers,
            detail=JWT_ERR_MSG_EXPIRED,
        )

    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers=jwt_headers,
            detail=JWT_ERR_MSG_INVALID,
        )
