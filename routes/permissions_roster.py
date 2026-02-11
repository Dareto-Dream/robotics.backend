"""
permissions_roster.py — Server-authoritative team, permission, & roster system

Identity model:
  - Authorization: Bearer <JWT>  →  user authentication via JWT tokens
  - User identity derived from JWT payload (user_id)

Data model:
  - Teams are the organisational unit. Each has a unique 6-char join code.
  - Members belong to exactly one team. Membership is keyed by the user's UUID.
  - Roles are assigned per-member. Permissions are computed from the role on the server
    and returned to the client. The client NEVER computes permissions locally.

Lifecycle:
  1. User registers/logs in via /auth/register or /auth/login → receives JWT tokens
  2. Creator calls POST /api/teams/create  → server generates join code, adds creator as owner.
  3. Others call   POST /api/teams/join    → server validates code, adds member as scout.
  4. Member calls  POST /api/teams/leave   → server marks them inactive, cleans up empty teams.
  5. Every sync    GET /api/auth/sync      → server returns role + permissions + team + roster.
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from datetime import datetime

from auth.dependencies import require_auth
from data.users_repo import ensure_user
from data.db import get_conn, release_conn
import secrets


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
            SELECT m.user_id,
                   m.role, m.display_name, m.bio, m.profile_pic_url, m.subteam, m.joined_at
            FROM memberships m
            WHERE m.team_code = %s AND m.is_active = TRUE
        """, (team_code,))
        rows = cur.fetchall()
    finally:
        cur.close()
        release_conn(conn)

    members = []
    for row in rows:
        user_id, role, display_name, bio, profile_pic_url, subteam, joined_at = row
        members.append({
            "user_id":         str(user_id),
            "display_name":    display_name or "",
            "bio":             bio or "",
            "profile_pic_url": profile_pic_url or "",
            "role":            role,
            "subteam":         subteam or "",
            "joined_at":       joined_at.isoformat() if joined_at else "",
            "is_active":       True,
        })
    return members


def _db_cleanup_empty_teams():
    """Remove teams that have no active members."""
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


# ━━━━━━━━━━━━━━━━━━ PERMISSION HELPERS ━━━━━━━━━━━━━━━━━━━━━━━

def requires_permission(permission_name):
    """Decorator to check if the authenticated user has a specific permission."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, current_user=None, **kwargs):
            if current_user is None:
                return jsonify({"detail": "Authentication required"}), 401

            user_id = current_user["id"]
            info = _db_get_user_membership(user_id)
            
            if info is None:
                return jsonify({"detail": "Not on a team"}), 403

            role = info["member"]["role"]
            permissions = ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS)
            
            if permission_name not in permissions:
                return jsonify({"detail": f"Permission denied: {permission_name} required"}), 403

            return f(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator


# ━━━━━━━━━━━━━━━━━━ SERIALIZATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _member_json(member):
    """Serialize member dict for API responses."""
    return {
        "user_id":         member["user_id"],
        "display_name":    member["display_name"],
        "bio":             member["bio"],
        "profile_pic_url": member["profile_pic_url"],
        "role":            member["role"],
        "subteam":         member["subteam"],
        "joined_at":       member["joined_at"],
    }


def _team_json(team):
    """Serialize team dict for API responses."""
    return {
        "team_code":   team["team_code"],
        "name":        team["name"],
        "team_number": team["team_number"],
        "description": team["description"],
        "created_by":  team["created_by"],
        "created_at":  team["created_at"],
    }


# ━━━━━━━━━━━━━━━━━━ AUTH & SYNC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/auth/sync', methods=['GET'])
@require_auth
def auth_sync(current_user):
    """
    GET /api/auth/sync
    
    The primary identity endpoint. Returns the user's team, role, permissions,
    and roster if they're on a team. Returns guest permissions if not.
    """
    uid = current_user["id"]
    email = current_user["email"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    
    if info is None:
        return jsonify({
            "user": {"id": uid, "email": email},
            "team": None,
            "member": None,
            "role": "viewer",
            "permissions": GUEST_PERMISSIONS,
            "roster": [],
        })

    team_code = info["team"]["team_code"]
    role = info["member"]["role"]
    permissions = ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS)
    roster = _db_get_team_roster(team_code)

    return jsonify({
        "user": {"id": uid, "email": email},
        "team": _team_json(info["team"]),
        "member": _member_json(info["member"]),
        "role": role,
        "permissions": permissions,
        "roster": [_member_json(m) for m in roster],
    })


# ━━━━━━━━━━━━━━━━━━ TEAM MANAGEMENT ━━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/teams/create', methods=['POST'])
@require_auth
def create_team(current_user):
    """POST /api/teams/create"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is not None:
        return jsonify({"detail": "Already on a team. Leave current team first."}), 400

    body = request.json or {}
    name = body.get("name", "").strip()
    team_number = body.get("team_number", "").strip()
    display_name = body.get("display_name", "").strip()

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

    updated = _db_get_user_membership(uid)
    return jsonify({
        "success": True,
        "team": _team_json(updated["team"]),
        "member": _member_json(updated["member"]),
        "role": "owner",
        "permissions": ROLE_PERMISSIONS["owner"],
    }), 201


@permissions_roster.route('/teams/join', methods=['POST'])
@require_auth
def join_team(current_user):
    """POST /api/teams/join"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is not None:
        return jsonify({"detail": "Already on a team. Leave current team first."}), 400

    body = request.json or {}
    join_code = body.get("join_code", "").strip().upper()
    display_name = body.get("display_name", "").strip()

    if not join_code or len(join_code) != 6:
        return jsonify({"detail": "Valid 6-character join code required"}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM teams WHERE team_code = %s", (join_code,))
        if cur.fetchone() is None:
            return jsonify({"detail": "Invalid join code"}), 404

        cur.execute("""
            INSERT INTO memberships (user_id, team_code, role, display_name)
            VALUES (%s, %s, 'scout', %s)
        """, (uid, join_code, display_name))

        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    updated = _db_get_user_membership(uid)
    return jsonify({
        "success": True,
        "team": _team_json(updated["team"]),
        "member": _member_json(updated["member"]),
        "role": "scout",
        "permissions": ROLE_PERMISSIONS["scout"],
    }), 201


@permissions_roster.route('/teams/leave', methods=['POST'])
@require_auth
def leave_team(current_user):
    """POST /api/teams/leave"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE memberships
            SET is_active = FALSE
            WHERE user_id = %s
        """, (uid,))
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    _db_cleanup_empty_teams()
    return jsonify({"success": True, "message": "Left team"})


@permissions_roster.route('/teams/info', methods=['GET'])
@require_auth
@requires_permission("view_roster")
def get_team_info(current_user):
    """GET /api/teams/info"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    return jsonify({
        "team": _team_json(info["team"]),
        "member": _member_json(info["member"]),
    })


@permissions_roster.route('/teams/settings', methods=['PUT'])
@require_auth
@requires_permission("edit_team_settings")
def update_team_settings(current_user):
    """PUT /api/teams/settings"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = info["team"]["team_code"]
    body = request.json or {}

    updates = {}
    if "name" in body:
        updates["name"] = body["name"].strip()
    if "team_number" in body:
        updates["team_number"] = body["team_number"].strip()
    if "description" in body:
        updates["description"] = body["description"].strip()

    if not updates:
        return jsonify({"detail": "No fields to update"}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        set_clause = ", ".join(f"{col}=%s" for col in updates)
        values = list(updates.values()) + [team_code]
        cur.execute(
            f"UPDATE teams SET {set_clause} WHERE team_code=%s",
            values
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    updated = _db_get_user_membership(uid)
    return jsonify({
        "success": True,
        "team": _team_json(updated["team"]),
    })


# ━━━━━━━━━━━━━━━━━━ ROSTER MANAGEMENT ━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/roster', methods=['GET'])
@require_auth
@requires_permission("view_roster")
def get_roster(current_user):
    """GET /api/roster"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = info["team"]["team_code"]
    roster = _db_get_team_roster(team_code)
    
    return jsonify({
        "roster": [_member_json(m) for m in roster],
        "count": len(roster),
    })


@permissions_roster.route('/roster/profile', methods=['PUT'])
@require_auth
def update_profile(current_user):
    """PUT /api/roster/profile"""
    uid = current_user["id"]
    ensure_user(uid)
    
    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    body = request.json or {}
    _db_apply_profile_fields(uid, body)

    updated = _db_get_user_membership(uid)
    return jsonify({
        "success": True,
        "member": _member_json(updated["member"]),
    })


def _db_apply_profile_fields(user_id, body):
    """Write profile fields from request body into the memberships table."""
    mapping = {
        "display_name": "display_name",
        "displayName": "display_name",
        "bio": "bio",
        "subteam": "subteam",
        "profile_pic_url": "profile_pic_url",
        "profilePicUrl": "profile_pic_url",
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
@require_auth
@requires_permission("manage_roles")
def update_member_role(current_user, target_id):
    """PUT /api/roster/{uuid}/role"""
    uid = current_user["id"]
    ensure_user(uid)
    
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
@require_auth
@requires_permission("manage_roster")
def remove_member(current_user, target_id):
    """DELETE /api/roster/{uuid}"""
    uid = current_user["id"]
    ensure_user(uid)
    
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
def get_roles():
    """GET /api/permissions/roles (no auth required)"""
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
@require_auth
@requires_permission("view_admin")
def admin_stats(current_user):
    """GET /api/admin/stats"""
    ensure_user(current_user["id"])
    
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
