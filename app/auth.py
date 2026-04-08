# backend/app/auth.py
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("SENTRIBID_SECRET", "dev-secret-change-me")
ALGORITHM = os.getenv("SENTRIBID_JWT_ALG", "HS256")
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "24"))

JWT_ISSUER = os.getenv("SENTRIBID_JWT_ISSUER", "")
JWT_AUDIENCE = os.getenv("SENTRIBID_JWT_AUDIENCE", "")

bearer_required = HTTPBearer(auto_error=True)
bearer_optional = HTTPBearer(auto_error=False)


def _jwt_decode(token: str) -> dict:
    try:
        options = {"verify_aud": bool(JWT_AUDIENCE)}
        kwargs = {}
        if JWT_ISSUER:
            kwargs["issuer"] = JWT_ISSUER
        if JWT_AUDIENCE:
            kwargs["audience"] = JWT_AUDIENCE
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options=options, **kwargs)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "typ": "access",
    }
    if JWT_ISSUER:
        to_encode["iss"] = JWT_ISSUER
    if JWT_AUDIENCE:
        to_encode["aud"] = JWT_AUDIENCE
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def require_auth(creds: HTTPAuthorizationCredentials = Depends(bearer_required)) -> str:
    payload = _jwt_decode(creds.credentials)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token (missing subject)")
    return sub


def optional_auth(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_optional)) -> Optional[str]:
    if not creds:
        return None
    try:
        payload = _jwt_decode(creds.credentials)
        return payload.get("sub")
    except HTTPException:
        return None
