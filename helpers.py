from pathlib import Path
from flask import abort
import os

FILES_DIR = Path("files").resolve()
FILES_DIR.mkdir(exist_ok=True)

STATIC_DIR = Path("static").resolve()
STATIC_DIR.mkdir(exist_ok=True)

TEMPLATE = Path("index.html")

USERNAME = os.getenv("FILE_SERVER_USER", "admin")
PASSWORD = os.getenv("FILE_SERVER_PASS", "changeme")

def safe_path(rel_path: str) -> Path:
    target = (FILES_DIR / rel_path).resolve()
    if not str(target).startswith(str(FILES_DIR)):
        abort(400, "Invalid path")
    return target

def format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"

def get_ext(name: str) -> str:
    parts = name.rsplit('.', 1)
    return parts[1].lower() if len(parts) > 1 else ''

FOLDER_SVG = (
    '<svg class="ico" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 7a2 2 0 0 1 2-2h5l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"/>'
    '</svg>'
)

FILE_SVG = (
    '<svg class="ico" viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 2v6h6"/>'
    '</svg>'
)

COPY_SVG = (
    '<svg viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="9" y="9" width="13" height="13" rx="2"/>'
    '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'
    '</svg>'
)

TRASH_SVG = (
    '<svg viewBox="0 0 24 24" fill="none"'
    ' stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M3 6h18"/>'
    '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
    '</svg>'
)

def walk(dir_path: Path, base: str = "") -> str:
    html = ""
    for p in sorted(dir_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        rel = f"{base}/{p.name}".lstrip("/")

        if p.is_dir():
            html += (
                f'<div class="dir" data-name="{p.name.lower()}">'
                f'<span class="chevron">\u203a</span>'
                f'{FOLDER_SVG}'
                f'<span class="dir-name">{p.name}</span>'
                f'</div>'
                f'<div class="children">{walk(p, rel)}</div>'
            )
        else:
            ext  = get_ext(p.name)
            size = format_size(p.stat().st_size)
            html += (
                f'<div class="file" data-name="{p.name.lower()}" data-path="{rel}">'
                f'{FILE_SVG}'
                f'<a href="/files/{rel}" class="file-name" data-path="{rel}">{p.name}</a>'
                f'<span class="ext-badge" data-ext="{ext}">.{ext}</span>'
                f'<span class="file-size">{size}</span>'
                f'<span class="file-actions">'
                f'<button class="act act-copy" data-url="/files/{rel}" title="Copy link">{COPY_SVG}</button>'
                f'<button class="act act-delete" data-path="{rel}" title="Delete">{TRASH_SVG}</button>'
                f'</span>'
                f'</div>'
            )
    return html