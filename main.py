from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import secrets
import shutil

# =====================
# APP SETUP
# =====================

app = FastAPI()
security = HTTPBasic()

# =====================
# CORS CONFIG
# =====================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "https://robotics.deltavdevs.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

# =====================
# CONFIG
# =====================

FILES_DIR = Path("files")
FILES_DIR.mkdir(exist_ok=True)

USERNAME = "admin"
PASSWORD = "changeme"  # CHANGE THIS

# =====================
# AUTH
# =====================

def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(credentials.username, USERNAME)
    pass_ok = secrets.compare_digest(credentials.password, PASSWORD)

    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

# =====================
# PUBLIC FILE ACCESS
# =====================

app.mount("/files", StaticFiles(directory=FILES_DIR), name="files")

@app.get("/")
def index():
    files = [f.name for f in FILES_DIR.iterdir() if f.is_file()]
    links = "<br>".join(f'<a href="/files/{f}">{f}</a>' for f in files)

    return HTMLResponse(f"""
        <h2>Public File Server</h2>
        {links}
        <hr>
        <p>Uploads require authentication.</p>
    """)

# =====================
# PROTECTED UPLOAD
# =====================

@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    _: HTTPBasicCredentials = Depends(check_auth)
):
    target = FILES_DIR / file.filename
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"updated": file.filename}
