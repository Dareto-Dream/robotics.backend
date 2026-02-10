from flask import Flask
from flask_cors import CORS
from routes.frontend import frontend
from routes.files import files
from routes.api import api
from routes.permissions_roster import permissions_roster
import os

app = Flask(__name__)

CORS(
    app,
    origins=["http://localhost", "https://robotics.deltavdevs.com", "https://tryingflutter-web-deploy-production.up.railway.app"],
    supports_credentials=True,
    allow_headers=["Authorization", "Content-Type", "X-User-Id"],
)


app.register_blueprint(frontend, url_prefix="/")
app.register_blueprint(files, url_prefix="/api/files")
app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(permissions_roster, url_prefix="/api")


if __name__ == "__main__":
    # Railway assigns a random port via the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    # Must bind to 0.0.0.0 so Railway's proxy can reach it
    app.run(host="0.0.0.0", port=port, debug=False)