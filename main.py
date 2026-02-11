from flask import Flask
from flask_cors import CORS
from routes.frontend import frontend
from routes.files import files
from routes.api import api
from routes.permissions_roster import permissions_roster
import os

from data.db import init_db

app = Flask(__name__)

# Initialize PostgreSQL tables at boot
init_db()

CORS(
    app,
    origins=["http://localhost", "https://robotics.deltavdevs.com"],
    supports_credentials=True,
    allow_headers=["Authorization", "Content-Type", "X-User-Id"],
)

app.register_blueprint(frontend, url_prefix="/")
app.register_blueprint(files, url_prefix="/api/files")
app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(permissions_roster, url_prefix="/api")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
