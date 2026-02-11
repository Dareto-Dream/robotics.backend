from flask import Blueprint, request, jsonify, abort
from functools import wraps
from datetime import datetime
import secrets
import requests
import os
import base64

from helpers import USERNAME, PASSWORD
from data.db import get_conn, release_conn

api = Blueprint('api', __name__)

# ==================== FRC CONFIG ====================

FRC_API_BASE = "https://frc-api.firstinspires.org/v3.0"
FRC_API_USERNAME = os.environ.get("FRC_API_USERNAME", "changeme")
FRC_API_TOKEN = os.environ.get("FRC_API_TOKEN", "changeme")

# Only external API caching remains in memory
cache = {
    "events": {"data": None, "timestamp": None, "ttl": 6 * 3600},
    "teams": {},
    "matches": {},
    "modules_manifest": {"data": None, "timestamp": None, "ttl": 24 * 3600},
    "modules": {},
}

# ==================== AUTH ====================

def check_auth(username, password):
    user_ok = secrets.compare_digest(username, USERNAME)
    pass_ok = secrets.compare_digest(password, PASSWORD)
    return user_ok and pass_ok

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return jsonify({"detail": "Invalid credentials"}), 401, {
                "WWW-Authenticate": 'Basic realm="Login Required"'
            }

        uid = request.headers.get("X-User-Id")
        if not uid:
            return jsonify({"detail": "Missing X-User-Id"}), 401

        return f(*args, **kwargs)
    return decorated

# ==================== FRC API ====================

def get_frc_api_headers():
    auth_string = f"{FRC_API_USERNAME}:{FRC_API_TOKEN}"
    encoded = base64.b64encode(auth_string.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json"
    }

def is_cache_valid(entry, ttl):
    if entry["data"] is None or entry["timestamp"] is None:
        return False
    age = (datetime.now() - entry["timestamp"]).total_seconds()
    return age < ttl

def fetch_from_frc_api(endpoint):
    try:
        url = f"{FRC_API_BASE}/{endpoint}"
        response = requests.get(url, headers=get_frc_api_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print("FRC API error:", e)
        return None

# ==================== EVENTS ====================

@api.route('/events', methods=['GET'])
@requires_auth
def get_events():
    if is_cache_valid(cache["events"], cache["events"]["ttl"]):
        return jsonify(cache["events"]["data"])

    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/events")

    if data is None:
        abort(503, "FRC API unavailable")

    cache["events"]["data"] = data
    cache["events"]["timestamp"] = datetime.now()
    return jsonify(data)

@api.route('/events/<event_code>/teams', methods=['GET'])
@requires_auth
def get_event_teams(event_code):
    ttl = 12 * 3600

    if event_code in cache["teams"] and is_cache_valid(cache["teams"][event_code], ttl):
        return jsonify(cache["teams"][event_code]["data"])

    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/teams?eventCode={event_code}")

    if data is None:
        abort(503, "FRC API unavailable")

    cache["teams"][event_code] = {"data": data, "timestamp": datetime.now()}
    return jsonify(data)

@api.route('/events/<event_code>/matches', methods=['GET'])
@requires_auth
def get_event_matches(event_code):
    ttl = 30 * 60

    if event_code in cache["matches"] and is_cache_valid(cache["matches"][event_code], ttl):
        return jsonify(cache["matches"][event_code]["data"])

    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/schedule/{event_code}")

    if data is None:
        abort(503, "FRC API unavailable")

    cache["matches"][event_code] = {"data": data, "timestamp": datetime.now()}
    return jsonify(data)

# ==================== MODULES ====================

@api.route('/modules/manifest', methods=['GET'])
@requires_auth
def get_modules_manifest():
    if is_cache_valid(cache["modules_manifest"], cache["modules_manifest"]["ttl"]):
        return jsonify(cache["modules_manifest"]["data"])

    manifest = {
        "version": "1.0",
        "modules": [
            {"id": "auto_scoring", "name": "Autonomous Scoring"},
            {"id": "teleop_performance", "name": "Teleop Performance"},
            {"id": "pit_scouting", "name": "Pit Scouting"},
        ]
    }

    cache["modules_manifest"]["data"] = manifest
    cache["modules_manifest"]["timestamp"] = datetime.now()
    return jsonify(manifest)

# ==================== MATCH REPORTS ====================

@api.route('/reports/match', methods=['POST'])
@requires_auth
def submit_match_report():
    data = request.json
    uid = request.headers.get("X-User-Id")

    required = ["event_code", "team_number", "match_number"]
    for r in required:
        if r not in data:
            abort(400, f"Missing {r}")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO match_reports (submitted_by, event_code, team_number, match_number, data)
    VALUES (%s,%s,%s,%s,%s)
    RETURNING id, timestamp;
    """, (
        uid,
        str(data["event_code"]),
        str(data["team_number"]),
        int(data["match_number"]),
        data
    ))

    rid, ts = cur.fetchone()
    conn.commit()

    cur.close()
    release_conn(conn)

    return jsonify({
        "success": True,
        "report_id": rid,
        "timestamp": ts.isoformat()
    }), 201


@api.route('/reports/match', methods=['GET'])
@requires_auth
def get_match_reports():
    event_code = request.args.get('event_code')
    team_number = request.args.get('team_number')
    match_number = request.args.get('match_number')

    conn = get_conn()
    cur = conn.cursor()

    query = """
    SELECT id, submitted_by, event_code, team_number, match_number, data, timestamp
    FROM match_reports WHERE 1=1
    """
    params = []

    if event_code:
        query += " AND event_code=%s"
        params.append(event_code)

    if team_number:
        query += " AND team_number=%s"
        params.append(team_number)

    if match_number:
        query += " AND match_number=%s"
        params.append(int(match_number))

    query += " ORDER BY timestamp DESC LIMIT 2000"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()

    cur.close()
    release_conn(conn)

    reports = [{
        "report_id": r[0],
        "submitted_by": str(r[1]),
        "event_code": r[2],
        "team_number": r[3],
        "match_number": r[4],
        "data": r[5],
        "timestamp": r[6].isoformat()
    } for r in rows]

    return jsonify({"count": len(reports), "reports": reports})

# ==================== PIT REPORTS ====================

@api.route('/reports/pit', methods=['POST'])
@requires_auth
def submit_pit_report():
    data = request.json
    uid = request.headers.get("X-User-Id")

    if "event_code" not in data or "team_number" not in data:
        abort(400, "Missing required fields")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO pit_reports (submitted_by, event_code, team_number, data)
    VALUES (%s,%s,%s,%s)
    RETURNING id, timestamp;
    """, (
        uid,
        str(data["event_code"]),
        str(data["team_number"]),
        data
    ))

    rid, ts = cur.fetchone()
    conn.commit()

    cur.close()
    release_conn(conn)

    return jsonify({
        "success": True,
        "report_id": rid,
        "timestamp": ts.isoformat()
    }), 201


@api.route('/reports/pit', methods=['GET'])
@requires_auth
def get_pit_reports():
    event_code = request.args.get('event_code')
    team_number = request.args.get('team_number')

    conn = get_conn()
    cur = conn.cursor()

    query = """
    SELECT id, submitted_by, event_code, team_number, data, timestamp
    FROM pit_reports WHERE 1=1
    """
    params = []

    if event_code:
        query += " AND event_code=%s"
        params.append(event_code)

    if team_number:
        query += " AND team_number=%s"
        params.append(team_number)

    query += " ORDER BY timestamp DESC LIMIT 2000"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()

    cur.close()
    release_conn(conn)

    reports = [{
        "report_id": r[0],
        "submitted_by": str(r[1]),
        "event_code": r[2],
        "team_number": r[3],
        "data": r[4],
        "timestamp": r[5].isoformat()
    } for r in rows]

    return jsonify({"count": len(reports), "reports": reports})

# ==================== HEALTH ====================

@api.route('/health', methods=['GET'])
def health_check():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        cur.close()
        release_conn(conn)
        db_ok = True
    except:
        db_ok = False

    return jsonify({
        "status": "healthy" if db_ok else "database_error",
        "timestamp": datetime.now().isoformat(),
        "database_connected": db_ok
    })
