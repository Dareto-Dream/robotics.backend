# OAC.md — Offline Authorization Certificate System

## Overview

The Offline Authorization Certificate (OAC) is a **device-bound, asymmetrically-signed JWT** that allows authenticated users to use the app when the server is unreachable. It does not replace the existing JWT auth system — it adds a layer on top of it.

```
ONLINE AUTH  → identity verification  (HS256 access/refresh tokens + Redis)
OFFLINE CERT → device authorization   (Ed25519 OAC + device keypair)
```

---

## Why Not Just Use the Existing JWT Offline?

The existing access/refresh tokens use **HS256** (symmetric signing). This means the same secret that signs tokens also verifies them. If you embed that secret in a client app, any user can forge tokens. Additionally:

- Access tokens expire in 30 minutes — useless offline.
- Refresh tokens require Redis to validate — no server, no validation.
- Neither token is bound to a specific device — they can be copied.

The OAC solves all three problems.

---

## Architecture

### Token Types

| Token | Algorithm | Lifetime | Verification | Purpose |
|-------|-----------|----------|-------------|---------|
| Access JWT | HS256 | 30 min | Server (symmetric secret) | API requests |
| Refresh JWT | HS256 | 30 days | Server (Redis + symmetric secret) | Token rotation |
| **OAC** | **Ed25519** | **7 days** | **Client (embedded public key)** | **Offline access** |

### Key Material

| Key | Location | Purpose |
|-----|----------|---------|
| Server Ed25519 **private** key | Server env (`OAC_PRIVATE_KEY`) | Signs OACs |
| Server Ed25519 **public** key | Embedded in client app + server env (`OAC_PUBLIC_KEY`) | Verifies OACs offline |
| Device **private** key | Device secure storage (Keystore/Keychain/TPM) | Proves device identity |
| Device **public** key | Sent to server at registration, hash stored in OAC | Binds OAC to device |

---

## Flow

### 1. Device Registration (online, one-time)

```
Client                                    Server
  │                                          │
  │── POST /auth/devices/register ──────────▶│
  │   Authorization: Bearer <access_token>   │
  │   {                                      │
  │     "device_public_key": "<PEM>",        │
  │     "device_name": "John's Pixel 8",     │
  │     "device_type": "android",            │
  │     "app_version": "2.1.0"               │
  │   }                                      │
  │                                          │
  │◀──────────── 201 Created ────────────────│
  │   {                                      │
  │     "device_id": "uuid",                 │
  │     "oac": "<ed25519_signed_jwt>",       │
  │     "oac_public_key": "<PEM>"            │
  │   }                                      │
  │                                          │
  │  Store:                                  │
  │   • OAC token                            │
  │   • OAC public key (for offline verify)  │
  │   • device_id                            │
  └──────────────────────────────────────────┘
```

**What the client must do:**

1. Generate an Ed25519 or ECDSA keypair using the platform's secure hardware:
   - **Android:** Android Keystore
   - **iOS / macOS:** Secure Enclave / Keychain
   - **Windows:** DPAPI / TPM
   - **Linux:** libsecret + filesystem fallback

2. The private key **must never leave the device**.

3. Send only the public key, device name, and device type to the server.

4. Store the returned OAC and the server's public key locally.

### 2. OAC Renewal (online, periodic)

Every time the app has internet access, it should silently renew the OAC:

```
Client                                    Server
  │                                          │
  │── POST /auth/devices/renew ─────────────▶│
  │   Authorization: Bearer <access_token>   │
  │   { "device_id": "uuid" }               │
  │                                          │
  │◀──────────── 200 OK ────────────────────│
  │   { "oac": "<new_signed_jwt>" }         │
  └──────────────────────────────────────────┘
```

This should happen transparently as part of the normal token refresh cycle:

```
refresh token → new access token → renew OAC
```

The user never notices.

### 3. Offline Authentication (no network)

When the app launches without internet, it performs **local verification** instead of calling `/api/auth/sync`.

#### Step A — Verify OAC Signature

```python
# Pseudocode
is_valid = verify(oac_token, server_public_key)
if not is_valid:
    reject()  # forged or tampered
```

Uses the server's Ed25519 public key embedded in the app. No network needed.

#### Step B — Check Expiration

```python
if now > oac.exp:
    require_internet()  # must reconnect to renew
```

This replaces Redis revocation checks for offline mode. Short expiry (7 days default) ensures banned users are locked out after the certificate expires.

#### Step C — Prove Device Ownership (anti-copy)

This is the critical step most implementations miss. Even if someone copies your app data to another device, they won't have the hardware-bound private key.

```python
# Client generates a challenge
nonce = random_bytes(32)

# Client signs the nonce with the device private key
signature = sign(nonce, device_private_key)

# Client verifies the signature using the public key hash from the OAC
device_public_key = load_from_secure_storage()
is_owner = verify(nonce, signature, device_public_key)
assert sha256(device_public_key) == oac.dpk

if not is_owner:
    reject()  # device key mismatch — copied data
```

If all three steps pass: the user is authorized offline.

---

## OAC JWT Payload

```json
{
  "sub": "user-uuid",
  "did": "device-uuid",
  "dpk": "sha256-hash-of-device-public-key",
  "iat": 1717200000,
  "exp": 1717804800,
  "scope": "offline_access",
  "type": "oac",
  "app_version": "2.1.0"
}
```

| Claim | Description |
|-------|-------------|
| `sub` | User ID |
| `did` | Device ID (from registration) |
| `dpk` | SHA-256 hash of the device's public key |
| `iat` | Issued at timestamp |
| `exp` | Expiration timestamp |
| `scope` | Always `offline_access` |
| `type` | Always `oac` |
| `app_version` | App version at time of issue |

---

## Token Lifetime Strategy

```
access token:      30 minutes
refresh token:     30 days
OAC:               7 days (configurable via OAC_EXPIRE_DAYS)
```

Every time the app gets internet:

```
refresh token  →  new access token
access token   →  request new OAC
```

If a user stays offline for more than 7 days, the app locks until they reconnect. This is intentional — it is the revocation mechanism.

---

## Revocation

### Problem

You cannot instantly revoke an offline certificate. No system can — the device may never be reachable.

### Solution: Delayed Revocation

1. **Short certificate expiry** (7 days default)
2. **Force renewal on reconnect** — the app always renews the OAC when online
3. **Server denies renewal for banned/revoked users** — revoked devices get `403`
4. **Admin can revoke devices** via `DELETE /auth/devices/<device_id>`

**Result:** A banned user continues to work offline until the OAC expires, then is locked out permanently. This is how Steam, Adobe, and other major offline-capable apps handle it.

### Revocation Scenarios

| Scenario | What Happens |
|----------|-------------|
| User banned while offline | Works until OAC expires (≤7 days), then locked |
| Device stolen | Admin revokes device; works until OAC expires, cannot renew |
| User logs out | Client should delete local OAC; device can be re-registered |
| Device lost | Admin revokes via `/auth/devices/<id>` from another device |

---

## Security Rules

### DO

- ✅ Sign OACs with **Ed25519** (asymmetric — client cannot forge)
- ✅ Bind the OAC to the device's public key (`dpk` claim)
- ✅ Store device private keys in hardware-backed secure storage
- ✅ Verify OAC signature + expiry + device key ownership on every offline launch
- ✅ Renew the OAC every time the app connects to the internet
- ✅ Keep OAC expiry short (7–14 days max)
- ✅ Embed the server's Ed25519 **public** key in the client app binary

### DO NOT

- ❌ Use HS256 for OACs (the client could forge tokens with the shared secret)
- ❌ Store user passwords locally for offline auth
- ❌ Reuse refresh tokens for offline validation
- ❌ Trust the system clock blindly (allow ±5 min skew)
- ❌ Store the device private key in shared preferences or plain files
- ❌ Set OAC expiry beyond 14 days

---

## Database Schema

### `devices` table

```sql
CREATE TABLE devices (
    device_id              UUID PRIMARY KEY,
    user_id                UUID NOT NULL REFERENCES users(user_id),
    device_name            TEXT NOT NULL,
    device_type            TEXT NOT NULL,
    device_public_key_hash TEXT NOT NULL,
    app_version            TEXT DEFAULT '',
    is_revoked             BOOLEAN DEFAULT FALSE,
    registered_at          TIMESTAMP DEFAULT NOW(),
    last_renewed           TIMESTAMP DEFAULT NOW()
);
```

---

## API Endpoints Summary

| Method | Route | Auth | Purpose |
|--------|-------|:----:|---------|
| POST | `/auth/devices/register` | JWT | Register device, get OAC |
| POST | `/auth/devices/renew` | JWT | Renew OAC |
| GET | `/auth/devices` | JWT | List user's devices |
| DELETE | `/auth/devices/<device_id>` | JWT | Revoke a device |
| GET | `/auth/devices/public-key` | None | Get OAC verification key |

See [STANDARDS.md](./STANDARDS.md) for full request/response details.

---

## Server Key Generation

Generate the Ed25519 keypair for signing OACs:

```python
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

pk = Ed25519PrivateKey.generate()

private_pem = pk.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption()
).decode()

public_pem = pk.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo
).decode()

print("OAC_PRIVATE_KEY:")
print(private_pem)
print("OAC_PUBLIC_KEY:")
print(public_pem)
```

Set both as environment variables. When storing in `.env`, replace newlines with `\n`:

```
OAC_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMC4C...base64...\n-----END PRIVATE KEY-----"
OAC_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\nMCow...base64...\n-----END PUBLIC KEY-----"
```

---

## Client Implementation Checklist

- [ ] Generate device keypair using platform secure storage
- [ ] Call `POST /auth/devices/register` on first launch (when online)
- [ ] Store OAC token, device_id, and server public key locally
- [ ] On every online launch: call `POST /auth/devices/renew`
- [ ] On offline launch: verify OAC signature → check expiry → prove device ownership
- [ ] On logout: delete local OAC and device credentials
- [ ] Embed the server's public key in the app binary (also available via GET `/auth/devices/public-key`)
