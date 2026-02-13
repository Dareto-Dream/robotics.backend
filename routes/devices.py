# routes/devices.py
#
# Device trust & Offline Authorization Certificate (OAC) system.
#
# Endpoints:
#   POST /auth/devices/register  — register a device, receive OAC
#   POST /auth/devices/renew     — renew an existing OAC
#   GET  /auth/devices            — list registered devices for current user
#   DELETE /auth/devices/<id>     — revoke a device
#   GET  /auth/devices/public-key — get the OAC public key for client embedding

import uuid
import jwt as pyjwt

from flask import Blueprint, request, jsonify

from auth.dependencies import require_auth
from auth.tokens import (
    create_oac,
    decode_oac,
    get_oac_public_key_pem,
    hash_device_public_key,
)
from data.db import get_conn, release_conn

devices = Blueprint("devices", __name__)


# ------------------------------------------------------------------
# POST /auth/devices/register
# ------------------------------------------------------------------
@devices.route("/register", methods=["POST"])
@require_auth
def register_device(current_user):
    """
    Register a new device for offline use. The client generates a
    cryptographic keypair and sends the public key here. The server
    stores the device record and returns a signed OAC.

    Required fields:
      - device_public_key: string (PEM or base64 of the device's public key)
      - device_name: string (human-readable label, e.g. "John's Pixel 8")
      - device_type: string (e.g. "android", "ios", "windows", "linux", "macos")

    Optional fields:
      - app_version: string (e.g. "2.1.0")
    """
    body = request.get_json(silent=True) or {}

    device_public_key = body.get("device_public_key", "").strip()
    device_name = body.get("device_name", "").strip()
    device_type = body.get("device_type", "").strip()
    app_version = body.get("app_version", "").strip()

    if not device_public_key:
        return jsonify({"detail": "device_public_key is required"}), 400
    if not device_name:
        return jsonify({"detail": "device_name is required"}), 400
    if not device_type:
        return jsonify({"detail": "device_type is required"}), 400

    user_id = current_user["id"]
    device_id = str(uuid.uuid4())
    dpk_hash = hash_device_public_key(device_public_key)

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO devices (device_id, user_id, device_name, device_type,
                                 device_public_key_hash, app_version)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (device_id, user_id, device_name, device_type, dpk_hash, app_version),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    oac_token = create_oac(
        user_id=user_id,
        device_id=device_id,
        device_public_key_hash=dpk_hash,
        app_version=app_version,
    )

    return jsonify({
        "success": True,
        "device_id": device_id,
        "oac": oac_token,
        "oac_public_key": get_oac_public_key_pem(),
    }), 201


# ------------------------------------------------------------------
# POST /auth/devices/renew
# ------------------------------------------------------------------
@devices.route("/renew", methods=["POST"])
@require_auth
def renew_oac(current_user):
    """
    Renew an existing OAC. Called when the app comes online and the
    current OAC is still valid or recently expired.

    Required fields:
      - device_id: string (UUID of the registered device)

    Optional fields:
      - app_version: string
    """
    body = request.get_json(silent=True) or {}
    device_id = body.get("device_id", "").strip()
    app_version = body.get("app_version", "").strip()

    if not device_id:
        return jsonify({"detail": "device_id is required"}), 400

    user_id = current_user["id"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT device_public_key_hash, is_revoked
            FROM devices
            WHERE device_id = %s AND user_id = %s
            """,
            (device_id, user_id),
        )
        row = cur.fetchone()
    finally:
        cur.close()
        release_conn(conn)

    if not row:
        return jsonify({"detail": "Device not found"}), 404

    dpk_hash, is_revoked = row

    if is_revoked:
        return jsonify({"detail": "Device has been revoked"}), 403

    # Update last_renewed
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE devices SET last_renewed = NOW(), app_version = %s WHERE device_id = %s",
            (app_version or None, device_id),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    oac_token = create_oac(
        user_id=user_id,
        device_id=device_id,
        device_public_key_hash=dpk_hash,
        app_version=app_version,
    )

    return jsonify({
        "success": True,
        "device_id": device_id,
        "oac": oac_token,
    }), 200


# ------------------------------------------------------------------
# GET /auth/devices
# ------------------------------------------------------------------
@devices.route("", methods=["GET"])
@require_auth
def list_devices(current_user):
    """List all devices registered for the current user."""
    user_id = current_user["id"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT device_id, device_name, device_type, app_version,
                   is_revoked, registered_at, last_renewed
            FROM devices
            WHERE user_id = %s
            ORDER BY registered_at DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        release_conn(conn)

    device_list = [
        {
            "device_id": str(r[0]),
            "device_name": r[1],
            "device_type": r[2],
            "app_version": r[3] or "",
            "is_revoked": r[4],
            "registered_at": r[5].isoformat() if r[5] else "",
            "last_renewed": r[6].isoformat() if r[6] else "",
        }
        for r in rows
    ]

    return jsonify({"devices": device_list, "count": len(device_list)}), 200


# ------------------------------------------------------------------
# DELETE /auth/devices/<device_id>
# ------------------------------------------------------------------
@devices.route("/<device_id>", methods=["DELETE"])
@require_auth
def revoke_device(current_user, device_id):
    """
    Revoke a device. The OAC will still be locally valid until expiry,
    but the server will refuse to renew it. This is delayed revocation.
    """
    user_id = current_user["id"]

    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT 1 FROM devices WHERE device_id = %s AND user_id = %s",
            (device_id, user_id),
        )
        if not cur.fetchone():
            return jsonify({"detail": "Device not found"}), 404

        cur.execute(
            "UPDATE devices SET is_revoked = TRUE WHERE device_id = %s",
            (device_id,),
        )
        conn.commit()
    finally:
        cur.close()
        release_conn(conn)

    return jsonify({"success": True, "message": "Device revoked"}), 200


# ------------------------------------------------------------------
# GET /auth/devices/public-key
# ------------------------------------------------------------------
@devices.route("/public-key", methods=["GET"])
def get_public_key():
    """
    Return the server's OAC Ed25519 public key in PEM format.
    Clients embed this key to verify OACs offline.
    No authentication required — this is public information.
    """
    pem = get_oac_public_key_pem()
    if not pem:
        return jsonify({"detail": "OAC keys not configured on server"}), 503

    return jsonify({"public_key": pem}), 200
