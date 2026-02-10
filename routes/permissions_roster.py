from flask import Blueprint, request, jsonify, abort
from functools import wraps
from datetime import datetime
import secrets
import uuid
from helpers import USERNAME, PASSWORD

permissions_roster = Blueprint('permissions_roster', __name__)

# ==================== PERMISSION SYSTEM ====================

# Role definitions (display-only, level is for sorting)
ROLES = {
    "viewer": {
        "level": 0,
        "name": "Viewer",
        "description": "Read-only access to public data"
    },
    "scout": {
        "level": 1,
        "name": "Scout",
        "description": "Submit reports, view analytics"
    },
    "leadScout": {
        "level": 2,
        "name": "Lead Scout",
        "description": "View all reports, export data"
    },
    "driveCoach": {
        "level": 2,
        "name": "Drive Coach",
        "description": "Timer access, strategy tools"
    },
    "analyst": {
        "level": 2,
        "name": "Analyst",
        "description": "Full analytics, comparison tools"
    },
    "admin": {
        "level": 3,
        "name": "Admin",
        "description": "All features, team management"
    },
    "owner": {
        "level": 4,
        "name": "Owner",
        "description": "All permissions"
    }
}

# Permission definitions by role
ROLE_PERMISSIONS = {
    "viewer": [
        "view_dashboard",
        "view_manual",
        "view_settings"
    ],
    "scout": [
        "view_dashboard",
        "view_scoreboard",
        "view_manual",
        "view_scouting",
        "view_analytics",
        "view_roster",
        "view_settings",
        "submit_match_report",
        "submit_pit_report",
        "edit_own_reports",
        "delete_own_reports"
    ],
    "leadScout": [
        "view_dashboard",
        "view_scoreboard",
        "view_manual",
        "view_scouting",
        "view_analytics",
        "view_roster",
        "view_settings",
        "submit_match_report",
        "submit_pit_report",
        "edit_own_reports",
        "delete_own_reports",
        "export_analytics"
    ],
    "driveCoach": [
        "view_dashboard",
        "view_scoreboard",
        "view_manual",
        "view_drive",
        "view_analytics",
        "view_roster",
        "view_settings",
        "export_analytics"
    ],
    "analyst": [
        "view_dashboard",
        "view_scoreboard",
        "view_manual",
        "view_scouting",
        "view_analytics",
        "view_alliance",
        "view_roster",
        "view_settings",
        "export_analytics"
    ],
    "admin": [
        "view_dashboard",
        "view_scoreboard",
        "view_manual",
        "view_scouting",
        "view_alliance",
        "view_drive",
        "view_analytics",
        "view_roster",
        "view_admin",
        "view_settings",
        "submit_match_report",
        "submit_pit_report",
        "edit_own_reports",
        "delete_own_reports",
        "delete_any_report",
        "edit_team_settings",
        "manage_roles",
        "export_analytics"
    ],
    "owner": [
        "view_dashboard",
        "view_scoreboard",
        "view_manual",
        "view_scouting",
        "view_alliance",
        "view_drive",
        "view_analytics",
        "view_roster",
        "view_admin",
        "view_settings",
        "submit_match_report",
        "submit_pit_report",
        "edit_own_reports",
        "delete_own_reports",
        "delete_any_report",
        "edit_team_settings",
        "manage_roles",
        "export_analytics"
    ]
}

# Guest/offline defaults
GUEST_PERMISSIONS = [
    "view_dashboard",
    "view_manual",
    "view_settings",
    "edit_own_profile"
]

# In-memory storage (replace with database in production)
user_sessions = {}  # session_id -> user_data
roster_members = {}  # user_id -> roster_data

def check_auth(username, password):
    """Basic authentication check"""
    user_ok = secrets.compare_digest(username, USERNAME)
    pass_ok = secrets.compare_digest(password, PASSWORD)
    return user_ok and pass_ok

def requires_auth(f):
    """Require basic authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"detail": "Invalid credentials"}), 401, {
                'WWW-Authenticate': 'Basic realm="Login Required"'
            }
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    """Get current user from session or auth"""
    # Check for session token in header
    session_token = request.headers.get('X-Session-Token')
    if session_token and session_token in user_sessions:
        return user_sessions[session_token]
    
    # Fallback to basic auth
    auth = request.authorization
    if auth and check_auth(auth.username, auth.password):
        # Return default admin user
        return {
            "userId": "admin_user",
            "username": auth.username,
            "role": "admin",
            "permissions": ROLE_PERMISSIONS["admin"]
        }
    
    return None

def requires_permission(permission_key):
    """Decorator to check if user has specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"detail": "Authentication required"}), 401
            
            permissions = user.get("permissions", [])
            if permission_key not in permissions:
                return jsonify({
                    "detail": f"Permission denied: requires '{permission_key}'",
                    "required_permission": permission_key,
                    "user_permissions": permissions
                }), 403
            
            return f(*args, **kwargs)
        return decorated
    return decorator

# ==================== AUTHENTICATION ENDPOINTS ====================

@permissions_roster.route('/auth/login', methods=['POST'])
def login():
    """
    POST /auth/login
    Authenticate user and return session with role and permissions
    
    Request body:
    {
        "username": "string",
        "password": "string"
    }
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    username = request.json.get('username')
    password = request.json.get('password')
    
    if not username or not password:
        abort(400, "Username and password required")
    
    # In production, validate against database
    # For now, check against basic auth
    if not check_auth(username, password):
        return jsonify({"detail": "Invalid credentials"}), 401
    
    # Look up user in roster or create default admin
    user_id = None
    role = "admin"  # Default for authenticated users
    
    # Check if user exists in roster
    for member_id, member in roster_members.items():
        if member.get('username') == username:
            user_id = member_id
            role = member.get('role', 'scout')
            break
    
    if not user_id:
        user_id = f"user_{uuid.uuid4().hex[:8]}"
    
    # Generate session token
    session_token = secrets.token_urlsafe(32)
    
    # Get permissions for role
    permissions = ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS)
    
    # Create session
    user_data = {
        "userId": user_id,
        "username": username,
        "role": role,
        "permissions": permissions,
        "loginAt": datetime.now().isoformat()
    }
    
    user_sessions[session_token] = user_data
    
    return jsonify({
        "success": True,
        "sessionToken": session_token,
        "user": {
            "userId": user_id,
            "username": username,
            "role": role,
            "roleLevel": ROLES[role]["level"],
            "roleName": ROLES[role]["name"],
            "permissions": permissions
        }
    })

@permissions_roster.route('/auth/session', methods=['GET'])
@requires_auth
def get_session():
    """
    GET /auth/session
    Get current session information
    Requires: X-Session-Token header or Basic Auth
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "No active session"}), 401
    
    role = user.get('role', 'viewer')
    
    return jsonify({
        "userId": user.get('userId'),
        "username": user.get('username'),
        "role": role,
        "roleLevel": ROLES[role]["level"],
        "roleName": ROLES[role]["name"],
        "permissions": user.get('permissions', GUEST_PERMISSIONS)
    })

@permissions_roster.route('/auth/refresh', methods=['POST'])
@requires_auth
def refresh_session():
    """
    POST /auth/refresh
    Refresh session and get updated permissions
    """
    user = get_current_user()
    if not user:
        return jsonify({"detail": "No active session"}), 401
    
    user_id = user.get('userId')
    
    # Look up current role in roster
    role = user.get('role', 'viewer')
    if user_id in roster_members:
        role = roster_members[user_id].get('role', role)
    
    # Update permissions
    permissions = ROLE_PERMISSIONS.get(role, GUEST_PERMISSIONS)
    
    # Update session
    session_token = request.headers.get('X-Session-Token')
    if session_token and session_token in user_sessions:
        user_sessions[session_token]['role'] = role
        user_sessions[session_token]['permissions'] = permissions
    
    return jsonify({
        "role": role,
        "roleLevel": ROLES[role]["level"],
        "permissions": permissions,
        "message": "Session refreshed"
    })

@permissions_roster.route('/auth/logout', methods=['POST'])
@requires_auth
def logout():
    """
    POST /auth/logout
    Logout and invalidate session
    """
    session_token = request.headers.get('X-Session-Token')
    if session_token and session_token in user_sessions:
        del user_sessions[session_token]
    
    return jsonify({
        "success": True,
        "message": "Logged out successfully"
    })

# ==================== PERMISSION ENDPOINTS ====================

@permissions_roster.route('/permissions/roles', methods=['GET'])
@requires_auth
def get_roles():
    """
    GET /permissions/roles
    Get all available roles
    """
    return jsonify({
        "roles": [
            {
                "id": role_id,
                "level": role_data["level"],
                "name": role_data["name"],
                "description": role_data["description"],
                "permissions": ROLE_PERMISSIONS.get(role_id, [])
            }
            for role_id, role_data in sorted(ROLES.items(), key=lambda x: x[1]["level"])
        ]
    })

@permissions_roster.route('/permissions/check', methods=['POST'])
@requires_auth
def check_permission():
    """
    POST /permissions/check
    Check if current user has specific permission(s)
    
    Request body:
    {
        "permission": "string" or ["string1", "string2"]
    }
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    user = get_current_user()
    if not user:
        return jsonify({"detail": "No active session"}), 401
    
    permissions = user.get('permissions', [])
    permission_set = set(permissions)
    
    requested = request.json.get('permission')
    if isinstance(requested, str):
        requested = [requested]
    
    if not isinstance(requested, list):
        abort(400, "Permission must be string or array of strings")
    
    results = {}
    for perm in requested:
        results[perm] = perm in permission_set
    
    return jsonify({
        "permissions": results,
        "allGranted": all(results.values())
    })

@permissions_roster.route('/permissions/guest', methods=['GET'])
def get_guest_permissions():
    """
    GET /permissions/guest
    Get default guest permissions (no auth required)
    """
    return jsonify({
        "role": "guest",
        "permissions": GUEST_PERMISSIONS
    })

# ==================== ROSTER ENDPOINTS ====================

@permissions_roster.route('/roster', methods=['GET'])
@requires_auth
@requires_permission('view_roster')
def get_roster():
    """
    GET /roster
    Get all roster members
    """
    members = []
    for user_id, member in roster_members.items():
        role = member.get('role', 'viewer')
        members.append({
            **member,
            "roleLevel": ROLES[role]["level"],
            "roleName": ROLES[role]["name"]
        })
    
    # Sort by role level (descending) then by name
    members.sort(key=lambda x: (-x.get('roleLevel', 0), x.get('displayName', '')))
    
    return jsonify({
        "count": len(members),
        "members": members
    })

@permissions_roster.route('/roster/register', methods=['POST'])
@requires_auth
def register_roster_member():
    """
    POST /roster/register
    Self-register as roster member
    
    Request body:
    {
        "displayName": "string",
        "username": "string",
        "bio": "string",
        "profilePicUrl": "string?",
        "subteam": "string"
    }
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Authentication required"}), 401
    
    required_fields = ['displayName', 'username']
    for field in required_fields:
        if field not in request.json:
            abort(400, f"Missing required field: {field}")
    
    # Check if username is already taken
    username = request.json.get('username')
    for member in roster_members.values():
        if member.get('username') == username:
            return jsonify({"detail": "Username already taken"}), 409
    
    # Create new roster member
    user_id = user.get('userId', f"user_{uuid.uuid4().hex[:8]}")
    
    member = {
        "id": str(uuid.uuid4()),
        "userId": user_id,
        "displayName": request.json.get('displayName'),
        "username": username,
        "bio": request.json.get('bio', ''),
        "profilePicUrl": request.json.get('profilePicUrl'),
        "role": "scout",  # Default role
        "subteam": request.json.get('subteam', ''),
        "joinedAt": datetime.now().isoformat()
    }
    
    roster_members[user_id] = member
    
    return jsonify({
        "success": True,
        "member": member,
        "message": "Roster registration successful"
    }), 201

@permissions_roster.route('/roster/<user_id>', methods=['GET'])
@requires_auth
@requires_permission('view_roster')
def get_roster_member(user_id):
    """
    GET /roster/{user_id}
    Get specific roster member
    """
    if user_id not in roster_members:
        abort(404, "Roster member not found")
    
    member = roster_members[user_id]
    role = member.get('role', 'viewer')
    
    return jsonify({
        **member,
        "roleLevel": ROLES[role]["level"],
        "roleName": ROLES[role]["name"]
    })

@permissions_roster.route('/roster/<user_id>', methods=['PUT'])
@requires_auth
def update_roster_member(user_id):
    """
    PUT /roster/{user_id}
    Update roster member (own profile or admin)
    
    Request body:
    {
        "displayName": "string?",
        "bio": "string?",
        "profilePicUrl": "string?",
        "subteam": "string?"
    }
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    user = get_current_user()
    if not user:
        return jsonify({"detail": "Authentication required"}), 401
    
    if user_id not in roster_members:
        abort(404, "Roster member not found")
    
    # Check if user is updating own profile or has admin permission
    current_user_id = user.get('userId')
    permissions = user.get('permissions', [])
    
    if user_id != current_user_id and 'manage_roles' not in permissions:
        return jsonify({"detail": "Permission denied: can only edit own profile"}), 403
    
    member = roster_members[user_id]
    
    # Update allowed fields
    updatable_fields = ['displayName', 'bio', 'profilePicUrl', 'subteam']
    for field in updatable_fields:
        if field in request.json:
            member[field] = request.json[field]
    
    roster_members[user_id] = member
    
    return jsonify({
        "success": True,
        "member": member,
        "message": "Roster member updated"
    })

@permissions_roster.route('/roster/<user_id>/role', methods=['PUT'])
@requires_auth
@requires_permission('manage_roles')
def update_member_role(user_id):
    """
    PUT /roster/{user_id}/role
    Update member role (admin only)
    
    Request body:
    {
        "role": "scout" | "leadScout" | "driveCoach" | "analyst" | "admin" | "owner"
    }
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    if user_id not in roster_members:
        abort(404, "Roster member not found")
    
    new_role = request.json.get('role')
    if not new_role or new_role not in ROLES:
        return jsonify({
            "detail": f"Invalid role. Must be one of: {list(ROLES.keys())}"
        }), 400
    
    # Update role
    roster_members[user_id]['role'] = new_role
    
    # Update any active sessions for this user
    for session_token, session_data in user_sessions.items():
        if session_data.get('userId') == user_id:
            session_data['role'] = new_role
            session_data['permissions'] = ROLE_PERMISSIONS.get(new_role, GUEST_PERMISSIONS)
    
    return jsonify({
        "success": True,
        "userId": user_id,
        "role": new_role,
        "permissions": ROLE_PERMISSIONS.get(new_role, []),
        "message": f"Role updated to {ROLES[new_role]['name']}"
    })

@permissions_roster.route('/roster/<user_id>', methods=['DELETE'])
@requires_auth
@requires_permission('manage_roles')
def delete_roster_member(user_id):
    """
    DELETE /roster/{user_id}
    Remove roster member (admin only)
    """
    if user_id not in roster_members:
        abort(404, "Roster member not found")
    
    member = roster_members[user_id]
    del roster_members[user_id]
    
    # Invalidate any sessions for this user
    sessions_to_remove = [
        token for token, data in user_sessions.items()
        if data.get('userId') == user_id
    ]
    for token in sessions_to_remove:
        del user_sessions[token]
    
    return jsonify({
        "success": True,
        "removed": member,
        "message": "Roster member removed"
    })

# ==================== ADMIN ENDPOINTS ====================

@permissions_roster.route('/admin/sessions', methods=['GET'])
@requires_auth
@requires_permission('view_admin')
def get_active_sessions():
    """
    GET /admin/sessions
    Get all active sessions (admin only)
    """
    sessions = []
    for token, data in user_sessions.items():
        sessions.append({
            "sessionToken": token[:8] + "...",  # Redact full token
            "userId": data.get('userId'),
            "username": data.get('username'),
            "role": data.get('role'),
            "loginAt": data.get('loginAt')
        })
    
    return jsonify({
        "count": len(sessions),
        "sessions": sessions
    })

@permissions_roster.route('/admin/sessions/<session_token>', methods=['DELETE'])
@requires_auth
@requires_permission('manage_roles')
def revoke_session(session_token):
    """
    DELETE /admin/sessions/{session_token}
    Revoke a session (admin only)
    """
    if session_token not in user_sessions:
        abort(404, "Session not found")
    
    session_data = user_sessions[session_token]
    del user_sessions[session_token]
    
    return jsonify({
        "success": True,
        "revoked": {
            "userId": session_data.get('userId'),
            "username": session_data.get('username')
        },
        "message": "Session revoked"
    })

@permissions_roster.route('/admin/stats', methods=['GET'])
@requires_auth
@requires_permission('view_admin')
def get_admin_stats():
    """
    GET /admin/stats
    Get system statistics (admin only)
    """
    role_counts = {}
    for member in roster_members.values():
        role = member.get('role', 'viewer')
        role_counts[role] = role_counts.get(role, 0) + 1
    
    return jsonify({
        "roster": {
            "totalMembers": len(roster_members),
            "byRole": role_counts
        },
        "sessions": {
            "active": len(user_sessions)
        },
        "timestamp": datetime.now().isoformat()
    })