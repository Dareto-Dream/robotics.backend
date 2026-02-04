from flask import Blueprint, send_from_directory
from helpers import FILES_DIR, STATIC_DIR, TEMPLATE, walk

frontend = Blueprint('frontend', __name__)

@frontend.route('/')
def index():
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("<!-- FILELIST -->", walk(FILES_DIR))

@frontend.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(STATIC_DIR, filename)

@frontend.route('/files/<path:filename>')
def serve_file(filename):
    return send_from_directory(FILES_DIR, filename)