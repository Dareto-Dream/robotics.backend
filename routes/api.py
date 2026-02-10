from flask import Blueprint, request, jsonify, abort
from functools import wraps
from datetime import datetime, timedelta
import secrets
import requests
from helpers import USERNAME, PASSWORD
import os

api = Blueprint('api', __name__)

# FRC API Configuration
FRC_API_BASE = "https://frc-api.firstinspires.org/v3.0"
FRC_API_USERNAME = os.environ.get("FRC_API_USERNAME", "changeme")
FRC_API_TOKEN = os.environ.get("FRC_API_TOKEN", "changeme")

# Cache storage (in production, use Redis or similar)
cache = {
    "events": {"data": None, "timestamp": None, "ttl": 6 * 3600},
    "teams": {},
    "matches": {},
    "modules_manifest": {"data": None, "timestamp": None, "ttl": 24 * 3600},
    "modules": {},
    "reports_match": [],
    "reports_pit": [],
}

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
                'WWW-Authenticate': 'Basic realm="Login Required"'
            }
        return f(*args, **kwargs)
    return decorated

def get_frc_api_headers():
    """Generate headers for FRC API requests"""
    import base64
    auth_string = f"{FRC_API_USERNAME}:{FRC_API_TOKEN}"
    encoded = base64.b64encode(auth_string.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Accept": "application/json"
    }

def is_cache_valid(cache_entry, ttl):
    if cache_entry.get("data") is None or cache_entry.get("timestamp") is None:
        return False
    age = (datetime.now() - cache_entry["timestamp"]).total_seconds()
    return age < ttl

def fetch_from_frc_api(endpoint):
    try:
        url = f"{FRC_API_BASE}/{endpoint}"
        response = requests.get(url, headers=get_frc_api_headers(), timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"FRC API error: {e}")
        return None

# ==================== Event Endpoints ====================

@api.route('/events', methods=['GET'])
@requires_auth
def get_events():
    if is_cache_valid(cache["events"], cache["events"]["ttl"]):
        return jsonify(cache["events"]["data"])

    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/events")

    if data is None:
        if cache["events"]["data"] is not None:
            return jsonify({"cached": True, "data": cache["events"]["data"]})
        abort(503, "FRC API unavailable and no cached data")

    cache["events"]["data"] = data
    cache["events"]["timestamp"] = datetime.now()
    return jsonify(data)

@api.route('/events/<event_code>/teams', methods=['GET'])
@requires_auth
def get_event_teams(event_code):
    cache_key = event_code
    ttl = 12 * 3600

    if cache_key in cache["teams"] and is_cache_valid(cache["teams"][cache_key], ttl):
        return jsonify(cache["teams"][cache_key]["data"])

    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/teams?eventCode={event_code}")

    if data is None:
        if cache_key in cache["teams"] and cache["teams"][cache_key]["data"] is not None:
            return jsonify({"cached": True, "data": cache["teams"][cache_key]["data"]})
        abort(503, "FRC API unavailable and no cached data")

    cache["teams"][cache_key] = {"data": data, "timestamp": datetime.now()}
    return jsonify(data)

@api.route('/events/<event_code>/matches', methods=['GET'])
@requires_auth
def get_event_matches(event_code):
    cache_key = event_code
    ttl = 30 * 60

    if cache_key in cache["matches"] and is_cache_valid(cache["matches"][cache_key], ttl):
        return jsonify(cache["matches"][cache_key]["data"])

    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/schedule/{event_code}")

    if data is None:
        if cache_key in cache["matches"] and cache["matches"][cache_key]["data"] is not None:
            return jsonify({"cached": True, "data": cache["matches"][cache_key]["data"]})
        abort(503, "FRC API unavailable and no cached data")

    cache["matches"][cache_key] = {"data": data, "timestamp": datetime.now()}
    return jsonify(data)

# ==================== Module Endpoints ====================

@api.route('/modules/manifest', methods=['GET'])
@requires_auth
def get_modules_manifest():
    if is_cache_valid(cache["modules_manifest"], cache["modules_manifest"]["ttl"]):
        return jsonify(cache["modules_manifest"]["data"])

    manifest = {
        "version": "1.0",
        "modules": [
            {"id": "auto_scoring",        "name": "Autonomous Scoring",  "version": "2024.1", "description": "Track autonomous period scoring"},
            {"id": "teleop_performance",   "name": "Teleop Performance",  "version": "2024.1", "description": "Track teleoperated period performance"},
            {"id": "pit_scouting",         "name": "Pit Scouting",        "version": "2024.1", "description": "Robot capabilities and pit observations"},
        ]
    }

    cache["modules_manifest"]["data"] = manifest
    cache["modules_manifest"]["timestamp"] = datetime.now()
    return jsonify(manifest)

@api.route('/modules/<module_id>', methods=['GET'])
@requires_auth
def get_module_definition(module_id):
    ttl = 24 * 3600
    if module_id in cache["modules"] and is_cache_valid(cache["modules"][module_id], ttl):
        return jsonify(cache["modules"][module_id]["data"])

    module_definitions = {
        "auto_scoring": {
            "id": "auto_scoring",
            "fields": [
                {"name": "mobility",  "type": "boolean", "label": "Left Starting Zone"},
                {"name": "auto_high", "type": "number",  "label": "Auto High Goals"},
                {"name": "auto_low",  "type": "number",  "label": "Auto Low Goals"},
            ]
        },
        "teleop_performance": {
            "id": "teleop_performance",
            "fields": [
                {"name": "teleop_high",     "type": "number", "label": "Teleop High Goals"},
                {"name": "teleop_low",      "type": "number", "label": "Teleop Low Goals"},
                {"name": "defense_rating",  "type": "rating", "label": "Defense Rating", "max": 5},
            ]
        },
        "pit_scouting": {
            "id": "pit_scouting",
            "fields": [
                {"name": "drivetrain", "type": "select", "label": "Drivetrain Type",
                 "options": ["Tank", "Mecanum", "Swerve", "Other"]},
                {"name": "weight", "type": "number", "label": "Robot Weight (lbs)"},
                {"name": "notes",  "type": "text",   "label": "Additional Notes"},
            ]
        },
    }

    if module_id not in module_definitions:
        abort(404, "Module not found")

    module_data = module_definitions[module_id]
    cache["modules"][module_id] = {"data": module_data, "timestamp": datetime.now()}
    return jsonify(module_data)

# ==================== Scouting Report Endpoints ====================

@api.route('/reports/match', methods=['POST'])
@requires_auth
def submit_match_report():
    if not request.json:
        abort(400, "No JSON data provided")

    required_fields = ['event_code', 'match_number', 'team_number']
    for field in required_fields:
        if field not in request.json:
            abort(400, f"Missing required field: {field}")

    # Tag with the submitter's UUID from X-User-Id header
    submitted_by = (request.headers.get("X-User-Id") or "").strip() or "unknown"

    report = {
        **request.json,
        "submitted_by": submitted_by,
        "timestamp": datetime.now().isoformat(),
        "report_id": len(cache["reports_match"]) + 1,
    }

    cache["reports_match"].append(report)

    return jsonify({
        "success": True,
        "report_id": report["report_id"],
        "message": "Match report submitted successfully"
    }), 201

@api.route('/reports/pit', methods=['POST'])
@requires_auth
def submit_pit_report():
    if not request.json:
        abort(400, "No JSON data provided")

    required_fields = ['event_code', 'team_number']
    for field in required_fields:
        if field not in request.json:
            abort(400, f"Missing required field: {field}")

    submitted_by = (request.headers.get("X-User-Id") or "").strip() or "unknown"

    report = {
        **request.json,
        "submitted_by": submitted_by,
        "timestamp": datetime.now().isoformat(),
        "report_id": len(cache["reports_pit"]) + 1,
    }

    cache["reports_pit"].append(report)

    return jsonify({
        "success": True,
        "report_id": report["report_id"],
        "message": "Pit report submitted successfully"
    }), 201

@api.route('/reports/match', methods=['GET'])
@requires_auth
def get_match_reports():
    event_code = request.args.get('event_code')
    team_number = request.args.get('team_number')
    match_number = request.args.get('match_number')

    reports = cache["reports_match"]

    if event_code:
        reports = [r for r in reports if r.get('event_code') == event_code]
    if team_number:
        reports = [r for r in reports if str(r.get('team_number')) == str(team_number)]
    if match_number:
        reports = [r for r in reports if str(r.get('match_number')) == str(match_number)]

    return jsonify({"count": len(reports), "reports": reports})

@api.route('/reports/pit', methods=['GET'])
@requires_auth
def get_pit_reports():
    event_code = request.args.get('event_code')
    team_number = request.args.get('team_number')

    reports = cache["reports_pit"]

    if event_code:
        reports = [r for r in reports if r.get('event_code') == event_code]
    if team_number:
        reports = [r for r in reports if str(r.get('team_number')) == str(team_number)]

    return jsonify({"count": len(reports), "reports": reports})

# ==================== Health Check ====================

@api.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_stats": {
            "events_cached": cache["events"]["data"] is not None,
            "teams_cached": len(cache["teams"]),
            "matches_cached": len(cache["matches"]),
            "match_reports": len(cache["reports_match"]),
            "pit_reports": len(cache["reports_pit"]),
        }
    })