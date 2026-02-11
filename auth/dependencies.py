# src/auth/dependencies.py
#
# Flask decorator that protects routes with JWT auth.
# Drop-in replacement for the existing requires_auth (Basic auth) decorator
# on any route that should require a logged-in user.
#
# Usage:
#   from src.auth.dependencies import require_auth
#
#   @api.route('/some/protected/route')
#   @require_auth
#   def my_route(current_user):
#       # current_user = {"id": "...", "email": "..."}
#       ...

from functools import wraps
from flask import request, jsonify
import jwt as pyjwt

from src.auth.tokens import decode_token
from data.auth_db import get_auth_conn, release_auth_conn


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return jsonify({"detail": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]

        # --- Decode JWT ---
        try:
            payload = decode_token(token)
        except pyjwt.ExpiredSignatureError:
            return jsonify({"detail": "Token expired"}), 401
        except pyjwt.InvalidTokenError:
            return jsonify({"detail": "Invalid token"}), 401

        if payload.get("type") != "access":
            return jsonify({"detail": "Expected access token"}), 401

        user_id = payload.get("sub")
        if not user_id:
            return jsonify({"detail": "Token missing subject"}), 401

        # --- Load user from auth DB ---
        conn = get_auth_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT id, email FROM auth_users WHERE id = %s",
            (user_id,)
        )
        row = cur.fetchone()
        cur.close()
        release_auth_conn(conn)

        if not row:
            return jsonify({"detail": "User not found"}), 401

        current_user = {"id": str(row[0]), "email": row[1]}
        return f(*args, current_user=current_user, **kwargs)

    return decorated
