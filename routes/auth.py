# routes/auth.py
#
# Auth Blueprint — mounts at /auth
#
# Endpoints:
#   POST /auth/register   — create account, returns tokens
#   POST /auth/login      — verify credentials, returns tokens
#   POST /auth/refresh    — strict token rotation
#   POST /auth/logout     — delete refresh token from Redis
#   GET  /auth/health     — liveness check for auth DB + Redis

import uuid
import jwt as pyjwt

from flask import Blueprint, request, jsonify

from auth.hashing import hash_password, verify_password
from auth.tokens import create_access_token, create_refresh_token, decode_token
from auth.dependencies import require_auth
from data.auth_db import get_auth_conn, release_auth_conn
from data.auth_redis import (
    set_refresh_token,
    get_refresh_token,
    delete_refresh_token,
    ping as redis_ping,
)
from data.users_repo import ensure_user

auth = Blueprint("auth", __name__)


# ------------------------------------------------------------------
# POST /auth/register
# ------------------------------------------------------------------
@auth.route("/register", methods=["POST"])
def register():
    body = request.get_json(silent=True) or {}
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        return jsonify({"detail": "email and password are required"}), 400

    if len(password) < 8:
        return jsonify({"detail": "Password must be at least 8 characters"}), 400

    conn = get_auth_conn()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM auth_users WHERE email = %s", (email,))
    if cur.fetchone():
        cur.close()
        release_auth_conn(conn)
        return jsonify({"detail": "Email already registered"}), 409

    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)

    cur.execute(
        "INSERT INTO auth_users (id, email, password_hash) VALUES (%s, %s, %s)",
        (user_id, email, password_hash)
    )
    conn.commit()
    cur.close()
    release_auth_conn(conn)

    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    set_refresh_token(user_id, refresh)

    ensure_user(user_id)

    return jsonify({"access": access, "refresh": refresh}), 201


# ------------------------------------------------------------------
# POST /auth/login
# ------------------------------------------------------------------
@auth.route("/login", methods=["POST"])
def login():
    body = request.get_json(silent=True) or {}
    email = body.get("email", "").strip().lower()
    password = body.get("password", "")

    if not email or not password:
        return jsonify({"detail": "email and password are required"}), 400

    conn = get_auth_conn()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, password_hash FROM auth_users WHERE email = %s",
        (email,)
    )
    row = cur.fetchone()
    cur.close()
    release_auth_conn(conn)

    if not row or not verify_password(password, row[1]):
        return jsonify({"detail": "Invalid email or password"}), 401

    user_id = str(row[0])
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)
    set_refresh_token(user_id, refresh)

    return jsonify({"access": access, "refresh": refresh}), 200


# ------------------------------------------------------------------
# POST /auth/refresh
# ------------------------------------------------------------------
@auth.route("/refresh", methods=["POST"])
def refresh():
    body = request.get_json(silent=True) or {}
    refresh_token = body.get("refresh", "").strip()

    if not refresh_token:
        return jsonify({"detail": "refresh token is required"}), 400

    try:
        payload = decode_token(refresh_token)
    except pyjwt.ExpiredSignatureError:
        return jsonify({"detail": "Refresh token expired, please log in again"}), 401
    except pyjwt.InvalidTokenError:
        return jsonify({"detail": "Invalid refresh token"}), 401

    if payload.get("type") != "refresh":
        return jsonify({"detail": "Expected refresh token"}), 401

    user_id = payload.get("sub")
    if not user_id:
        return jsonify({"detail": "Token missing subject"}), 401

    stored = get_refresh_token(user_id)

    if not stored:
        return jsonify({"detail": "Session expired, please log in again"}), 401

    if stored != refresh_token:
        delete_refresh_token(user_id)
        return jsonify({"detail": "Refresh token reuse detected — session invalidated"}), 401

    delete_refresh_token(user_id)

    new_access = create_access_token(user_id)
    new_refresh = create_refresh_token(user_id)
    set_refresh_token(user_id, new_refresh)

    return jsonify({"access": new_access, "refresh": new_refresh}), 200


# ------------------------------------------------------------------
# POST /auth/logout
# ------------------------------------------------------------------
@auth.route("/logout", methods=["POST"])
@require_auth
def logout(current_user):
    delete_refresh_token(current_user["id"])
    return jsonify({"success": True}), 200


# ------------------------------------------------------------------
# GET /auth/health
# ------------------------------------------------------------------
@auth.route("/health", methods=["GET"])
def auth_health():
    db_ok = False
    redis_ok = redis_ping()

    try:
        conn = get_auth_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        cur.close()
        release_auth_conn(conn)
        db_ok = True
    except Exception:
        pass

    status = "healthy" if (db_ok and redis_ok) else "degraded"
    return jsonify({
        "status": status,
        "auth_db": db_ok,
        "auth_redis": redis_ok,
    }), 200 if status == "healthy" else 503
