"""
permissions_roster.py — Server-authoritative team, permission, & roster system

Key behavioral changes from v1:
  - is_active is COSMETIC ONLY (shows who is currently using the app).
    Membership is determined by whether a row exists in the memberships table.
  - Leaving a team DELETES the membership row.
  - A team is deleted ONLY when the owner leaves.
    When deleted, all member rows for that team are removed.
  - Ownership can be transferred via POST /api/teams/transfer.
  - The owner cannot leave without first transferring ownership or
    being the last member.
"""

from flask import Blueprint, request, jsonify
from functools import wraps
from datetime import datetime

from auth.dependencies import require_auth
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
        "select_event", "sync_data", "edit_modules", "transfer_ownership",
    ],
}

GUEST_PERMISSIONS = [
    "view_dashboard", "view_manual", "view_settings", "edit_own_profile",
]


# ━━━━━━━━━━━━━━━━━━ DATABASE HELPERS ━━━━━━━━━━━━━━━━━━━━━━━━━━

_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _generate_join_code():
    """Create a unique 6-char code."""
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
    Return a dict with team + member info, or None.
    Membership is determined by row existence (NOT is_active).
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT t.team_code, t.name, t.team_number, t.description,
                   t.created_by, t.created_at,
                   m.role, m.display_name, m.bio, m.profile_pic_url,
                   m.subteam, m.joined_at, m.is_active
            FROM memberships m
            JOIN teams t ON t.team_code = m.team_code
            WHERE m.user_id = %s
        """, (user_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        release_conn(conn)

    if row is None:
        return None

    (team_code, name, team_number, description,
     created_by, created_at,
     role, display_name, bio, profile_pic_url, subteam, joined_at, is_active) = row

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
            "is_active":       is_active,
        },
    }


def _db_get_team_roster(team_code):
    """Return a list of member dicts for all members of a team."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT m.user_id,
                   m.role, m.display_name, m.bio, m.profile_pic_url,
                   m.subteam, m.joined_at, m.is_active
            FROM memberships m
            WHERE m.team_code = %s
            ORDER BY m.joined_at ASC
        """, (team_code,))
        rows = cur.fetchall()
    finally:
        cur.close()
        release_conn(conn)

    members = []
    for row in rows:
        user_id, role, display_name, bio, profile_pic_url, subteam, joined_at, is_active = row
        members.append({
            "user_id":         str(user_id),
            "display_name":    display_name or "",
            "bio":             bio or "",
            "profile_pic_url": profile_pic_url or "",
            "role":            role,
            "subteam":         subteam or "",
            "joined_at":       joined_at.isoformat() if joined_at else "",
            "is_active":       is_active,
        })
    return members


def _db_delete_team(team_code):
    """
    Delete a team and ALL its memberships.
    Called only when the owner leaves.
    """
    conn = get_conn()
    cur = conn.cursor()
    try:
        # Delete all memberships first (FK constraint)
        cur.execute("DELETE FROM memberships WHERE team_code = %s", (team_code,))
        # Delete the team
        cur.execute("DELETE FROM teams WHERE team_code = %s", (team_code,))
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)


def _db_count_team_members(team_code):
    """Return count of members on a team."""
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM memberships WHERE team_code = %s", (team_code,))
        return cur.fetchone()[0]
    finally:
        cur.close()
        release_conn(conn)


# ━━━━━━━━━━━━━━━━━━ PERMISSION HELPERS ━━━━━━━━━━━━━━━━━━━━━━━

def requires_permission(permission_name):
    """Decorator: check if the authenticated user has a specific permission."""
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
    return {
        "user_id":         member["user_id"],
        "display_name":    member["display_name"],
        "bio":             member["bio"],
        "profile_pic_url": member["profile_pic_url"],
        "role":            member["role"],
        "subteam":         member["subteam"],
        "joined_at":       member["joined_at"],
        "is_active":       member["is_active"],
    }


def _team_json(team):
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

    Primary identity endpoint. Returns user's team, role, permissions, roster.
    Also sets is_active = TRUE for the calling user (they are using the app).
    """
    uid = current_user["id"]
    email = current_user["email"]

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

    # Mark user as active (cosmetic — they are using the app right now)
    team_code = info["team"]["team_code"]
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE memberships SET is_active = TRUE WHERE user_id = %s AND team_code = %s",
            (uid, team_code),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    role = info["member"]["role"]
    permissions = ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS)
    roster = _db_get_team_roster(team_code)

    # Refresh info after is_active update
    info = _db_get_user_membership(uid)

    return jsonify({
        "user": {"id": uid, "email": email},
        "team": _team_json(info["team"]),
        "member": _member_json(info["member"]),
        "role": role,
        "permissions": permissions,
        "roster": [_member_json(m) for m in roster],
    })


# ━━━━━━━━━━━━━━━━━━ ACTIVITY STATUS ━━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/status/active', methods=['POST'])
@require_auth
def set_active(current_user):
    """
    POST /api/status/active

    Set the current user's is_active flag. This is cosmetic only —
    it indicates whether the user is currently using the app.

    Required: { "is_active": true/false }
    """
    uid = current_user["id"]

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    body = request.get_json(silent=True) or {}
    is_active = body.get("is_active")

    if is_active is None or not isinstance(is_active, bool):
        return jsonify({"detail": "is_active (boolean) is required"}), 400

    team_code = info["team"]["team_code"]
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE memberships SET is_active = %s WHERE user_id = %s AND team_code = %s",
            (is_active, uid, team_code),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    return jsonify({"success": True, "is_active": is_active})


# ━━━━━━━━━━━━━━━━━━ TEAM MANAGEMENT ━━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/teams/create', methods=['POST'])
@require_auth
def create_team(current_user):
    """POST /api/teams/create"""
    uid = current_user["id"]

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
            INSERT INTO memberships (user_id, team_code, role, display_name, is_active)
            VALUES (%s, %s, 'owner', %s, TRUE)
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
            INSERT INTO memberships (user_id, team_code, role, display_name, is_active)
            VALUES (%s, %s, 'scout', %s, TRUE)
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
    """
    POST /api/teams/leave

    Leave the current team. Deletes the membership row.

    If the caller is the owner:
      - If they are the ONLY member, the team is deleted.
      - If other members exist, they must first transfer ownership
        via POST /api/teams/transfer.
    """
    uid = current_user["id"]

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = info["team"]["team_code"]
    role = info["member"]["role"]

    if role == "owner":
        member_count = _db_count_team_members(team_code)

        if member_count > 1:
            return jsonify({
                "detail": "You are the owner. Transfer ownership before leaving, "
                          "or remove all other members first.",
                "hint": "POST /api/teams/transfer"
            }), 400

        # Owner is the only member — delete the team entirely
        _db_delete_team(team_code)
        return jsonify({
            "success": True,
            "message": "Team deleted (you were the last member)",
        })

    # Non-owner: just delete their membership row
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM memberships WHERE user_id = %s AND team_code = %s", (uid, team_code))
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    return jsonify({"success": True, "message": "Left team"})


@permissions_roster.route('/teams/transfer', methods=['POST'])
@require_auth
def transfer_ownership(current_user):
    """
    POST /api/teams/transfer

    Transfer team ownership to another member.
    Only the current owner can do this. The caller is demoted to admin.

    Required: { "target_user_id": "<uuid>" }
    """
    uid = current_user["id"]

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    if info["member"]["role"] != "owner":
        return jsonify({"detail": "Only the owner can transfer ownership"}), 403

    body = request.json or {}
    target_id = body.get("target_user_id", "").strip()

    if not target_id:
        return jsonify({"detail": "target_user_id is required"}), 400

    if target_id == uid:
        return jsonify({"detail": "You are already the owner"}), 400

    team_code = info["team"]["team_code"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        # Verify target is on the same team
        cur.execute(
            "SELECT 1 FROM memberships WHERE user_id = %s AND team_code = %s",
            (target_id, team_code),
        )
        if not cur.fetchone():
            return jsonify({"detail": "Target user is not on this team"}), 404

        # Promote target to owner
        cur.execute(
            "UPDATE memberships SET role = 'owner' WHERE user_id = %s AND team_code = %s",
            (target_id, team_code),
        )
        # Demote caller to admin
        cur.execute(
            "UPDATE memberships SET role = 'admin' WHERE user_id = %s AND team_code = %s",
            (uid, team_code),
        )
        # Update teams.created_by to new owner
        cur.execute(
            "UPDATE teams SET created_by = %s WHERE team_code = %s",
            (target_id, team_code),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    return jsonify({
        "success": True,
        "message": f"Ownership transferred to {target_id}",
        "new_owner": target_id,
        "your_new_role": "admin",
    })


@permissions_roster.route('/teams/info', methods=['GET'])
@require_auth
@requires_permission("view_roster")
def get_team_info(current_user):
    """GET /api/teams/info"""
    uid = current_user["id"]

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

    caller_info = _db_get_user_membership(uid)
    if caller_info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = caller_info["team"]["team_code"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role FROM memberships WHERE user_id=%s AND team_code=%s",
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

    if new_role == "owner":
        return jsonify({"detail": "Use POST /api/teams/transfer to assign ownership"}), 400

    caller_level = ROLES.get(caller_info["member"]["role"], {}).get("level", 0)
    if ROLES[new_role]["level"] > caller_level:
        return jsonify({"detail": "Cannot assign a role higher than your own"}), 403
    if current_target_role == "owner":
        return jsonify({"detail": "Cannot demote the team owner. Transfer ownership first."}), 403

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

    info = _db_get_user_membership(uid)
    if info is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_code = info["team"]["team_code"]

    if target_id == uid:
        return jsonify({"detail": "Use POST /api/teams/leave to remove yourself"}), 400

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT role FROM memberships WHERE user_id=%s AND team_code=%s",
            (target_id, team_code)
        )
        row = cur.fetchone()
        if row is None:
            return jsonify({"detail": "Member not found"}), 404
        if row[0] == "owner":
            return jsonify({"detail": "Cannot remove the team owner"}), 403

        # Hard-delete the membership row
        cur.execute(
            "DELETE FROM memberships WHERE user_id=%s AND team_code=%s",
            (target_id, team_code)
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

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

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(DISTINCT team_code) FROM memberships")
        team_count = cur.fetchone()[0]

        cur.execute("SELECT role, COUNT(*) FROM memberships GROUP BY role")
        by_role = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("SELECT COUNT(*) FROM memberships")
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
