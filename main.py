from flask import Flask
from flask_cors import CORS
from routes.frontend import frontend
from routes.files import files
from routes.api import api
from routes.permissions_roster import permissions_roster
from routes.auth import auth
import os

from data.db import init_db
from data.auth_db import init_auth_db

app = Flask(__name__)

@app.before_serving
def startup():
    from data.db import init_db
    from data.auth_db import init_auth_db

    print("Initializing databases...")
    init_db()
    init_auth_db()

CORS(
    app,
    origins=["http://localhost", "https://robotics.deltavdevs.com"],
    supports_credentials=True,
    allow_headers=["Authorization", "Content-Type"],
)

app.register_blueprint(frontend, url_prefix="/")
app.register_blueprint(files, url_prefix="/api/files")
app.register_blueprint(api, url_prefix="/api")
app.register_blueprint(permissions_roster, url_prefix="/api")
app.register_blueprint(auth, url_prefix="/auth")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
