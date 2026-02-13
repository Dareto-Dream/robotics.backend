# STANDARDS.md — API Route Reference

Every route, its method, authentication requirements, inputs, and example payloads.

---

## Authentication Convention

| Label | Meaning |
|-------|---------|
| **JWT Required** | Send `Authorization: Bearer <access_token>` header |
| **No Auth** | No header needed |

All request bodies are JSON (`Content-Type: application/json`) unless noted.

---

## 1. Auth Routes (`/auth`)

### POST `/auth/register`

Create a new account.

| Auth | JWT Required |
|------|:---:|
| | **No** |

**Body (required):**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `email` | string | ✅ | Lowercased automatically |
| `password` | string | ✅ | Min 8 characters |

**Example:**
```json
{
  "email": "scout@team1234.org",
  "password": "securePass123"
}
```

**Response `201`:**
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

**Errors:** `400` missing fields / short password, `409` email taken.

---

### POST `/auth/login`

Log in with existing credentials.

| Auth | JWT Required |
|------|:---:|
| | **No** |

**Body (required):**

| Field | Type | Required |
|-------|------|:--------:|
| `email` | string | ✅ |
| `password` | string | ✅ |

**Example:**
```json
{
  "email": "scout@team1234.org",
  "password": "securePass123"
}
```

**Response `200`:**
```json
{
  "access": "<jwt>",
  "refresh": "<jwt>"
}
```

**Errors:** `400` missing fields, `401` invalid credentials.

---

### POST `/auth/refresh`

Rotate tokens. The old refresh token is invalidated and a new pair is issued.

| Auth | JWT Required |
|------|:---:|
| | **No** (uses refresh token in body) |

**Body (required):**

| Field | Type | Required |
|-------|------|:--------:|
| `refresh` | string | ✅ |

**Example:**
```json
{
  "refresh": "<old_refresh_jwt>"
}
```

**Response `200`:**
```json
{
  "access": "<new_jwt>",
  "refresh": "<new_jwt>"
}
```

**Errors:** `400` missing token, `401` expired / invalid / reuse detected.

---

### POST `/auth/logout`

Invalidate the current session's refresh token.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body:** None.

**Response `200`:**
```json
{ "success": true }
```

---

### GET `/auth/health`

Liveness check for auth DB and Redis.

| Auth | JWT Required |
|------|:---:|
| | **No** |

**Response `200` / `503`:**
```json
{
  "status": "healthy",
  "auth_db": true,
  "auth_redis": true
}
```

---

## 2. Device / OAC Routes (`/auth/devices`)

### POST `/auth/devices/register`

Register a new device for offline use. Returns a signed OAC.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body:**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `device_public_key` | string | ✅ | PEM or base64 of client-generated public key |
| `device_name` | string | ✅ | Human label, e.g. "John's Pixel 8" |
| `device_type` | string | ✅ | `android`, `ios`, `windows`, `linux`, `macos` |
| `app_version` | string | ❌ | e.g. "2.1.0" |

**Example:**
```json
{
  "device_public_key": "-----BEGIN PUBLIC KEY-----\nMCow...\n-----END PUBLIC KEY-----",
  "device_name": "John's Pixel 8",
  "device_type": "android",
  "app_version": "2.1.0"
}
```

**Response `201`:**
```json
{
  "success": true,
  "device_id": "uuid-string",
  "oac": "<signed_jwt_ed25519>",
  "oac_public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

**Errors:** `400` missing required fields.

---

### POST `/auth/devices/renew`

Renew an existing device's OAC. Call when the app reconnects online.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body:**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `device_id` | string | ✅ | UUID from registration |
| `app_version` | string | ❌ | |

**Example:**
```json
{
  "device_id": "abc12345-...",
  "app_version": "2.2.0"
}
```

**Response `200`:**
```json
{
  "success": true,
  "device_id": "abc12345-...",
  "oac": "<new_signed_jwt>"
}
```

**Errors:** `400` missing device_id, `403` device revoked, `404` device not found.

---

### GET `/auth/devices`

List all registered devices for the current user.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Response `200`:**
```json
{
  "devices": [
    {
      "device_id": "uuid",
      "device_name": "John's Pixel 8",
      "device_type": "android",
      "app_version": "2.1.0",
      "is_revoked": false,
      "registered_at": "2025-06-01T12:00:00",
      "last_renewed": "2025-06-10T09:30:00"
    }
  ],
  "count": 1
}
```

---

### DELETE `/auth/devices/<device_id>`

Revoke a device. The OAC remains locally valid until expiry but cannot be renewed.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Response `200`:**
```json
{ "success": true, "message": "Device revoked" }
```

**Errors:** `404` device not found.

---

### GET `/auth/devices/public-key`

Get the server's OAC Ed25519 public key. Clients embed this to verify OACs offline.

| Auth | JWT Required |
|------|:---:|
| | **No** |

**Response `200`:**
```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
}
```

---

## 3. Team & Roster Routes (`/api`)

### GET `/api/auth/sync`

Primary identity endpoint. Returns the user's team, role, permissions, and full roster. Also marks the user as active (cosmetic).

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Response `200` (on a team):**
```json
{
  "user": { "id": "uuid", "email": "scout@team.org" },
  "team": {
    "team_code": "A1B2C3",
    "name": "Team Titan",
    "team_number": "1234",
    "description": "",
    "created_by": "uuid",
    "created_at": "2025-01-01T00:00:00"
  },
  "member": {
    "user_id": "uuid",
    "display_name": "John",
    "bio": "",
    "profile_pic_url": "",
    "role": "scout",
    "subteam": "programming",
    "joined_at": "2025-01-15T00:00:00",
    "is_active": true
  },
  "role": "scout",
  "permissions": ["view_dashboard", "submit_match_report", "..."],
  "roster": [ ... ]
}
```

**Response `200` (no team):**
```json
{
  "user": { "id": "uuid", "email": "scout@team.org" },
  "team": null,
  "member": null,
  "role": "viewer",
  "permissions": ["view_dashboard", "view_manual", "view_settings", "edit_own_profile"],
  "roster": []
}
```

---

### POST `/api/status/active`

Set your is_active flag (cosmetic — shows you're on the app).

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body (required):**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `is_active` | boolean | ✅ | `true` or `false` |

**Example:**
```json
{ "is_active": false }
```

**Response `200`:**
```json
{ "success": true, "is_active": false }
```

---

### POST `/api/teams/create`

Create a new team. Caller becomes owner.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body:**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `name` | string | ✅ | Team name |
| `team_number` | string | ❌ | FRC team number |
| `display_name` | string | ❌ | Your display name on the roster |

**Example:**
```json
{
  "name": "Team Titan",
  "team_number": "1234",
  "display_name": "Coach Smith"
}
```

**Response `201`:** Full team + member + role + permissions payload.

**Errors:** `400` already on a team or missing name.

---

### POST `/api/teams/join`

Join an existing team by 6-character code.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body:**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `join_code` | string | ✅ | 6-char uppercase code |
| `display_name` | string | ❌ | Your roster display name |

**Example:**
```json
{
  "join_code": "A1B2C3",
  "display_name": "Jane"
}
```

**Response `201`:** Full team + member payload. Role defaults to `scout`.

**Errors:** `400` already on team / bad code, `404` invalid code.

---

### POST `/api/teams/leave`

Leave your current team.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body:** None.

**Behavior:**
- **Non-owner:** Membership row is deleted. You are removed from the team.
- **Owner (only member):** Team is deleted entirely.
- **Owner (other members exist):** Returns `400` — you must transfer ownership first.

**Response `200`:**
```json
{ "success": true, "message": "Left team" }
```

---

### POST `/api/teams/transfer`

Transfer team ownership to another member. Caller is demoted to admin.

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | Owner only |

**Body (required):**

| Field | Type | Required |
|-------|------|:--------:|
| `target_user_id` | string (UUID) | ✅ |

**Example:**
```json
{ "target_user_id": "abc-def-123-..." }
```

**Response `200`:**
```json
{
  "success": true,
  "message": "Ownership transferred to abc-def-123-...",
  "new_owner": "abc-def-123-...",
  "your_new_role": "admin"
}
```

**Errors:** `400` target is self / missing, `403` not owner, `404` target not on team.

---

### GET `/api/teams/info`

Get your team's info.

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | `view_roster` |

**Response `200`:**
```json
{
  "team": { "team_code": "...", "name": "...", ... },
  "member": { "user_id": "...", "role": "...", ... }
}
```

---

### PUT `/api/teams/settings`

Update team name, number, or description.

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | `edit_team_settings` |

**Body (all optional, at least one required):**

| Field | Type | Required |
|-------|------|:--------:|
| `name` | string | ❌ |
| `team_number` | string | ❌ |
| `description` | string | ❌ |

**Example:**
```json
{ "name": "Team Titan v2", "description": "Updated for 2026 season" }
```

**Response `200`:** `{ "success": true, "team": { ... } }`

---

### GET `/api/roster`

Get the full team roster.

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | `view_roster` |

**Response `200`:**
```json
{
  "roster": [ { "user_id": "...", "display_name": "...", "role": "...", "is_active": true, ... } ],
  "count": 5
}
```

> **Note on `is_active`:** This is purely cosmetic. It indicates whether the user is currently using the app, not whether they are on the team. If a row exists in the roster, they are a member.

---

### PUT `/api/roster/profile`

Update your own profile fields.

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body (all optional):**

| Field | Type | Notes |
|-------|------|-------|
| `display_name` / `displayName` | string | |
| `bio` | string | |
| `subteam` | string | |
| `profile_pic_url` / `profilePicUrl` | string | URL to avatar |

**Example:**
```json
{ "display_name": "Jane S.", "subteam": "programming" }
```

---

### PUT `/api/roster/<user_id>/role`

Change a member's role.

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | `manage_roles` |

**Body (required):**

| Field | Type | Required | Notes |
|-------|------|:--------:|-------|
| `role` | string | ✅ | One of: `viewer`, `scout`, `leadScout`, `driveCoach`, `analyst`, `admin`. Cannot assign `owner` — use `/teams/transfer`. |

**Example:**
```json
{ "role": "admin" }
```

**Errors:** `400` invalid role / assigning owner, `403` role too high / target is owner, `404` not found.

---

### DELETE `/api/roster/<user_id>`

Remove a member from the team (hard delete).

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | `manage_roster` |

**Errors:** `400` trying to remove self (use `/teams/leave`), `403` target is owner, `404` not found.

---

## 4. Permission Query Routes

### GET `/api/permissions/roles`

List all roles and their permissions. **No auth required.**

### GET `/api/permissions/guest`

Get the guest/viewer permission set. **No auth required.**

---

## 5. Admin Routes

### GET `/api/admin/stats`

Team and membership statistics.

| Auth | JWT Required | Permission |
|------|:---:|:---:|
| | **Yes** | `view_admin` |

---

## 6. FRC Data Routes (`/api`)

All require JWT.

| Route | Method | Params |
|-------|--------|--------|
| `/api/events` | GET | `?season=2025` (optional, defaults current year) |
| `/api/events/<event_code>/teams` | GET | `?season=2025` |
| `/api/events/<event_code>/matches` | GET | `?season=2025` |
| `/api/modules/manifest` | GET | — |

---

## 7. Report Routes (`/api`)

### POST `/api/reports/match`

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body (required):**

| Field | Type | Required |
|-------|------|:--------:|
| `event_code` | string | ✅ |
| `team_number` | string | ✅ |
| `match_number` | integer | ✅ |
| *(any other fields)* | any | ❌ (stored in `data` JSONB) |

### GET `/api/reports/match`

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Query params (all optional):** `event_code`, `team_number`, `match_number`

### POST `/api/reports/pit`

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Body (required):**

| Field | Type | Required |
|-------|------|:--------:|
| `event_code` | string | ✅ |
| `team_number` | string | ✅ |
| *(any other fields)* | any | ❌ |

### GET `/api/reports/pit`

| Auth | JWT Required |
|------|:---:|
| | **Yes** |

**Query params (all optional):** `event_code`, `team_number`

---

## 8. Health

### GET `/api/health`

**No auth.** Returns database connection status.

```json
{
  "status": "healthy",
  "timestamp": "2025-06-01T12:00:00",
  "database_connected": true
}
```
