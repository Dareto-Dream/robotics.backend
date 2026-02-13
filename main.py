from flask import Flask
from flask_cors import CORS
from routes.api import api
from routes.permissions_roster import permissions_roster
from routes.auth import auth
from routes.devices import devices
from data.startup import wait_for_databases
from data.db import init_db
from data.auth_db import init_auth_db
import os

app = Flask(__name__)

# ---------- CORS ----------
CORS(
    app,
    origins=os.environ.get("CORS_ORIGINS", "http://localhost").split(","),
    supports_credentials=True,
    allow_headers=["Authorization", "Content-Type"],
)

# ---------- ROUTES ----------
app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(permissions_roster, url_prefix="/api")
app.register_blueprint(auth, url_prefix="/auth")
app.register_blueprint(devices, url_prefix="/auth/devices")

# ---------- LOCAL RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
