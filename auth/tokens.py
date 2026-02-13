# auth/tokens.py
#
# JWT creation for access, refresh, and offline authorization certificates.
#
# Access token:  short-lived (30 min), used on every API request (HS256)
# Refresh token: long-lived (30 days), stored in Redis (HS256)
# OAC:           device-bound offline certificate (Ed25519 asymmetric)

from datetime import datetime, timedelta, timezone
import jwt
import os
import hashlib
import json

# ─── Symmetric secret for access / refresh tokens ───
SECRET = os.environ.get("AUTH_JWT_SECRET", "dev_secret_change_me")
ALGO = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 30

# ─── Asymmetric keys for Offline Authorization Certificates ───
# Ed25519 PEM keys — generate with:
#   python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; \
#   from cryptography.hazmat.primitives import serialization; \
#   pk = Ed25519PrivateKey.generate(); \
#   print(pk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()); \
#   print(pk.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode())"
#
OAC_PRIVATE_KEY_PEM = os.environ.get("OAC_PRIVATE_KEY", "")
OAC_PUBLIC_KEY_PEM = os.environ.get("OAC_PUBLIC_KEY", "")
OAC_ALGO = "EdDSA"
OAC_EXPIRE_DAYS = int(os.environ.get("OAC_EXPIRE_DAYS", "7"))


def _load_oac_private_key():
    """Load Ed25519 private key from PEM string."""
    if not OAC_PRIVATE_KEY_PEM:
        raise RuntimeError(
            "OAC_PRIVATE_KEY not configured. "
            "Set the Ed25519 private key PEM in environment."
        )
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    return load_pem_private_key(OAC_PRIVATE_KEY_PEM.encode(), password=None)


def _load_oac_public_key():
    """Load Ed25519 public key from PEM string."""
    if not OAC_PUBLIC_KEY_PEM:
        raise RuntimeError(
            "OAC_PUBLIC_KEY not configured. "
            "Set the Ed25519 public key PEM in environment."
        )
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    return load_pem_public_key(OAC_PUBLIC_KEY_PEM.encode())


# ─── Standard tokens (HS256) ───

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "type": "access", "exp": expire}
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def create_refresh_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def decode_token(token: str) -> dict:
    """Decode HS256 access/refresh token."""
    return jwt.decode(token, SECRET, algorithms=[ALGO])


# ─── Offline Authorization Certificate (Ed25519) ───

def create_oac(
    user_id: str,
    device_id: str,
    device_public_key_hash: str,
    app_version: str = "",
) -> str:
    """
    Issue an Offline Authorization Certificate.

    This is a JWT signed with Ed25519 (asymmetric) so that clients can
    verify it offline using only the embedded public key — no server needed.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=OAC_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "did": device_id,
        "dpk": device_public_key_hash,
        "iat": now,
        "exp": expire,
        "scope": "offline_access",
        "type": "oac",
        "app_version": app_version,
    }

    private_key = _load_oac_private_key()
    return jwt.encode(payload, private_key, algorithm=OAC_ALGO)


def decode_oac(token: str) -> dict:
    """
    Decode and verify an OAC using the server's Ed25519 public key.
    Used server-side for renewal validation.
    """
    public_key = _load_oac_public_key()
    return jwt.decode(token, public_key, algorithms=[OAC_ALGO])


def get_oac_public_key_pem() -> str:
    """
    Return the OAC public key PEM for clients to embed.
    Clients use this to verify OACs offline.
    """
    return OAC_PUBLIC_KEY_PEM


def hash_device_public_key(device_public_key: str) -> str:
    """SHA-256 hash of the device's public key for embedding in OAC."""
    return hashlib.sha256(device_public_key.encode()).hexdigest()
