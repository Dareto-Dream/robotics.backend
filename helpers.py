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
    Generate an HTML file tree for the given directory
    """
    def _walk_recursive(dir_path, indent=0):
        html_parts = []
        try:
            items = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name))
            for item in items:
                rel_path = item.relative_to(FILES_DIR)
                indent_str = "  " * indent
                
                if item.is_dir():
                    html_parts.append(f'{indent_str}<li class="dir">{item.name}/')
                    html_parts.append(f'{indent_str}  <ul>')
                    html_parts.append(_walk_recursive(item, indent + 2))
                    html_parts.append(f'{indent_str}  </ul>')
                    html_parts.append(f'{indent_str}</li>')
                else:
                    file_size = item.stat().st_size
                    size_kb = file_size / 1024
                    html_parts.append(
                        f'{indent_str}<li class="file">'
                        f'<a href="/files/{rel_path}">{item.name}</a> '
                        f'<span class="size">({size_kb:.1f} KB)</span>'
                        f'</li>'
                    )
        except PermissionError:
            html_parts.append(f'{indent_str}<li class="error">Permission denied</li>')
        
        return '\n'.join(html_parts)
    
    return f'<ul class="file-tree">\n{_walk_recursive(directory)}\n</ul>'