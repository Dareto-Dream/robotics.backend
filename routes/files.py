from flask import Blueprint, request, jsonify, abort
from werkzeug.security import check_password_hash
from functools import wraps
import secrets
import shutil
from helpers import safe_path, USERNAME, PASSWORD

files = Blueprint('files', __name__)

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

@files.route('/mkdir/<path:path>', methods=['POST'])
@requires_auth
def make_dir(path):
    target = safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return jsonify({"created": path})

@files.route('/upload/<path:path>', methods=['POST'])
@requires_auth
def upload_file(path):
    if 'file' not in request.files:
        abort(400, "No file provided")
    
    file = request.files['file']
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    
    file.save(target)
    return jsonify({"updated": path})

@files.route('/delete/<path:path>', methods=['DELETE'])
@requires_auth
def delete_path(path):
    target = safe_path(path)
    
    if not target.exists():
        abort(404, "Path does not exist")
    
    if target.is_file():
        target.unlink()
        return jsonify({"deleted_file": path})
    
    if target.is_dir():
        shutil.rmtree(target)
        return jsonify({"deleted_directory": path})
    
    abort(400, "Invalid target")