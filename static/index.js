/* ═══════════════════════════════════════════════════
   FILE SERVER — CLIENT
   ═══════════════════════════════════════════════════ */

// ── Auth (prompted once, cached for the session) ──
let _auth = null;

function auth() {
  if (_auth) return _auth;
  const u = prompt('Username');
  if (!u) return null;
  const p = prompt('Password');
  if (!p) return null;
  _auth = 'Basic ' + btoa(u + ':' + p);
  return _auth;
}

// ── Folder toggle ──────────────────────────────────
document.querySelectorAll('.dir').forEach(dir => {
  dir.addEventListener('click', () => {
    dir.classList.toggle('open');
    dir.nextElementSibling.classList.toggle('open');
  });
});

// ── Expand / Collapse All ──────────────────────────
let _expanded = false;

document.getElementById('toggleExpand').addEventListener('click', () => {
  _expanded = !_expanded;
  document.querySelectorAll('.dir').forEach(d => d.classList.toggle('open', _expanded));
  document.querySelectorAll('.children').forEach(c => c.classList.toggle('open', _expanded));
});

// ── Empty state on initial load ────────────────────
if (document.querySelectorAll('.file').length === 0) {
  document.getElementById('emptyState').style.display = 'block';
  document.getElementById('emptyState').textContent = 'Empty — upload a file to get started';
}

// ── Search / Filter ────────────────────────────────
const searchInput = document.getElementById('searchInput');
const emptyState  = document.getElementById('emptyState');

searchInput.addEventListener('input', function () {
  const q = this.value.trim().toLowerCase();

  // Full reset
  document.querySelectorAll('.dir').forEach(d => { d.style.display = ''; d.classList.remove('open'); });
  document.querySelectorAll('.children').forEach(c => { c.style.display = ''; c.classList.remove('open'); });
  document.querySelectorAll('.file').forEach(f => f.style.display = '');
  emptyState.style.display = 'none';

  if (!q) return;

  // Hide everything, then selectively show matches + their ancestors
  document.querySelectorAll('.dir').forEach(d => d.style.display = 'none');
  document.querySelectorAll('.children').forEach(c => c.style.display = 'none');

  let found = false;

  document.querySelectorAll('.file').forEach(file => {
    const match = (file.dataset.name || '').includes(q) || (file.dataset.path || '').includes(q);
    file.style.display = match ? '' : 'none';
    if (!match) return;
    found = true;

    // Walk up the DOM, reveal every ancestor .children and its .dir
    let el = file.parentElement;
    while (el) {
      if (el.classList.contains('children')) {
        el.style.display = '';
        el.classList.add('open');
        const prev = el.previousElementSibling;
        if (prev && prev.classList.contains('dir')) {
          prev.style.display = '';
          prev.classList.add('open');
        }
      }
      el = el.parentElement;
    }
  });

  emptyState.style.display = found ? 'none' : 'block';
});

// ── Upload ─────────────────────────────────────────
const uploadPanel   = document.getElementById('uploadPanel');
const fileInput     = document.getElementById('fileInput');
const uploadName    = document.getElementById('uploadName');
const uploadConfirm = document.getElementById('uploadConfirm');
const uploadCancel  = document.getElementById('uploadCancel');
const progressBar   = document.getElementById('progressBar');

let _pendingFile = null; // holds the file from picker OR drag-drop

document.getElementById('uploadTrigger').addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) showPending(fileInput.files[0]);
});

function showPending(file) {
  _pendingFile = file;
  uploadName.textContent = file.name;
  uploadPanel.classList.add('visible');
}

uploadCancel.addEventListener('click', () => {
  _pendingFile = null;
  fileInput.value = '';
  progressBar.style.width = '0%';
  uploadPanel.classList.remove('visible');
});

uploadConfirm.addEventListener('click', () => {
  if (!_pendingFile) return;
  const a = auth();
  if (!a) return;

  let dir = document.getElementById('uploadPath').value.trim();
  if (dir && !dir.endsWith('/')) dir += '/';
  const path = dir + _pendingFile.name;

  const form = new FormData();
  form.append('file', _pendingFile);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/upload/' + path);
  xhr.setRequestHeader('Authorization', a);
  xhr.upload.onprogress = e => {
    if (e.lengthComputable) progressBar.style.width = (e.loaded / e.total * 100) + '%';
  };
  xhr.onload = () => {
    if (xhr.status === 401) { _auth = null; alert('Auth failed'); }
    else location.reload();
  };
  xhr.onerror = () => alert('Upload failed');
  xhr.send(form);
});

// ── Drag & Drop ────────────────────────────────────
const dragOverlay = document.getElementById('dragOverlay');
let _dragCount = 0;

document.addEventListener('dragenter', e => {
  e.preventDefault();
  if (++_dragCount === 1) dragOverlay.classList.add('active');
});

document.addEventListener('dragleave', e => {
  e.preventDefault();
  if (--_dragCount === 0) dragOverlay.classList.remove('active');
});

document.addEventListener('dragover', e => e.preventDefault());

document.addEventListener('drop', e => {
  e.preventDefault();
  _dragCount = 0;
  dragOverlay.classList.remove('active');
  const file = e.dataTransfer.files[0];
  if (file) showPending(file);
});

// ── File actions (copy link / delete) ──────────────
document.addEventListener('click', e => {
  // Copy
  const cp = e.target.closest('.act-copy');
  if (cp) {
    const url = location.origin + cp.dataset.url;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => flash(cp));
    } else {
      // Fallback for non-HTTPS
      const ta = document.createElement('textarea');
      ta.value = url;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      flash(cp);
    }
    return;
  }

  // Delete
  const del = e.target.closest('.act-delete');
  if (del) {
    if (!confirm('Delete ' + del.dataset.path + '?')) return;
    const a = auth();
    if (!a) return;
    fetch('/delete/' + del.dataset.path, {
      method: 'DELETE',
      headers: { Authorization: a }
    }).then(r => {
      if (r.ok)            location.reload();
      else if (r.status === 401) { _auth = null; alert('Auth failed'); }
      else                 alert('Delete failed');
    });
  }
});

function flash(el) {
  el.style.color = 'var(--green)';
  setTimeout(() => el.style.color = '', 700);
}

// ── JSON click interception ────────────────────────
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-path]');
  if (a && a.dataset.path.endsWith('.json')) {
    e.preventDefault();
    openJSON(a.dataset.path);
  }
});

// ── JSON editor ────────────────────────────────────
let _jsonPath = null;

function openJSON(path) {
  _jsonPath = path;
  document.getElementById('jsonTitle').textContent = path;
  fetch('/files/' + path)
    .then(r => r.text())
    .then(t => {
      document.getElementById('jsonEditor').value = JSON.stringify(JSON.parse(t), null, 2);
      document.getElementById('jsonModal').classList.add('open');
    });
}

function closeJSON() {
  document.getElementById('jsonModal').classList.remove('open');
  const s = document.getElementById('jsonStatus');
  s.textContent = '';
  s.className = 'modal-status';
}

async function saveJSON() {
  const s = document.getElementById('jsonStatus');
  const a = auth();
  if (!a) return;

  try {
    const data = JSON.parse(document.getElementById('jsonEditor').value);
    const form = new FormData();
    form.append('file', new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));

    const r = await fetch('/upload/' + _jsonPath, {
      method: 'POST',
      headers: { Authorization: a },
      body: form
    });

    if (r.ok)                  { s.textContent = 'Saved';       s.className = 'modal-status ok'; }
    else if (r.status === 401) { _auth = null; s.textContent = 'Auth failed'; s.className = 'modal-status error'; }
    else                       { s.textContent = 'Failed';      s.className = 'modal-status error'; }
  } catch {
    s.textContent = 'Invalid JSON';
    s.className = 'modal-status error';
  }
}

// ── Keyboard ───────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && document.getElementById('jsonModal').classList.contains('open')) {
    closeJSON();
  }
});