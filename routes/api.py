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
FRC_API_USERNAME = os.environ.get("FRC_API_USERNAME", "changeme")  # Configure with your FRC API credentials
FRC_API_TOKEN = os.environ.get("FRC_API_TOKEN", "changeme")

# Cache storage (in production, use Redis or similar)
cache = {
    "events": {"data": None, "timestamp": None, "ttl": 6 * 3600},  # 6 hours
    "teams": {},  # event_code: {data, timestamp}
    "matches": {},  # event_code: {data, timestamp}
    "modules_manifest": {"data": None, "timestamp": None, "ttl": 24 * 3600},  # 1 day
    "modules": {},  # module_id: {data, timestamp}
    "reports_match": [],
    "reports_pit": [],
    "rosters": {}  # team_code: roster data
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
    """Check if cached data is still valid"""
    if cache_entry.get("data") is None or cache_entry.get("timestamp") is None:
        return False
    age = (datetime.now() - cache_entry["timestamp"]).total_seconds()
    return age < ttl

def fetch_from_frc_api(endpoint):
    """Fetch data from FRC API with error handling"""
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
    """
    GET /api/events
    List all FRC events for the season
    Cache: 6 hours
    """
    # Check cache
    if is_cache_valid(cache["events"], cache["events"]["ttl"]):
        return jsonify(cache["events"]["data"])
    
    # Fetch from FRC API
    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/events")
    
    if data is None:
        # Return cached data if API fails
        if cache["events"]["data"] is not None:
            return jsonify({
                "cached": True,
                "data": cache["events"]["data"]
            })
        abort(503, "FRC API unavailable and no cached data")
    
    # Update cache
    cache["events"]["data"] = data
    cache["events"]["timestamp"] = datetime.now()
    
    return jsonify(data)

@api.route('/events/<event_code>/teams', methods=['GET'])
@requires_auth
def get_event_teams(event_code):
    """
    GET /api/events/{code}/teams
    Teams registered for a specific event
    Cache: 12 hours
    """
    cache_key = event_code
    ttl = 12 * 3600  # 12 hours
    
    # Check cache
    if cache_key in cache["teams"] and is_cache_valid(cache["teams"][cache_key], ttl):
        return jsonify(cache["teams"][cache_key]["data"])
    
    # Fetch from FRC API
    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/teams?eventCode={event_code}")
    
    if data is None:
        # Return cached data if API fails
        if cache_key in cache["teams"] and cache["teams"][cache_key]["data"] is not None:
            return jsonify({
                "cached": True,
                "data": cache["teams"][cache_key]["data"]
            })
        abort(503, "FRC API unavailable and no cached data")
    
    # Update cache
    cache["teams"][cache_key] = {
        "data": data,
        "timestamp": datetime.now()
    }
    
    return jsonify(data)

@api.route('/events/<event_code>/matches', methods=['GET'])
@requires_auth
def get_event_matches(event_code):
    """
    GET /api/events/{code}/matches
    Match schedule and results for an event
    Cache: 30 minutes
    """
    cache_key = event_code
    ttl = 30 * 60  # 30 minutes
    
    # Check cache
    if cache_key in cache["matches"] and is_cache_valid(cache["matches"][cache_key], ttl):
        return jsonify(cache["matches"][cache_key]["data"])
    
    # Fetch from FRC API
    season = request.args.get('season', datetime.now().year)
    data = fetch_from_frc_api(f"{season}/schedule/{event_code}")
    
    if data is None:
        # Return cached data if API fails
        if cache_key in cache["matches"] and cache["matches"][cache_key]["data"] is not None:
            return jsonify({
                "cached": True,
                "data": cache["matches"][cache_key]["data"]
            })
        abort(503, "FRC API unavailable and no cached data")
    
    # Update cache
    cache["matches"][cache_key] = {
        "data": data,
        "timestamp": datetime.now()
    }
    
    return jsonify(data)

# ==================== Module Endpoints ====================

@api.route('/modules/manifest', methods=['GET'])
@requires_auth
def get_modules_manifest():
    """
    GET /api/modules/manifest
    Module manifest listing all available modules
    Cache: 1 day
    """
    # Check cache
    if is_cache_valid(cache["modules_manifest"], cache["modules_manifest"]["ttl"]):
        return jsonify(cache["modules_manifest"]["data"])
    
    # In production, this would fetch from a modules directory or database
    # For now, returning a sample manifest
    manifest = {
        "version": "1.0",
        "modules": [
            {
                "id": "auto_scoring",
                "name": "Autonomous Scoring",
                "version": "2024.1",
                "description": "Track autonomous period scoring"
            },
            {
                "id": "teleop_performance",
                "name": "Teleop Performance",
                "version": "2024.1",
                "description": "Track teleoperated period performance"
            },
            {
                "id": "pit_scouting",
                "name": "Pit Scouting",
                "version": "2024.1",
                "description": "Robot capabilities and pit observations"
            }
        ]
    }
    
    # Update cache
    cache["modules_manifest"]["data"] = manifest
    cache["modules_manifest"]["timestamp"] = datetime.now()
    
    return jsonify(manifest)

@api.route('/modules/<module_id>', methods=['GET'])
@requires_auth
def get_module_definition(module_id):
    """
    GET /api/modules/{id}
    Individual module JSON definition
    Cache: 1 day
    """
    ttl = 24 * 3600  # 1 day
    
    # Check cache
    if module_id in cache["modules"] and is_cache_valid(cache["modules"][module_id], ttl):
        return jsonify(cache["modules"][module_id]["data"])
    
    # In production, load from files or database
    # Sample module definition
    module_definitions = {
        "auto_scoring": {
            "id": "auto_scoring",
            "fields": [
                {"name": "mobility", "type": "boolean", "label": "Left Starting Zone"},
                {"name": "auto_high", "type": "number", "label": "Auto High Goals"},
                {"name": "auto_low", "type": "number", "label": "Auto Low Goals"}
            ]
        },
        "teleop_performance": {
            "id": "teleop_performance",
            "fields": [
                {"name": "teleop_high", "type": "number", "label": "Teleop High Goals"},
                {"name": "teleop_low", "type": "number", "label": "Teleop Low Goals"},
                {"name": "defense_rating", "type": "rating", "label": "Defense Rating", "max": 5}
            ]
        },
        "pit_scouting": {
            "id": "pit_scouting",
            "fields": [
                {"name": "drivetrain", "type": "select", "label": "Drivetrain Type", 
                 "options": ["Tank", "Mecanum", "Swerve", "Other"]},
                {"name": "weight", "type": "number", "label": "Robot Weight (lbs)"},
                {"name": "notes", "type": "text", "label": "Additional Notes"}
            ]
        }
    }
    
    if module_id not in module_definitions:
        abort(404, "Module not found")
    
    module_data = module_definitions[module_id]
    
    # Update cache
    cache["modules"][module_id] = {
        "data": module_data,
        "timestamp": datetime.now()
    }
    
    return jsonify(module_data)

# ==================== Scouting Report Endpoints ====================

@api.route('/reports/match', methods=['POST'])
@requires_auth
def submit_match_report():
    """
    POST /api/reports/match
    Submit a match scouting report
    Persistent storage
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    required_fields = ['event_code', 'match_number', 'team_number']
    for field in required_fields:
        if field not in request.json:
            abort(400, f"Missing required field: {field}")
    
    report = {
        **request.json,
        "timestamp": datetime.now().isoformat(),
        "report_id": len(cache["reports_match"]) + 1
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
    """
    POST /api/reports/pit
    Submit a pit scouting report
    Persistent storage
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    required_fields = ['event_code', 'team_number']
    for field in required_fields:
        if field not in request.json:
            abort(400, f"Missing required field: {field}")
    
    report = {
        **request.json,
        "timestamp": datetime.now().isoformat(),
        "report_id": len(cache["reports_pit"]) + 1
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
    """
    GET /api/reports/match
    Retrieve match reports with optional filtering
    """
    event_code = request.args.get('event_code')
    team_number = request.args.get('team_number')
    match_number = request.args.get('match_number')
    
    reports = cache["reports_match"]
    
    # Apply filters
    if event_code:
        reports = [r for r in reports if r.get('event_code') == event_code]
    if team_number:
        reports = [r for r in reports if str(r.get('team_number')) == str(team_number)]
    if match_number:
        reports = [r for r in reports if str(r.get('match_number')) == str(match_number)]
    
    return jsonify({
        "count": len(reports),
        "reports": reports
    })

@api.route('/reports/pit', methods=['GET'])
@requires_auth
def get_pit_reports():
    """
    GET /api/reports/pit
    Retrieve pit reports with optional filtering
    """
    event_code = request.args.get('event_code')
    team_number = request.args.get('team_number')
    
    reports = cache["reports_pit"]
    
    # Apply filters
    if event_code:
        reports = [r for r in reports if r.get('event_code') == event_code]
    if team_number:
        reports = [r for r in reports if str(r.get('team_number')) == str(team_number)]
    
    return jsonify({
        "count": len(reports),
        "reports": reports
    })

# ==================== Roster Endpoints ====================

@api.route('/teams/<team_code>/roster', methods=['GET'])
@requires_auth
def get_team_roster(team_code):
    """
    GET /api/teams/{code}/roster
    Get roster for a team
    Persistent storage
    """
    if team_code not in cache["rosters"]:
        return jsonify({
            "team_code": team_code,
            "members": []
        })
    
    return jsonify(cache["rosters"][team_code])

@api.route('/teams/<team_code>/roster', methods=['POST'])
@requires_auth
def register_roster_member(team_code):
    """
    POST /api/teams/{code}/roster
    Register a new roster member
    Persistent storage
    """
    if not request.json:
        abort(400, "No JSON data provided")
    
    required_fields = ['name', 'role']
    for field in required_fields:
        if field not in request.json:
            abort(400, f"Missing required field: {field}")
    
    # Initialize roster if it doesn't exist
    if team_code not in cache["rosters"]:
        cache["rosters"][team_code] = {
            "team_code": team_code,
            "members": []
        }
    
    member = {
        **request.json,
        "member_id": len(cache["rosters"][team_code]["members"]) + 1,
        "registered_at": datetime.now().isoformat()
    }
    
    cache["rosters"][team_code]["members"].append(member)
    
    return jsonify({
        "success": True,
        "member_id": member["member_id"],
        "message": "Roster member registered successfully"
    }), 201

# ==================== Health Check ====================

@api.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "cache_stats": {
            "events_cached": cache["events"]["data"] is not None,
            "teams_cached": len(cache["teams"]),
            "matches_cached": len(cache["matches"]),
            "match_reports": len(cache["reports_match"]),
            "pit_reports": len(cache["reports_pit"]),
            "rosters": len(cache["rosters"])
        }
    })