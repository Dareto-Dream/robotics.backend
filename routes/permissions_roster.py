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

permissions_roster = Blueprint('permissions_roster', __name__)

# ━━━━━━━━━━━━━━━ ROLE & PERMISSION DEFINITIONS ━━━━━━━━━━━━━━━━

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


# ━━━━━━━━━━━━━━━━ IN-MEMORY STORAGE ━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# teams[team_code] = {
#     "team_code": str,           # 6-char join code (also the dict key)
#     "name": str,                # display name chosen by creator
#     "team_number": str,         # FRC team number
#     "description": str,
#     "created_by": str,          # UUID of the creator
#     "created_at": str,          # ISO timestamp
#     "members": {
#         <user_uuid>: {
#             "user_id": str,     # same UUID
#             "username": str,
#             "display_name": str,
#             "bio": str,
#             "profile_pic_url": str,
#             "role": str,        # one of ROLES keys
#             "subteam": str,
#             "joined_at": str,
#             "is_active": bool,  # False = left / removed
#         }
#     }
# }
teams = {}

# Reverse lookup:  user_uuid  ->  team_code
# Only contains *active* members.
user_team_map = {}


# ━━━━━━━━━━━━━━━━━━━ AUTH HELPERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

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


def _get_user_team(user_id):
    """Return (team_code, team_dict, member_dict) or (None, None, None)."""
    code = user_team_map.get(user_id)
    if code and code in teams:
        team = teams[code]
        member = team["members"].get(user_id)
        if member and member.get("is_active", False):
            return code, team, member
    return None, None, None


def _resolve_permissions(user_id):
    """Compute (role_str, permissions_list) from membership."""
    _, _, member = _get_user_team(user_id)
    if member is None:
        return "viewer", list(GUEST_PERMISSIONS)
    role = member.get("role", "viewer")
    return role, list(ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS))


def requires_permission(perm_key):
    """Decorator: 403 if the calling user lacks perm_key."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            uid = _get_user_id()
            if not uid:
                return jsonify({"detail": "X-User-Id header required"}), 401
            _, perms = _resolve_permissions(uid)
            if perm_key not in perms:
                return jsonify({"detail": f"Permission denied: requires '{perm_key}'"}), 403
            return f(*args, **kwargs)
        return wrapper
    return decorator


# ━━━━━━━━━━━━━━━━━━ TEAM HELPERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O/1/I


def _generate_join_code():
    """Create a unique 6-char code that is not already in use."""
    for _ in range(100):
        code = "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(6))
        if code not in teams:
            return code
    raise RuntimeError("Could not generate unique join code")


def _active_member_count(team):
    return sum(1 for m in team["members"].values() if m.get("is_active"))


def _cleanup_empty_teams():
    """Delete every team that has zero active members."""
    empty = [code for code, t in teams.items() if _active_member_count(t) == 0]
    for code in empty:
        del teams[code]
    # Scrub stale entries from user_team_map
    stale = [uid for uid, c in user_team_map.items() if c not in teams]
    for uid in stale:
        del user_team_map[uid]


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
        "team_code":    t["team_code"],
        "name":         t["name"],
        "team_number":  t["team_number"],
        "description":  t.get("description", ""),
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
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    body = request.json or {}
    username = body.get("username", "")

    # Housekeeping: remove any abandoned teams
    _cleanup_empty_teams()

    # If user is on a team, keep their username fresh
    _, team, member = _get_user_team(uid)
    if member and username:
        member["username"] = username

    role, permissions = _resolve_permissions(uid)

    resp = {
        "user_id":     uid,
        "role":        role,
        "permissions": permissions,
        "team":        None,
        "roster":      None,
    }

    if team is not None:
        resp["team"] = _team_json(team)
        resp["roster"] = [
            _member_json(m) for m in team["members"].values()
            if m.get("is_active")
        ]

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
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    # Must not already be on a team
    _, existing_team, existing_member = _get_user_team(uid)
    if existing_team is not None:
        return jsonify({"detail": "Already on a team. Leave first."}), 409

    body = request.json or {}
    name = body.get("name", "").strip()
    team_number = body.get("team_number", "").strip()
    username = body.get("username", "").strip()
    display_name = body.get("display_name", "").strip() or username

    if not name:
        return jsonify({"detail": "Team name is required"}), 400

    code = _generate_join_code()
    now = datetime.now().isoformat()

    teams[code] = {
        "team_code":   code,
        "name":        name,
        "team_number": team_number,
        "description": "",
        "created_by":  uid,
        "created_at":  now,
        "members": {
            uid: {
                "user_id":         uid,
                "username":        username,
                "display_name":    display_name,
                "bio":             "",
                "profile_pic_url": "",
                "role":            "owner",
                "subteam":         "",
                "joined_at":       now,
                "is_active":       True,
            }
        },
    }
    user_team_map[uid] = code

    role, permissions = _resolve_permissions(uid)

    return jsonify({
        "success":     True,
        "team":        _team_json(teams[code]),
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
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    # Must not already be on a team
    _, existing_team, _ = _get_user_team(uid)
    if existing_team is not None:
        return jsonify({"detail": "Already on a team. Leave first."}), 409

    body = request.json or {}
    code = body.get("team_code", "").strip().upper()
    username = body.get("username", "").strip()
    display_name = body.get("display_name", "").strip() or username

    if not code:
        return jsonify({"detail": "Team code is required"}), 400
    if code not in teams:
        return jsonify({"detail": "Invalid team code"}), 404

    team = teams[code]
    now = datetime.now().isoformat()

    # Returning member?  Reactivate with their previous role.
    if uid in team["members"]:
        prev = team["members"][uid]
        prev["is_active"] = True
        if username:
            prev["username"] = username
        if display_name:
            prev["display_name"] = display_name
    else:
        # Brand-new member -> scout
        team["members"][uid] = {
            "user_id":         uid,
            "username":        username,
            "display_name":    display_name,
            "bio":             "",
            "profile_pic_url": "",
            "role":            "scout",
            "subteam":         "",
            "joined_at":       now,
            "is_active":       True,
        }

    user_team_map[uid] = code

    role, permissions = _resolve_permissions(uid)

    return jsonify({
        "success":     True,
        "team":        _team_json(team),
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
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400

    _, team, member = _get_user_team(uid)
    if team is None or member is None:
        return jsonify({"detail": "Not on a team"}), 404

    team_name = team["name"]

    # Deactivate
    member["is_active"] = False
    user_team_map.pop(uid, None)

    # Auto-delete if nobody active is left
    _cleanup_empty_teams()

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
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, team, _ = _get_user_team(uid)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404
    return jsonify({
        **_team_json(team),
        "created_at":   team["created_at"],
        "member_count": _active_member_count(team),
    })


@permissions_roster.route('/teams/update', methods=['PUT'])
@requires_auth
@requires_permission("edit_team_settings")
def update_team():
    """PUT /api/teams/update"""
    uid = _get_user_id()
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, team, _ = _get_user_team(uid)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404
    body = request.json or {}
    for key in ("name", "team_number", "description"):
        if key in body:
            team[key] = body[key]
    return jsonify({"success": True, "team": _team_json(team)})


# ━━━━━━━━━━━━━━━━━━ ROSTER ENDPOINTS ━━━━━━━━━━━━━━━━━━━━━━━━━

@permissions_roster.route('/roster', methods=['GET'])
@requires_auth
@requires_permission("view_roster")
def get_roster():
    """GET /api/roster"""
    uid = _get_user_id()
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, team, _ = _get_user_team(uid)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404
    members = [
        _member_json(m) for m in team["members"].values()
        if m.get("is_active")
    ]
    members.sort(key=lambda x: (
        -ROLES.get(x["role"], {}).get("level", 0),
        x.get("displayName", ""),
    ))
    return jsonify({"count": len(members), "members": members})


@permissions_roster.route('/roster/me', methods=['GET'])
@requires_auth
def get_own_profile():
    """GET /api/roster/me"""
    uid = _get_user_id()
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, _, member = _get_user_team(uid)
    if member is None:
        return jsonify({"detail": "Not on a team"}), 404
    return jsonify(_member_json(member))


@permissions_roster.route('/roster/me', methods=['PUT'])
@requires_auth
def update_own_profile():
    """PUT /api/roster/me"""
    uid = _get_user_id()
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, _, member = _get_user_team(uid)
    if member is None:
        return jsonify({"detail": "Not on a team"}), 404
    body = request.json or {}
    _apply_profile_fields(member, body)
    return jsonify({"success": True, "member": _member_json(member)})


@permissions_roster.route('/roster/register', methods=['POST'])
@requires_auth
def register_profile():
    """POST /api/roster/register  (Flutter push-queue compat)"""
    uid = _get_user_id()
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, _, member = _get_user_team(uid)
    if member is None:
        # Not on a team: accept silently so the push queue drains
        return jsonify({"success": True, "member": None}), 200
    body = request.json or {}
    _apply_profile_fields(member, body)
    return jsonify({"success": True, "member": _member_json(member)}), 201


def _apply_profile_fields(member, body):
    mapping = {
        "display_name": "display_name", "displayName": "display_name",
        "bio": "bio", "subteam": "subteam",
        "profile_pic_url": "profile_pic_url", "profilePicUrl": "profile_pic_url",
    }
    for req_key, int_key in mapping.items():
        if req_key in body:
            member[int_key] = body[req_key]


@permissions_roster.route('/roster/<target_id>/role', methods=['PUT'])
@requires_auth
@requires_permission("manage_roles")
def update_member_role(target_id):
    """PUT /api/roster/{uuid}/role"""
    uid = _get_user_id()
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, team, caller = _get_user_team(uid)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404
    if target_id not in team["members"]:
        return jsonify({"detail": "Member not found"}), 404
    target = team["members"][target_id]
    if not target.get("is_active"):
        return jsonify({"detail": "Member is inactive"}), 404
    body = request.json or {}
    new_role = body.get("role", "")
    if new_role not in ROLES:
        return jsonify({"detail": f"Invalid role. Valid: {list(ROLES.keys())}"}), 400
    caller_level = ROLES.get(caller["role"], {}).get("level", 0)
    if ROLES[new_role]["level"] > caller_level:
        return jsonify({"detail": "Cannot assign a role higher than your own"}), 403
    if target["role"] == "owner" and caller["role"] != "owner":
        return jsonify({"detail": "Cannot demote the team owner"}), 403
    target["role"] = new_role
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
    if not uid:
        return jsonify({"detail": "X-User-Id header required"}), 400
    _, team, _ = _get_user_team(uid)
    if team is None:
        return jsonify({"detail": "Not on a team"}), 404
    if target_id not in team["members"]:
        return jsonify({"detail": "Member not found"}), 404
    if target_id == uid:
        return jsonify({"detail": "Use /teams/leave to remove yourself"}), 400
    target = team["members"][target_id]
    if target["role"] == "owner":
        return jsonify({"detail": "Cannot remove the team owner"}), 403
    target["is_active"] = False
    user_team_map.pop(target_id, None)
    _cleanup_empty_teams()
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
    _cleanup_empty_teams()
    total = 0
    by_role = {}
    for t in teams.values():
        for m in t["members"].values():
            if m.get("is_active"):
                total += 1
                r = m.get("role", "viewer")
                by_role[r] = by_role.get(r, 0) + 1
    return jsonify({
        "teams":         len(teams),
        "total_members": total,
        "by_role":       by_role,
        "timestamp":     datetime.now().isoformat(),
    })