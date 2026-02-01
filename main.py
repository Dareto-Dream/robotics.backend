from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import secrets
import shutil
import os

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
# DIRECTORIES
# =====================

FILES_DIR  = Path("files").resolve()
FILES_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path("static").resolve()
STATIC_DIR.mkdir(exist_ok=True)

TEMPLATE   = Path("index.html")

# =====================
# AUTH CONFIG (ENV)
# =====================

USERNAME = os.getenv("FILE_SERVER_USER", "admin")
PASSWORD = os.getenv("FILE_SERVER_PASS", "changeme")

# =====================
# AUTH CHECK
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
# SAFETY: PATH RESOLUTION
# =====================

def safe_path(rel_path: str) -> Path:
    target = (FILES_DIR / rel_path).resolve()
    if not str(target).startswith(str(FILES_DIR)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target

# =====================
# FILE-TREE HTML GENERATOR
# =====================

FOLDER_CLOSED_SVG = (
    '<svg class="ico ico-closed" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
    ' stroke-linejoin="round" aria-hidden="true">'
    '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>'
    '</svg>'
)

FOLDER_OPEN_SVG = (
    '<svg class="ico ico-open" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
    ' stroke-linejoin="round" aria-hidden="true">'
    '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h8"/>'
    '<path d="M3 9h18l-2 10H5L3 9z"/>'
    '</svg>'
)

FILE_SVG = (
    '<svg class="ico" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round"'
    ' stroke-linejoin="round" aria-hidden="true">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 2v6h6"/>'
    '</svg>'
)


def walk(dir_path: Path, base: str = "") -> str:
    html = ""
    for p in sorted(dir_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        rel = f"{base}/{p.name}".lstrip("/")

        if p.is_dir():
            html += (
                f'<div class="dir">'
                f'<span class="folder-icon">{FOLDER_CLOSED_SVG}{FOLDER_OPEN_SVG}</span>'
                f'<span class="name">{p.name}</span>'
                f'</div>'
                f'<div class="children">{walk(p, rel)}</div>'
            )
        else:
            size_kb = p.stat().st_size / 1024
            html += (
                f'<div class="file">'
                f'{FILE_SVG}'
                f'<a href="/files/{rel}" data-path="{rel}">{p.name}</a>'
                f'<span class="size-badge">{size_kb:.1f} KB</span>'
                f'</div>'
            )
    return html

# =====================
# STATIC ASSETS & INDEX
# =====================

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/files",  StaticFiles(directory=FILES_DIR),  name="files")


@app.get("/", response_class=HTMLResponse)
def index():
    html = TEMPLATE.read_text(encoding="utf-8")
    return HTMLResponse(html.replace("<!-- FILELIST -->", walk(FILES_DIR)))

# =====================
# PROTECTED: CREATE DIRECTORY
# =====================

@app.post("/mkdir/{path:path}")
def make_dir(
    path: str,
    _: HTTPBasicCredentials = Depends(check_auth)
):
    target = safe_path(path)
    target.mkdir(parents=True, exist_ok=True)
    return {"created": path}

# =====================
# PROTECTED: UPLOAD FILE
# =====================

@app.post("/upload/{path:path}")
def upload_file(
    path: str,
    file: UploadFile = File(...),
    _: HTTPBasicCredentials = Depends(check_auth)
):
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"updated": path}

# =====================
# PROTECTED: DELETE FILE OR DIRECTORY
# =====================

@app.delete("/delete/{path:path}")
def delete_path(
    path: str,
    _: HTTPBasicCredentials = Depends(check_auth)
):
    target = safe_path(path)

    if not target.exists():
        raise HTTPException(status_code=404, detail="Path does not exist")

    if target.is_file():
        target.unlink()
        return {"deleted_file": path}

    if target.is_dir():
        shutil.rmtree(target)
        return {"deleted_directory": path}

    raise HTTPException(status_code=400, detail="Invalid target")