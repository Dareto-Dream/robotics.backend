"""
permissions_roster.py — Server-authoritative team, permission, & roster system

Identity model:
  - Authorization: Basic <credential>  →  shared backend credential (one per deployment)
  - X-User-Id: <uuid>                  →  per-device user identity (generated on first app launch)

Data model:
  - Teams are the organisational unit.  Each has a unique 6-char join code.
  - Members belong to exactly one team.  Membership is keyed by the user's UUID.
  - Roles are assigned per-member.  Permissions are computed from the role on the server
    and returned to the client.  The client NEVER computes permissions locally.

Lifecycle:
  1. Creator calls POST /api/teams/create  → server generates join code, adds creator as owner.
  2. Others call   POST /api/teams/join    → server validates code, adds member as scout.
  3. Member calls  POST /api/teams/leave   → server marks them inactive, cleans up empty teams.
  4. Every sync    POST /api/auth/sync     → server returns role + permissions + team + roster.
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from datetime import datetime
import secrets
from helpers import USERNAME, PASSWORD

from data.users_repo import ensure_user
from data.db import get_conn, release_conn


permissions_roster = Blueprint('permissions_roster', __name__)

# ━━━━━━━━━━━━━━━ ROLE & PERMISSION DEFINITIONS ━━━━━━━━━━━━━━━━━━

ROLES = {
    "viewer":     {"level": 0, "name": "Viewer",      "description": "Read-only access"},
    "scout":      {"level": 1, "name": "Scout",        "description": "Submit reports, view analytics"},
    "leadScout":  {"level": 2, "name": "Lead Scout",   "description": "View all reports, export data"},
    "driveCoach": {"level": 2, "name": "Drive Coach",  "description": "Timer access, strategy tools"},
    "analyst":    {"level": 2, "name": "Analyst",      "description": "Full analytics, comparison tools"},
    "admin":      {"level": 3, "name": "Admin",        "description": "All features, team management"},
    "owner":      {"level": 4, "name": "Owner",        "description": "Full control, cannot be demoted"},
}

ROLE_PERMISSIONS = {
    "viewer": [
        "view_dashboard", "view_manual", "view_settings", "edit_own_profile",
    ],
    "scout": [
        "view_dashboard", "view_scoreboard", "view_manual", "view_scouting",
        "view_analytics", "view_roster", "view_settings", "edit_own_profile",
        "submit_match_report", "submit_pit_report",
        "edit_own_reports", "delete_own_reports", "sync_data",
    ],
    "leadScout": [
        "view_dashboard", "view_scoreboard", "view_manual", "view_scouting",
        "view_analytics", "view_alliance", "view_roster", "view_settings",
        "edit_own_profile", "submit_match_report", "submit_pit_report",
        "edit_own_reports", "delete_own_reports", "view_all_reports",
        "edit_alliance", "export_analytics", "select_event", "sync_data",
    ],
    "driveCoach": [
        "view_dashboard", "view_scoreboard", "view_manual", "view_scouting",
        "view_drive", "view_analytics", "view_roster", "view_settings",
        "edit_own_profile", "submit_match_report", "submit_pit_report",
        "edit_own_reports", "use_drive", "sync_data",
    ],
    "analyst": [
        "view_dashboard", "view_scoreboard", "view_manual", "view_scouting",
        "view_analytics", "view_alliance", "view_roster", "view_settings",
        "edit_own_profile", "submit_match_report", "submit_pit_report",
        "edit_own_reports", "delete_own_reports", "view_all_reports",
        "edit_alliance", "export_analytics", "select_event", "sync_data",
    ],
    "admin": [
        "view_dashboard", "view_scoreboard", "view_manual", "view_scouting",
        "view_alliance", "view_drive", "view_analytics", "view_roster",
        "view_admin", "view_settings", "edit_own_profile",
        "submit_match_report", "submit_pit_report",
        "edit_own_reports", "delete_own_reports",
        "edit_any_report", "delete_any_report", "view_all_reports",
        "edit_alliance", "use_drive", "export_analytics",
        "edit_team_settings", "manage_roles", "manage_roster",
        "select_event", "sync_data", "edit_modules",
    ],
    "owner": [
        "view_dashboard", "view_scoreboard", "view_manual", "view_scouting",
        "view_alliance", "view_drive", "view_analytics", "view_roster",
        "view_admin", "view_settings", "edit_own_profile",
        "submit_match_report", "submit_pit_report",
        "edit_own_reports", "delete_own_reports",
        "edit_any_report", "delete_any_report", "view_all_reports",
        "edit_alliance", "use_drive", "export_analytics",
        "edit_team_settings", "manage_roles", "manage_roster",
        "select_event", "sync_data", "edit_modules",
    ],
}

GUEST_PERMISSIONS = [
    "view_dashboard", "view_manual", "view_settings", "edit_own_profile",
]


# ━━━━━━━━━━━━━━━━━━ AUTH HELPERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _check_auth(user, pw):
    return (secrets.compare_digest(user, USERNAME)
            and secrets.compare_digest(pw, PASSWORD))


def requires_auth(f):
    """Verify the shared Basic-Auth credential."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_auth(auth.username, auth.password):
            return jsonify({"detail": "Invalid credentials"}), 401, {
                "WWW-Authenticate": 'Basic realm="Login Required"'}
        return f(*args, **kwargs)
    return wrapper


def _get_user_id():
    """Read the per-device UUID from the X-User-Id header."""
    return (request.headers.get("X-User-Id") or "").strip() or None


# ━━━━━━━━━━━━━━━━━━ DATABASE HELPERS ━━━━━━━━━━━━━━━━━━━━━━━━━━

_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I


def _generate_join_code():
    """Create a unique 6-char code not already in the teams table."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        for _ in range(100):
            code = "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(6))
            cur.execute("SELECT 1 FROM teams WHERE team_code=%s", (code,))
            if cur.fetchone() is None:
                return code
    finally:
        cur.close()
        release_conn(conn)
    raise RuntimeError("Could not generate unique join code")


def _db_get_user_membership(user_id):
    """
    Return a dict with team + member info for an active member, or None.
    Shape mirrors the old in-memory structure used by the rest of the module.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT t.team_code, t.name, t.team_number, t.description,
                   t.created_by, t.created_at,
                   m.role, m.display_name, m.bio, m.profile_pic_url, m.subteam, m.joined_at
            FROM memberships m
            JOIN teams t ON t.team_code = m.team_code
            WHERE m.user_id = %s AND m.is_active = TRUE
        """, (user_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        release_conn(conn)

    if row is None:
        return None

    (team_code, name, team_number, description,
     created_by, created_at,
     role, display_name, bio, profile_pic_url, subteam, joined_at) = row

    return {
        "team": {
            "team_code":   team_code,
            "name":        name,
            "team_number": team_number or "",
            "description": description or "",
            "created_by":  str(created_by) if created_by else "",
            "created_at":  created_at.isoformat() if created_at else "",
        },
        "member": {
            "user_id":         user_id,
            "username":        "",          # fetched from users table if needed
            "display_name":    display_name or "",
            "bio":             bio or "",
            "profile_pic_url": profile_pic_url or "",
            "role":            role,
            "subteam":         subteam or "",
            "joined_at":       joined_at.isoformat() if joined_at else "",
            "is_active":       True,
        },
    }


def _db_get_team_roster(team_code):
    """Return a list of member dicts for all active members of a team."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT m.user_id, u.username,
                   m.role, m.display_name, m.bio, m.profile_pic_url, m.subteam, m.joined_at
            FROM memberships m
            JOIN users u ON u.user_id = m.user_id
            WHERE m.team_code = %s AND m.is_active = TRUE
        """, (team_code,))
        rows = cur.fetchall()
    finally:
        cur.close()
        release_conn(conn)

    members = []
    for (uid, username, role, display_name, bio, profile_pic_url, subteam, joined_at) in rows:
        members.append({
            "user_id":         str(uid),
            "username":        username or "",
            "display_name":    display_name or "",
            "bio":             bio or "",
            "profile_pic_url": profile_pic_url or "",
            "role":            role,
            "subteam":         subteam or "",
            "joined_at":       joined_at.isoformat() if joined_at else "",
            "is_active":       True,
        })
    return members


def _db_active_member_count(team_code):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM memberships WHERE team_code=%s AND is_active=TRUE",
            (team_code,)
        )
        return cur.fetchone()[0]
    finally:
        cur.close()
        release_conn(conn)


def _db_cleanup_empty_teams():
    """Delete teams that have zero active members."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            DELETE FROM teams
            WHERE team_code NOT IN (
                SELECT DISTINCT team_code FROM memberships WHERE is_active = TRUE
            )
        """)
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


def _resolve_permissions(user_id):
    """Compute (role_str, permissions_list) from DB membership."""
    info = _db_get_user_membership(user_id)
    if info is None:
        return "viewer", list(GUEST_PERMISSIONS)
    role = info["member"]["role"]
    return role, list(ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS))


def requires_permission(perm_key):
    """Decorator: 403 if the calling user lacks perm_key."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            uid = _get_user_id()
            username = (request.json or {}).get("username")
            ensure_user(uid, username)
            if not uid:
                return jsonify({"detail": "X-User-Id header required"}), 401
            _, perms = _resolve_permissions(uid)
            if perm_key not in perms:
                return jsonify({"detail": f"Permission denied: requires '{perm_key}'"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ━━━━━━━━━━━━━━━━━ JSON SHAPE HELPERS ━━━━━━━━━━━━━━━━━━━━━━━━━

def _member_json(m):
    """Internal member dict -> JSON shape the Flutter client expects."""
    return {
        "id":             m.get("user_id", ""),
        "username":       m.get("username", ""),
        "displayName":    m.get("display_name", ""),
        "bio":            m.get("bio", ""),
        "profilePicUrl":  m.get("profile_pic_url", ""),
        "role":           m.get("role", "viewer"),
        "subteam":        m.get("subteam", ""),
        "joinedAt":       m.get("joined_at", ""),
        "isActive":       m.get("is_active", False),
    }


def _team_json(t):
    return {
        "team_code":   t["team_code"],
        "name":        t["name"],
        "team_number": t["team_number"],
        "description": t.get("description", ""),
    }


# ━━━━━━━━━━━━━━━━━ AUTH / SYNC ENDPOINT ━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/auth/sync', methods=['POST'])
@requires_auth
def auth_sync():
    """
    POST /api/auth/sync

    Primary sync endpoint.  Called by the Flutter app on every periodic
    sync and on startup.  Returns the caller's role, full permission set,
    team info, and complete active roster.

    Headers:   Authorization (Basic),   X-User-Id (device UUID)
    Body:      { "username": "..." }  (optional, kept in roster)

    200  { user_id, role, permissions[], team|null, roster[]|null }
    """
    uid = _get_user_id()
    body = request.json or {}
    username = body.get("username", "")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _db_cleanup_empty_teams()

    info = _db_get_user_membership(uid)
    role, permissions = _resolve_permissions(uid)

    resp = {
        "user_id":     uid,
        "role":        role,
        "permissions": permissions,
        "team":        None,
        "roster":      None,
    }

    if info is not None:
        team = info["team"]
        resp["team"] = _team_json(team)
        resp["roster"] = [_member_json(m) for m in _db_get_team_roster(team["team_code"])]

    return jsonify(resp)


# ━━━━━━━━━━━━━━━━━━ TEAM ENDPOINTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/teams/create', methods=['POST'])
@requires_auth
def create_team():
    """
    POST /api/teams/create

    Create a new team.  The caller's UUID (X-User-Id) becomes the owner.

    Body:  { name, team_number, username, display_name? }
    201   { success, team{}, role, permissions[] }
    """
    uid = _get_user_id()
    body = request.json or {}
    username = body.get("username", "")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    # Must not already be on a team
    if _db_get_user_membership(uid) is not None:
        return jsonify({"detail": "Already on a team. Leave first."}), 409

    name = body.get("name", "").strip()
    team_number = body.get("team_number", "").strip()
    display_name = body.get("display_name", "").strip() or username.strip()

    if not name:
        return jsonify({"detail": "Team name is required"}), 400

    code = _generate_join_code()

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO teams (team_code, name, team_number, created_by)
            VALUES (%s, %s, %s, %s)
        """, (code, name, team_number, uid))

        cur.execute("""
            INSERT INTO memberships (user_id, team_code, role, display_name)
            VALUES (%s, %s, 'owner', %s)
        """, (uid, code, display_name))

        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    info = _db_get_user_membership(uid)
    role, permissions = _resolve_permissions(uid)

    return jsonify({
        "success":     True,
        "team":        _team_json(info["team"]),
        "role":        role,
        "permissions": permissions,
    }), 201


@permissions_roster.route('/teams/join', methods=['POST'])
@requires_auth
def join_team():
    """
    POST /api/teams/join

    Join an existing team via its 6-char join code.  The caller's UUID
    (X-User-Id) is added as a scout.  If they previously left, they are
    reactivated with their old role.

    Body:  { team_code, username, display_name? }
    200   { success, team{}, role, permissions[] }
    """
    uid = _get_user_id()
    body = request.json or {}
    username = body.get("username", "")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    # Must not already be on a team
    if _db_get_user_membership(uid) is not None:
        return jsonify({"detail": "Already on a team. Leave first."}), 409

    code = body.get("team_code", "").strip().upper()
    display_name = body.get("display_name", "").strip() or username.strip()

    if not code:
        return jsonify({"detail": "Team code is required"}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Verify team exists
        cur.execute("SELECT team_code FROM teams WHERE team_code=%s", (code,))
        if cur.fetchone() is None:
            return jsonify({"detail": "Invalid team code"}), 404

        # Upsert membership: reactivate if previously left, otherwise insert as scout
        cur.execute("""
            INSERT INTO memberships (user_id, team_code, role, display_name, is_active)
            VALUES (%s, %s, 'scout', %s, TRUE)
            ON CONFLICT (user_id)
            DO UPDATE SET
                team_code    = EXCLUDED.team_code,
                is_active    = TRUE,
                display_name = COALESCE(EXCLUDED.display_name, memberships.display_name)
        """, (uid, code, display_name))

        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    info = _db_get_user_membership(uid)
    role, permissions = _resolve_permissions(uid)

    return jsonify({
        "success":     True,
        "team":        _team_json(info["team"]),
        "role":        role,
        "permissions": permissions,
    })


@permissions_roster.route('/teams/leave', methods=['POST'])
@requires_auth
def leave_team():
    """
    POST /api/teams/leave

    Leave the current team.  Member is marked inactive (history preserved).
    If zero active members remain, the team is automatically deleted.

    200  { success, message, role, permissions[] }
    """
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_name = info["team"]["name"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE memberships SET is_active=FALSE WHERE user_id=%s",
            (uid,)
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    _db_cleanup_empty_teams()

    return jsonify({
        "success":     True,
        "message":     f"Left team {team_name}",
        "role":        "viewer",
        "permissions": list(GUEST_PERMISSIONS),
    })


@permissions_roster.route('/teams/info', methods=['GET'])
@requires_auth
def team_info():
    """GET /api/teams/info"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team = info["team"]
    return jsonify({
        **_team_json(team),
        "created_at":   team["created_at"],
        "member_count": _db_active_member_count(team["team_code"]),
    })


@permissions_roster.route('/teams/update', methods=['PUT'])
@requires_auth
@requires_permission("edit_team_settings")
def update_team():
    """PUT /api/teams/update"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    body = request.json or {}
    team_code = info["team"]["team_code"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        if "name" in body:
            cur.execute("UPDATE teams SET name=%s WHERE team_code=%s", (body["name"], team_code))
        if "team_number" in body:
            cur.execute("UPDATE teams SET team_number=%s WHERE team_code=%s", (body["team_number"], team_code))
        if "description" in body:
            cur.execute("UPDATE teams SET description=%s WHERE team_code=%s", (body["description"], team_code))
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    updated = _db_get_user_membership(uid)
    return jsonify({"success": True, "team": _team_json(updated["team"])})


# ━━━━━━━━━━━━━━━━━━ ROSTER ENDPOINTS ━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/roster', methods=['GET'])
@requires_auth
@requires_permission("view_roster")
def get_roster():
    """GET /api/roster"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    members = _db_get_team_roster(info["team"]["team_code"])
    members.sort(key=lambda x: (
        -ROLES.get(x["role"], {}).get("level", 0),
        x.get("display_name", ""),
    ))
    return jsonify({"count": len(members), "members": [_member_json(m) for m in members]})


@permissions_roster.route('/roster/me', methods=['GET'])
@requires_auth
def get_own_profile():
    """GET /api/roster/me"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    return jsonify(_member_json(info["member"]))


@permissions_roster.route('/roster/me', methods=['PUT'])
@requires_auth
def update_own_profile():
    """PUT /api/roster/me"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    body = request.json or {}
    _db_apply_profile_fields(uid, body)

    updated = _db_get_user_membership(uid)
    return jsonify({"success": True, "member": _member_json(updated["member"])})


@permissions_roster.route('/roster/register', methods=['POST'])
@requires_auth
def register_profile():
    """POST /api/roster/register  (Flutter push-queue compat)"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        # Not on a team: accept silently so the push queue drains
        return jsonify({"success": True, "member": None}), 200

    body = request.json or {}
    _db_apply_profile_fields(uid, body)

    updated = _db_get_user_membership(uid)
    return jsonify({"success": True, "member": _member_json(updated["member"])}), 201


def _db_apply_profile_fields(user_id, body):
    """Write profile fields from request body into the memberships table."""
    mapping = {
        "display_name": "display_name", "displayName": "display_name",
        "bio": "bio", "subteam": "subteam",
        "profile_pic_url": "profile_pic_url", "profilePicUrl": "profile_pic_url",
    }
    updates = {}
    for req_key, col in mapping.items():
        if req_key in body:
            updates[col] = body[req_key]

    if not updates:
        return

    conn = get_conn()
    cur = conn.cursor()
    try:
        set_clause = ", ".join(f"{col}=%s" for col in updates)
        values = list(updates.values()) + [user_id]
        cur.execute(
            f"UPDATE memberships SET {set_clause} WHERE user_id=%s",
            values
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


@permissions_roster.route('/roster/<target_id>/role', methods=['PUT'])
@requires_auth
@requires_permission("manage_roles")
def update_member_role(target_id):
    """PUT /api/roster/{uuid}/role"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    caller_info = _db_get_user_membership(uid)
    if caller_info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = caller_info["team"]["team_code"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role FROM memberships WHERE user_id=%s AND team_code=%s AND is_active=TRUE",
            (target_id, team_code)
        )
        row = cur.fetchone()
    finally:
        cur.close()
        release_conn(conn)

    if row is None:
        return jsonify({"detail": "Member not found"}), 404

    current_target_role = row[0]
    body = request.json or {}
    new_role = body.get("role", "")

    if new_role not in ROLES:
        return jsonify({"detail": f"Invalid role. Valid: {list(ROLES.keys())}"}), 400

    caller_level = ROLES.get(caller_info["member"]["role"], {}).get("level", 0)
    if ROLES[new_role]["level"] > caller_level:
        return jsonify({"detail": "Cannot assign a role higher than your own"}), 403
    if current_target_role == "owner" and caller_info["member"]["role"] != "owner":
        return jsonify({"detail": "Cannot demote the team owner"}), 403

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE memberships SET role=%s WHERE user_id=%s AND team_code=%s",
            (new_role, target_id, team_code)
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    return jsonify({
        "success":     True,
        "user_id":     target_id,
        "role":        new_role,
        "permissions": ROLE_PERMISSIONS.get(new_role, GUEST_PERMISSIONS),
    })


@permissions_roster.route('/roster/<target_id>', methods=['DELETE'])
@requires_auth
@requires_permission("manage_roster")
def remove_member(target_id):
    """DELETE /api/roster/{uuid}"""
    uid = _get_user_id()
    username = (request.json or {}).get("username")
    ensure_user(uid, username)
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = info["team"]["team_code"]

    if target_id == uid:
        return jsonify({"detail": "Use /teams/leave to remove yourself"}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role FROM memberships WHERE user_id=%s AND team_code=%s AND is_active=TRUE",
            (target_id, team_code)
        )
        row = cur.fetchone()
        if row is None:
            return jsonify({"detail": "Member not found"}), 404
        if row[0] == "owner":
            return jsonify({"detail": "Cannot remove the team owner"}), 403

        cur.execute(
            "UPDATE memberships SET is_active=FALSE WHERE user_id=%s",
            (target_id,)
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    _db_cleanup_empty_teams()
    return jsonify({"success": True, "message": "Member removed"})


# ━━━━━━━━━━━━━━━ PERMISSION QUERY ENDPOINTS ━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/permissions/roles', methods=['GET'])
@requires_auth
def get_roles():
    """GET /api/permissions/roles"""
    return jsonify({
        "roles": [
            {
                "id": rid, "level": rd["level"], "name": rd["name"],
                "description": rd["description"],
                "permissions": ROLE_PERMISSIONS.get(rid, []),
            }
            for rid, rd in sorted(ROLES.items(), key=lambda x: x[1]["level"])
        ]
    })


@permissions_roster.route('/permissions/guest', methods=['GET'])
def get_guest_permissions():
    """GET /api/permissions/guest (no auth needed)"""
    return jsonify({"role": "viewer", "permissions": GUEST_PERMISSIONS})


# ━━━━━━━━━━━━━━━━━━━ ADMIN ENDPOINTS ━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/admin/stats', methods=['GET'])
@requires_auth
@requires_permission("view_admin")
def admin_stats():
    """GET /api/admin/stats"""
    _db_cleanup_empty_teams()

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(DISTINCT team_code) FROM memberships WHERE is_active=TRUE")
        team_count = cur.fetchone()[0]

        cur.execute("SELECT role, COUNT(*) FROM memberships WHERE is_active=TRUE GROUP BY role")
        by_role = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) FROM memberships WHERE is_active=TRUE")
        total = cur.fetchone()[0]
    finally:
        cur.close()
        release_conn(conn)

    return jsonify({
        "teams":         team_count,
        "total_members": total,
        "by_role":       by_role,
        "timestamp":     datetime.now().isoformat(),
    })