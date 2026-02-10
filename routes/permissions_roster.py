"""
permissions_roster.py — Server-authoritative permission & roster system

Architecture:
  - Basic Auth (Authorization header) = shared backend credential, one per deployment
  - X-User-Id header = per-device user identity (UUID generated on first launch)
  - Teams are the organizational unit; each has a 6-char join code
  - Roles are assigned per-member within a team
  - Permissions are computed server-side from role and returned to the client
  - The client NEVER computes its own permissions; it caches what the server sends
"""

from flask import Blueprint, request, jsonify, abort
from functools import wraps
from datetime import datetime
import secrets
import uuid
from helpers import USERNAME, PASSWORD

permissions_roster = Blueprint('permissions_roster', __name__)

# ==================== ROLE & PERMISSION DEFINITIONS ====================

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


# ==================== IN-MEMORY STORAGE ====================
# Replace with a real database in production.
#
# teams[team_code] = {
#     team_code, name, team_number, description, created_by, created_at,
#     members: { user_id: { user_id, username, display_name, bio,
#         profile_pic_url, role, subteam, joined_at, is_active } }
# }
teams = {}

# user_team_map[user_id] = team_code  (quick reverse lookup)
user_team_map = {}


# ==================== AUTH HELPERS ====================

def check_auth(username, password):
    """Validate the shared backend credential."""
    return (secrets.compare_digest(username, USERNAME)
            and secrets.compare_digest(password, PASSWORD))


def requires_auth(f):
    """Require the shared Basic Auth credential on the request."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"detail": "Invalid credentials"}), 401, {
                "WWW-Authenticate": 'Basic realm="Login Required"'
            }
        return f(*args, **kwargs)
    return decorated


def get_user_id():
    """Extract per-user identity from the X-User-Id header."""
    return request.headers.get("X-User-Id", "").strip() or None


def get_user_team(user_id):
    """Return (team_code, team_dict, member_dict) or (None, None, None)."""
    team_code = user_team_map.get(user_id)
    if not team_code or team_code not in teams:
        return None, None, None
    team = teams[team_code]
    member = team["members"].get(user_id)
    return team_code, team, member


def resolve_permissions(user_id):
    """Return (role_str, permissions_list) for a user based on team membership."""
    _, _, member = get_user_team(user_id)
    if member is None or not member.get("is_active", True):
        return "viewer", list(GUEST_PERMISSIONS)
    role = member.get("role", "viewer")
    return role, list(ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS))


def requires_permission(perm_key):
    """Decorator: reject the request if the user lacks a specific permission."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_id = get_user_id()
            if not user_id:
                return jsonify({"detail": "X-User-Id header required"}), 401
            _, perms = resolve_permissions(user_id)
            if perm_key not in perms:
                return jsonify({
                    "detail": f"Permission denied: requires '{perm_key}'",
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def _generate_join_code():
    """Generate a 6-character alphanumeric join code (no ambiguous chars)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(6))


def _member_to_json(member):
    """Convert internal member dict to the JSON shape the Flutter client expects."""
    role = member.get("role", "viewer")
    return {
        "id": member.get("user_id", ""),
        "username": member.get("username", ""),
        "displayName": member.get("display_name", ""),
        "bio": member.get("bio", ""),
        "profilePicUrl": member.get("profile_pic_url", ""),
        "role": role,
        "subteam": member.get("subteam", ""),
        "joinedAt": member.get("joined_at", ""),
        "isActive": member.get("is_active", True),
    }


def _team_to_json(team):
    """Convert internal team dict to the JSON shape the Flutter client expects."""
    return {
        "team_code": team["team_code"],
        "name": team["name"],
        "team_number": team["team_number"],
        "description": team.get("description", ""),
    }


# ==================== AUTH / SYNC ENDPOINT ====================

@permissions_roster.route('/auth/sync', methods=['POST'])
@requires_auth
def auth_sync():
    """
    POST /api/auth/sync
    Primary sync endpoint. Called by the Flutter app on every sync cycle.
    Returns the user's current role, permission set, team info, and roster.

    Headers:
        Authorization: Basic <credential>
        X-User-Id: <device UUID>

    Body (optional): { "username": "string" }

    Response 200: {
        "user_id", "role", "permissions": [...],
        "team": { team_code, name, team_number, description } | null,
        "roster": [ { member }, ... ] | null
    }
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    body = request.json or {}
    username = body.get("username", "")

    # Update username in roster if the user is on a team
    _, team, member = get_user_team(user_id)
    if member is not None and username:
        member["username"] = username

    role, permissions = resolve_permissions(user_id)

    resp = {
        "user_id": user_id,
        "role": role,
        "permissions": permissions,
        "team": None,
        "roster": None,
    }

    if team is not None:
        resp["team"] = _team_to_json(team)
        resp["roster"] = [
            _member_to_json(m) for m in team["members"].values()
            if m.get("is_active", True)
        ]

    return jsonify(resp)


# ==================== TEAM ENDPOINTS ====================

@permissions_roster.route('/teams/create', methods=['POST'])
@requires_auth
def create_team():
    """
    POST /api/teams/create
    Create a new team. The creator becomes the owner.

    Body: { "name", "team_number", "username", "display_name"? }
    Response 201: { success, team: {...}, role, permissions: [...] }
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    body = request.json or {}
    name = body.get("name", "").strip()
    team_number = body.get("team_number", "").strip()
    username = body.get("username", "").strip()
    display_name = body.get("display_name", "").strip() or username

    if not name:
        return jsonify({"detail": "Team name is required"}), 400

    if user_id in user_team_map:
        return jsonify({"detail": "Already on a team. Leave current team first."}), 409

    join_code = _generate_join_code()
    while join_code in teams:
        join_code = _generate_join_code()

    now = datetime.now().isoformat()

    team = {
        "team_code": join_code,
        "name": name,
        "team_number": team_number,
        "description": "",
        "created_by": user_id,
        "created_at": now,
        "members": {
            user_id: {
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "bio": "",
                "profile_pic_url": "",
                "role": "owner",
                "subteam": "",
                "joined_at": now,
                "is_active": True,
            }
        },
    }

    teams[join_code] = team
    user_team_map[user_id] = join_code

    role, permissions = resolve_permissions(user_id)

    return jsonify({
        "success": True,
        "team": _team_to_json(team),
        "role": role,
        "permissions": permissions,
    }), 201


@permissions_roster.route('/teams/join', methods=['POST'])
@requires_auth
def join_team():
    """
    POST /api/teams/join
    Join an existing team via 6-character join code. New members get 'scout'.
    If the user was previously a member, they are reactivated with their old role.

    Body: { "team_code", "username", "display_name"? }
    Response 200: { success, team: {...}, role, permissions: [...] }
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    body = request.json or {}
    team_code = body.get("team_code", "").strip().upper()
    username = body.get("username", "").strip()
    display_name = body.get("display_name", "").strip() or username

    if not team_code:
        return jsonify({"detail": "Team code is required"}), 400

    if team_code not in teams:
        return jsonify({"detail": "Invalid team code"}), 404

    if user_id in user_team_map:
        return jsonify({"detail": "Already on a team. Leave current team first."}), 409

    team = teams[team_code]
    now = datetime.now().isoformat()

    # Rejoin: reactivate if user was previously a member
    if user_id in team["members"]:
        existing = team["members"][user_id]
        existing["is_active"] = True
        if username:
            existing["username"] = username
        if display_name:
            existing["display_name"] = display_name
    else:
        team["members"][user_id] = {
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
            "bio": "",
            "profile_pic_url": "",
            "role": "scout",
            "subteam": "",
            "joined_at": now,
            "is_active": True,
        }

    user_team_map[user_id] = team_code

    role, permissions = resolve_permissions(user_id)

    return jsonify({
        "success": True,
        "team": _team_to_json(team),
        "role": role,
        "permissions": permissions,
    })


@permissions_roster.route('/teams/leave', methods=['POST'])
@requires_auth
def leave_team():
    """
    POST /api/teams/leave
    Leave the current team. Member is marked inactive (preserves history).
    Returns guest permissions.

    Response 200: { success, message, role: "viewer", permissions: [guest] }
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, member = get_user_team(user_id)
    if team is None or member is None:
        return jsonify({"detail": "Not on a team"}), 404

    member["is_active"] = False
    user_team_map.pop(user_id, None)

    return jsonify({
        "success": True,
        "message": f"Left team {team['name']}",
        "role": "viewer",
        "permissions": list(GUEST_PERMISSIONS),
    })


@permissions_roster.route('/teams/info', methods=['GET'])
@requires_auth
def get_team_info():
    """GET /api/teams/info — info about the caller's current team."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, _ = get_user_team(user_id)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404

    active = sum(1 for m in team["members"].values() if m.get("is_active", True))
    return jsonify({**_team_to_json(team), "created_at": team["created_at"], "member_count": active})


@permissions_roster.route('/teams/update', methods=['PUT'])
@requires_auth
@requires_permission("edit_team_settings")
def update_team_info():
    """PUT /api/teams/update — edit team name/number/description."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, _ = get_user_team(user_id)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404

    body = request.json or {}
    for field in ("name", "team_number", "description"):
        if field in body:
            team[field] = body[field]

    return jsonify({"success": True, "team": _team_to_json(team)})


# ==================== ROSTER ENDPOINTS ====================

@permissions_roster.route('/roster', methods=['GET'])
@requires_auth
@requires_permission("view_roster")
def get_roster():
    """GET /api/roster — all active members on the caller's team."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, _ = get_user_team(user_id)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404

    members = [
        _member_to_json(m) for m in team["members"].values()
        if m.get("is_active", True)
    ]
    members.sort(key=lambda x: (
        -ROLES.get(x.get("role", "viewer"), {}).get("level", 0),
        x.get("displayName", ""),
    ))
    return jsonify({"count": len(members), "members": members})


@permissions_roster.route('/roster/me', methods=['GET'])
@requires_auth
def get_own_profile():
    """GET /api/roster/me — caller's own roster profile."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, _, member = get_user_team(user_id)
    if member is None:
        return jsonify({"detail": "Not on a team"}), 404
    return jsonify(_member_to_json(member))


@permissions_roster.route('/roster/me', methods=['PUT'])
@requires_auth
def update_own_profile():
    """PUT /api/roster/me — update own display_name, bio, subteam, profile_pic_url."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, _, member = get_user_team(user_id)
    if member is None:
        return jsonify({"detail": "Not on a team"}), 404

    body = request.json or {}
    field_map = {
        "display_name": "display_name", "displayName": "display_name",
        "bio": "bio", "subteam": "subteam",
        "profile_pic_url": "profile_pic_url", "profilePicUrl": "profile_pic_url",
    }
    for req_key, int_key in field_map.items():
        if req_key in body:
            member[int_key] = body[req_key]

    return jsonify({"success": True, "member": _member_to_json(member)})


@permissions_roster.route('/roster/register', methods=['POST'])
@requires_auth
def register_roster_member():
    """POST /api/roster/register — legacy profile update endpoint (Flutter push queue compat)."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, _, member = get_user_team(user_id)
    if member is None:
        # User isn't on a team — silently accept so the push queue drains
        return jsonify({"success": True, "member": None}), 200

    body = request.json or {}
    field_map = {
        "display_name": "display_name", "displayName": "display_name",
        "bio": "bio", "subteam": "subteam",
        "profile_pic_url": "profile_pic_url", "profilePicUrl": "profile_pic_url",
    }
    for req_key, int_key in field_map.items():
        if req_key in body:
            member[int_key] = body[req_key]

    return jsonify({"success": True, "member": _member_to_json(member)}), 201


@permissions_roster.route('/roster/<target_user_id>/role', methods=['PUT'])
@requires_auth
@requires_permission("manage_roles")
def update_member_role(target_user_id):
    """
    PUT /api/roster/{user_id}/role
    Change a team member's role. Cannot promote above your own level.
    Cannot demote the owner unless you are also an owner.

    Body: { "role": "scout" | "leadScout" | ... }
    Response 200: { success, user_id, role, permissions }
    """
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, caller = get_user_team(user_id)
    if team is None or caller is None:
        return jsonify({"detail": "Not on a team"}), 404

    if target_user_id not in team["members"]:
        return jsonify({"detail": "Member not found"}), 404

    target = team["members"][target_user_id]
    if not target.get("is_active", True):
        return jsonify({"detail": "Member is inactive"}), 404

    body = request.json or {}
    new_role = body.get("role", "")
    if new_role not in ROLES:
        return jsonify({"detail": f"Invalid role. Must be one of: {list(ROLES.keys())}"}), 400

    caller_level = ROLES.get(caller["role"], {}).get("level", 0)
    if ROLES[new_role]["level"] > caller_level:
        return jsonify({"detail": "Cannot assign a role higher than your own"}), 403

    if target["role"] == "owner" and caller["role"] != "owner":
        return jsonify({"detail": "Cannot demote the team owner"}), 403

    target["role"] = new_role

    return jsonify({
        "success": True,
        "user_id": target_user_id,
        "role": new_role,
        "permissions": ROLE_PERMISSIONS.get(new_role, GUEST_PERMISSIONS),
    })


@permissions_roster.route('/roster/<target_user_id>', methods=['DELETE'])
@requires_auth
@requires_permission("manage_roster")
def remove_roster_member(target_user_id):
    """DELETE /api/roster/{user_id} — remove a member (mark inactive)."""
    user_id = get_user_id()
    if not user_id:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, _ = get_user_team(user_id)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404
    if target_user_id not in team["members"]:
        return jsonify({"detail": "Member not found"}), 404
    if target_user_id == user_id:
        return jsonify({"detail": "Cannot remove yourself. Use /teams/leave."}), 400

    target = team["members"][target_user_id]
    if target["role"] == "owner":
        return jsonify({"detail": "Cannot remove the team owner"}), 403

    target["is_active"] = False
    user_team_map.pop(target_user_id, None)
    return jsonify({"success": True, "message": "Member removed"})


# ==================== PERMISSION QUERY ENDPOINTS ====================

@permissions_roster.route('/permissions/roles', methods=['GET'])
@requires_auth
def get_roles():
    """GET /api/permissions/roles — all role definitions with permission lists."""
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
    """GET /api/permissions/guest — guest defaults (no auth required)."""
    return jsonify({"role": "viewer", "permissions": GUEST_PERMISSIONS})


# ==================== ADMIN ENDPOINTS ====================

@permissions_roster.route('/admin/stats', methods=['GET'])
@requires_auth
@requires_permission("view_admin")
def get_admin_stats():
    """GET /api/admin/stats — aggregate system statistics."""
    total_members = 0
    role_counts = {}
    for t in teams.values():
        for m in t["members"].values():
            if m.get("is_active", True):
                total_members += 1
                r = m.get("role", "viewer")
                role_counts[r] = role_counts.get(r, 0) + 1

    return jsonify({
        "teams": len(teams),
        "total_members": total_members,
        "by_role": role_counts,
        "timestamp": datetime.now().isoformat(),
    })