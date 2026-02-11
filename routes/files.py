from flask import Blueprint, request, jsonify, abort
import shutil
from helpers import safe_path
from auth.dependencies import require_auth
from data.users_repo import ensure_user

files = Blueprint('files', __name__)


@files.route('/mkdir/<path:path>', methods=['POST'])
@require_auth
def make_dir(current_user, path):
    ensure_user(current_user["id"])
    
    target = safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return jsonify({"created": path})


@files.route('/upload/<path:path>', methods=['POST'])
@require_auth
def upload_file(current_user, path):
    ensure_user(current_user["id"])
    
    if 'file' not in request.files:
        abort(400, "No file provided")
    
    file = request.files['file']
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    
    file.save(target)
    return jsonify({"uploaded": path})


@files.route('/delete/<path:path>', methods=['DELETE'])
@require_auth
def delete_path(current_user, path):
    ensure_user(current_user["id"])
    
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
