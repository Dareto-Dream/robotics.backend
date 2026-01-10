from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pathlib import Path
import secrets
import shutil

app = FastAPI()
security = HTTPBasic()

# ===== CONFIG =====
FILES_DIR = Path("files")
FILES_DIR.mkdir(exist_ok=True)

USERNAME = "admin"
PASSWORD = "changeme"  # change this
# ==================

def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_user = secrets.compare_digest(credentials.username, USERNAME)
    correct_pass = secrets.compare_digest(credentials.password, PASSWORD)

    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

# Public file access
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

# ===== PROTECTED WRITE ENDPOINT =====
@app.post("/upload")
def upload_file(
    file: UploadFile = File(...),
    _: HTTPBasicCredentials = Depends(check_auth)
):
    target = FILES_DIR / file.filename
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"updated": file.filename}
