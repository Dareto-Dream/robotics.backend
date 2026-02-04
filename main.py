from flask import Flask
from flask_cors import CORS
from routes.frontend import frontend
from routes.files import files
import os

app = Flask(__name__)

CORS(
    app,
    origins=["http://localhost", "https://robotics.deltavdevs.com"],
    supports_credentials=True,
    allow_headers=["Authorization", "Content-Type"],
)


app.register_blueprint(frontend, url_prefix="/")
app.register_blueprint(files, url_prefix="/api/files")


if __name__ == "__main__":
    # Railway assigns a random port via the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    # Must bind to 0.0.0.0 so Railway’s proxy can reach it
    app.run(host="0.0.0.0", port=port, debug=False)