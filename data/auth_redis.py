# data/auth_redis.py
#
# Redis client exclusively for auth session/token storage.
# Uses AUTH_REDIS_URL — isolated from any other Redis instances.
#
# Stores:
#   refresh:<user_id>  →  refresh token string  (TTL: 30 days)
#
# Strict rotation: on every /auth/refresh call the old key is deleted
# and a new one is written. Logout also deletes the key, immediately
# invalidating the refresh token server-side.

import os
import redis

AUTH_REDIS_URL = os.environ.get("AUTH_REDIS_URL", "redis://localhost:6379")

# decode_responses=True means all get/set values are plain strings
_client: redis.Redis = redis.from_url(AUTH_REDIS_URL, decode_responses=True)

REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days


def set_refresh_token(user_id: str, token: str) -> None:
    """Store a refresh token, overwriting any previous value."""
    _client.set(f"refresh:{user_id}", token, ex=REFRESH_TTL_SECONDS)


def get_refresh_token(user_id: str) -> str | None:
    """Return the stored refresh token, or None if missing / expired."""
    return _client.get(f"refresh:{user_id}")


def delete_refresh_token(user_id: str) -> None:
    """Delete the refresh token (logout or rotation)."""
    _client.delete(f"refresh:{user_id}")


def ping() -> bool:
    """Health-check helper used by /auth/health."""
    try:
        return _client.ping()
    except Exception:
        return False
