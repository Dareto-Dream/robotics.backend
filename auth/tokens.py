# auth/tokens.py
#
# JWT creation for access and refresh tokens.
#
# Access token:  short-lived (30 min), used on every API request
# Refresh token: long-lived (30 days), stored in Redis, used only to
#                rotate both tokens via POST /auth/refresh

from datetime import datetime, timedelta, timezone
import jwt
import os

SECRET = os.environ.get("AUTH_JWT_SECRET", "dev_secret_change_me")
ALGO   = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES  = 30
REFRESH_TOKEN_EXPIRE_DAYS    = 30


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "type": "access", "exp": expire}
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT. Raises jwt.ExpiredSignatureError or
    jwt.InvalidTokenError on failure — callers should handle these.
    """
    return jwt.decode(token, SECRET, algorithms=[ALGO])
