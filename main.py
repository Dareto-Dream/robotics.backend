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

@app.get("/", response_class=HTMLResponse)
def index():
    def walk(dir_path, base=""):
        html = ""
        for p in sorted(dir_path.iterdir()):
            rel = f"{base}/{p.name}".lstrip("/")

            if p.is_dir():
                html += f"""
                <div class="dir">📁 {p.name}</div>
                <div class="children">
                    {walk(p, rel)}
                </div>
                """
            else:
                size_kb = p.stat().st_size / 1024
                html += f"""
                <div class="file">
                    <a href="/files/{rel}" data-path="{rel}">
                        {p.name}
                    </a>
                    <span class="small">({size_kb:.1f} KB)</span>
                </div>
                """
        return html

    return HTMLResponse(f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Robotics File Server</title>
<style>
body {{
    font-family: system-ui, sans-serif;
    background: #0f1115;
    color: #e5e7eb;
    padding: 20px;
}}
a {{ color: #60a5fa; text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.panel {{
    border: 1px solid #374151;
    padding: 12px;
    margin-bottom: 16px;
    background: #0b0d11;
}}
.dir {{
    font-weight: bold;
    cursor: pointer;
    margin-top: 6px;
}}
.children {{
    margin-left: 16px;
    display: none;
}}
.file {{ margin-left: 16px; }}
.small {{ opacity: .6; font-size: 12px; }}
.progress {{ width: 100%; height: 10px; background: #1f2937; }}
.bar {{ height: 100%; width: 0%; background: #22c55e; }}

.modal {{
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,.75);
    display: none;
    align-items: center;
    justify-content: center;
}}
.modal-content {{
    background: #0b0d11;
    border: 1px solid #374151;
    width: 80%;
    max-width: 900px;
    padding: 12px;
}}
textarea {{
    width: 100%;
    height: 400px;
    font-family: monospace;
    background: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
}}
button, input {{
    background: #111827;
    color: #e5e7eb;
    border: 1px solid #374151;
    padding: 6px 8px;
}}
button:hover {{ background: #1f2937; cursor: pointer; }}
</style>
</head>
<body>

<h1>(～﹃～)~zZ Robotics File Server</h1>
<p class="small">Public reads · Authenticated writes</p>

<div class="panel">
    <h3>⬆ Upload</h3>
    <input type="file" id="fileInput">
    <input type="text" id="uploadPath" placeholder="optional/path/filename.ext">
    <button onclick="upload()">Upload</button>
    <div class="progress"><div class="bar" id="progressBar"></div></div>
</div>

<div class="panel">
    <h3>Files</h3>
    {walk(FILES_DIR)}
</div>

<!-- JSON MODAL -->
<div class="modal" id="jsonModal">
  <div class="modal-content">
    <h3 id="jsonTitle"></h3>
    <textarea id="jsonEditor"></textarea>
    <br><br>
    <button onclick="saveJSON()">Save</button>
    <button onclick="closeJSON()">Close</button>
    <span class="small" id="jsonStatus"></span>
  </div>
</div>

<script>
let currentJSONPath = null;

// folder toggle
document.querySelectorAll(".dir").forEach(dir => {{
    dir.onclick = () => {{
        const next = dir.nextElementSibling;
        next.style.display =
            next.style.display === "none" ? "block" : "none";
    }};
}});

// JSON interception
document.addEventListener("click", e => {{
    const a = e.target.closest("a[data-path]");
    if (!a) return;

    const path = a.dataset.path;
    if (path.endsWith(".json")) {{
        e.preventDefault();
        openJSON(path);
    }}
}});

function upload() {{
    const file = fileInput.files[0];
    let path = uploadPath.value.trim();
    if (!file) return alert("Select a file");
    if (!path) path = file.name;

    const form = new FormData();
    form.append("file", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/upload/" + path);

    xhr.upload.onprogress = e => {{
        if (e.lengthComputable)
            progressBar.style.width = (e.loaded / e.total * 100) + "%";
    }};
    xhr.onload = () => location.reload();
    xhr.send(form);
}}

function openJSON(path) {{
    currentJSONPath = path;
    jsonTitle.textContent = path;
    fetch("/files/" + path)
        .then(r => r.text())
        .then(t => {{
            jsonEditor.value = JSON.stringify(JSON.parse(t), null, 2);
            jsonModal.style.display = "flex";
        }});
}}

function closeJSON() {{
    jsonModal.style.display = "none";
}}

async function saveJSON() {{
    try {{
        const data = JSON.parse(jsonEditor.value);
        const blob = new Blob(
            [JSON.stringify(data, null, 2)],
            {{ type: "application/json" }}
        );
        const form = new FormData();
        form.append("file", blob);

        await fetch("/upload/" + currentJSONPath, {{
            method: "POST",
            body: form
        }});

        jsonStatus.textContent = "Saved";
    }} catch {{
        jsonStatus.textContent = "Invalid JSON";
    }}
}}
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
