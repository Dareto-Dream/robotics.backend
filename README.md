# `standards.md`

Authoritative Backend API Documentation

This document describes every public HTTP route exposed by the server, including:

* authentication requirements
* request body schema
* query parameters
* permissions
* responses
* side effects

The API uses **JWT Bearer authentication** and a **team-based permission model**.

---

## Authentication

Protected endpoints require:

```
Authorization: Bearer <access_token>
```

Identity is injected from the JWT via `require_auth` .

Tokens are rotated using refresh tokens; reuse invalidates the session .

---

# ROUTES

---

## AUTH (5)

---

### 1. POST `/auth/register`

Create a new account.

**Body**

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

Rules:

* password ≥ 8 characters 
* email unique

**Response**

```json
{
  "access": "JWT",
  "refresh": "JWT"
}
```

---

### 2. POST `/auth/login`

Authenticate user.

**Body**

```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Success**

```
200
```

Returns access + refresh tokens.

**Failure**

```
401 Invalid email or password
```

---

### 3. POST `/auth/refresh`

Rotate refresh token.

**Body**

```json
{
  "refresh": "JWT"
}
```

Returns new token pair.

---

### 4. POST `/auth/logout`

Requires authentication.

Deletes refresh token.

```
{ "success": true }
```

---

### 5. GET `/auth/health`

Auth database + redis check.

---

## IDENTITY / PERMISSIONS (3)

---

### 6. GET `/api/auth/sync`

Primary identity endpoint.

Returns:

* user
* team
* role
* permissions
* roster

If user has no team → viewer permissions .

---

### 7. GET `/api/permissions/roles`

Public.

Returns all roles and permissions.

---

### 8. GET `/api/permissions/guest`

Public.

Returns guest permissions.

---

## TEAM MANAGEMENT (5)

---

### 9. POST `/api/teams/create`

Creates a team and makes caller owner.

**Body**

```json
{
  "name": "Team Name",
  "team_number": "1234",
  "display_name": "Scout Leader"
}
```

Generates 6-character join code .

---

### 10. POST `/api/teams/join`

Join a team.

```json
{
  "join_code": "ABCD23",
  "display_name": "Scout1"
}
```

User becomes scout.

---

### 11. POST `/api/teams/leave`

Leaves team.
Empty teams are automatically deleted .

---

### 12. GET `/api/teams/info`

Permission required: `view_roster`

Returns team + member info.

---

### 13. PUT `/api/teams/settings`

Permission required: `edit_team_settings`

Updatable:

```
name
team_number
description
```

---

## ROSTER (4)

---

### 14. GET `/api/roster`

Permission: `view_roster`

Returns active members list.

---

### 15. PUT `/api/roster/profile`

Update your profile.

**Fields**

```
display_name
bio
subteam
profile_pic_url
```

---

### 16. PUT `/api/roster/{user_id}/role`

Permission: `manage_roles`

Change member role.

Restrictions:

* cannot promote above yourself
* cannot demote owner 

---

### 17. DELETE `/api/roster/{user_id}`

Permission: `manage_roster`

Removes member.

---

## FRC DATA (3)

External FIRST Robotics data cached in memory .

| Resource | Cache |
| -------- | ----- |
| Events   | 6h    |
| Teams    | 12h   |
| Matches  | 30m   |

---

### 18. GET `/api/events`

Optional:

```
?season=2025
```

---

### 19. GET `/api/events/{event_code}/teams`

Returns all teams attending event.

---

### 20. GET `/api/events/{event_code}/matches`

Returns match schedule.

---

## MODULES (1)

---

### 21. GET `/api/modules/manifest`

Returns enabled scouting modules .

```json
{
  "version":"1.0",
  "modules":[
    {"id":"auto_scoring","name":"Autonomous Scoring"},
    {"id":"teleop_performance","name":"Teleop Performance"},
    {"id":"pit_scouting","name":"Pit Scouting"}
  ]
}
```

---

## REPORTS & HEALTH (1 + shared)

---

### 22. `/api/reports/match` (GET, POST)

**POST — submit report**

Required:

```
event_code
team_number
match_number
```

Example:

```json
{
  "event_code":"HIHO",
  "team_number":368,
  "match_number":12,
  "auto_points":4,
  "cycles":7,
  "notes":"fast robot"
}
```

Stored as raw JSON .

**GET — fetch reports**

Filters:

```
event_code
team_number
match_number
```

---

### 23. `/api/reports/pit` (GET, POST)

**POST**

```
event_code
team_number
```

**GET**
Filters:

```
event_code
team_number
```

---

### 24. GET `/api/health`

Database connectivity test .

---

## Error Codes

| Code | Meaning                |
| ---- | ---------------------- |
| 400  | Missing/invalid fields |
| 401  | Not authenticated      |
| 403  | Permission denied      |
| 404  | Not found              |
| 409  | Email already exists   |
| 503  | FRC API unavailable    |

---

## Required Client Behavior

1. Login
2. Store tokens
3. Call `/api/auth/sync`
4. Join or create team
5. Refresh tokens periodically
6. Never compute permissions locally 