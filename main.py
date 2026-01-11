from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, status, Response
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
# FILE STORAGE
# =====================

FILES_DIR = Path("files").resolve()
FILES_DIR.mkdir(exist_ok=True)

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
# PUBLIC FILE ACCESS
# =====================

app.mount("/files", StaticFiles(directory=FILES_DIR), name="files")

@app.get("/")
def index():
    return HTMLResponse("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Robotics File Server</title>
<style>
body {
    font-family: system-ui, sans-serif;
    background: #0f1115;
    color: #e5e7eb;
    padding: 20px;
}
h1 { margin-bottom: 6px; }
a { color: #60a5fa; text-decoration: none; }
a:hover { text-decoration: underline; }
input, textarea, button {
    background: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    padding: 6px 8px;
}
button { cursor: pointer; }
button:hover { background: #1f2937; }
.panel {
    border: 1px solid #374151;
    padding: 12px;
    margin-bottom: 16px;
    background: #0b0d11;
}
.progress {
    width: 100%;
    background: #1f2937;
    height: 12px;
    margin-top: 6px;
}
.bar {
    height: 100%;
    width: 0%;
    background: #22c55e;
}
textarea {
    width: 100%;
    height: 300px;
    font-family: monospace;
    margin-top: 8px;
}
.small { font-size: 12px; opacity: 0.6; }
</style>
</head>
<body>

<h1>(～﹃～)~zZ Robotics File Server</h1>
<p class="small">Public reads · Authenticated writes</p>

<div class="panel">
    <h3>⬆ Upload File</h3>
    <input type="file" id="fileInput"><br><br>
    <input type="text" id="uploadPath" placeholder="optional/path/filename.ext" style="width: 320px;">
    <br><br>
    <button onclick="upload()">Upload</button>
    <div class="progress"><div class="bar" id="progressBar"></div></div>
</div>

<div class="panel">
    <h3>Inline JSON Editor</h3>
    <input type="text" id="jsonPath" placeholder="path/to/file.json" style="width: 320px;">
    <button onclick="loadJSON()">Load</button>
    <textarea id="jsonEditor" placeholder="JSON will appear here"></textarea>
    <br>
    <button onclick="saveJSON()">Save JSON</button>
    <div class="small" id="jsonStatus"></div>
</div>

<p class="small">
Browse files at <a href="/files/">/files/</a>
</p>

<script>
function upload() {
    const file = document.getElementById("fileInput").files[0];
    let path = document.getElementById("uploadPath").value.trim();
    const bar = document.getElementById("progressBar");

    if (!file) return alert("Select a file");

    if (!path) path = file.name;

    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload/" + path);

    xhr.upload.onprogress = e => {
        if (e.lengthComputable) {
            bar.style.width = (e.loaded / e.total * 100) + "%";
        }
    };

    xhr.onload = () => {
        if (xhr.status === 200) location.reload();
        else alert("Upload failed");
    };

    xhr.send(form);
}

async function loadJSON() {
    const path = document.getElementById("jsonPath").value.trim();
    const status = document.getElementById("jsonStatus");
    if (!path.endsWith(".json")) {
        status.textContent = "Not a JSON file";
        return;
    }

    const res = await fetch("/files/" + path);
    if (!res.ok) {
        status.textContent = "Failed to load file";
        return;
    }

    const text = await res.text();
    try {
        const obj = JSON.parse(text);
        document.getElementById("jsonEditor").value =
            JSON.stringify(obj, null, 2);
        status.textContent = "Loaded";
    } catch {
        status.textContent = "Invalid JSON";
    }
}

async function saveJSON() {
    const path = document.getElementById("jsonPath").value.trim();
    const status = document.getElementById("jsonStatus");
    const text = document.getElementById("jsonEditor").value;

    let parsed;
    try {
        parsed = JSON.parse(text);
    } catch {
        status.textContent = "JSON syntax error";
        return;
    }

    const blob = new Blob(
        [JSON.stringify(parsed, null, 2)],
        { type: "application/json" }
    );

    const form = new FormData();
    form.append("file", blob, path.split("/").pop());

    const res = await fetch("/upload/" + path, {
        method: "POST",
        body: form
    });

    status.textContent = res.ok ? "Saved" : "Save failed";
}
</script>

</body>
</html>
""")

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
