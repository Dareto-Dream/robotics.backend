from pathlib import Path
import os

# Directory paths
BASE_DIR = Path(__file__).parent
FILES_DIR = BASE_DIR / "files"
STATIC_DIR = BASE_DIR / "static"
TEMPLATE = BASE_DIR  / "index.html"

# Authentication credentials (in production, use environment variables)
USERNAME = os.environ.get("API_USERNAME", "admin")
PASSWORD = os.environ.get("API_PASSWORD", "changeme")

# Ensure directories exist
FILES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

def safe_path(path_str):
    """
    Resolve a path safely within FILES_DIR to prevent directory traversal
    """
    requested = Path(path_str)
    resolved = (FILES_DIR / requested).resolve()
    
    # Ensure the resolved path is within FILES_DIR
    if not str(resolved).startswith(str(FILES_DIR.resolve())):
        raise ValueError("Invalid path: directory traversal attempt")
    
    return resolved

def walk(directory):
    """
    Generate an HTML file tree for the given directory.
    
    The JS extractFileTreeFromElement() parser expects:
      - <div class="dir" data-name="..."><span class="dir-name">...</span></div>
        followed by <div class="children">...</div> for subdirectories
      - <div class="file" data-path="..." data-name="...">
          <span class="file-name" data-path="...">...</span>
          <span class="file-size">...</span>
        </div> for files
    """
    def _format_size(size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    def _walk_recursive(dir_path):
        html_parts = []
        try:
            items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for item in items:
                rel_path = item.relative_to(FILES_DIR)
                name = item.name

                if item.is_dir():
                    html_parts.append(
                        f'<div class="dir" data-name="{name}">'
                        f'<span class="dir-name">{name}</span>'
                        f'</div>'
                    )
                    children_html = _walk_recursive(item)
                    if children_html:
                        html_parts.append(f'<div class="children">{children_html}</div>')
                else:
                    file_size = item.stat().st_size
                    size_str = _format_size(file_size)
                    path_str = str(rel_path)
                    html_parts.append(
                        f'<div class="file" data-path="{path_str}" data-name="{name}">'
                        f'<span class="file-name" data-path="{path_str}">{name}</span>'
                        f'<span class="file-size">{size_str}</span>'
                        f'</div>'
                    )
        except PermissionError:
            html_parts.append('<div class="error">Permission denied</div>')

        return '\n'.join(html_parts)

    return _walk_recursive(directory)