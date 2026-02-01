let currentJSONPath = null;

// ─── folder toggle ────────────────────────────────────

document.querySelectorAll(".dir").forEach(dir => {
  dir.onclick = () => {
    const next = dir.nextElementSibling;
    const open = next.style.display === "block";
    next.style.display = open ? "none" : "block";
    dir.classList.toggle("open", !open);
  };
});

// ─── JSON click interception ──────────────────────────

document.addEventListener("click", e => {
  const a = e.target.closest("a[data-path]");
  if (!a) return;
  const path = a.dataset.path;
  if (path.endsWith(".json")) {
    e.preventDefault();
    openJSON(path);
  }
});

// ─── upload ───────────────────────────────────────────

function upload() {
  const file = fileInput.files[0];
  let path = uploadPath.value.trim();
  if (!file) return alert("Select a file");
  if (!path) path = file.name;

  const form = new FormData();
  form.append("file", file);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload/" + path);
  xhr.upload.onprogress = e => {
    if (e.lengthComputable)
      progressBar.style.width = (e.loaded / e.total * 100) + "%";
  };
  xhr.onload = () => location.reload();
  xhr.send(form);
}

// ─── JSON editor ──────────────────────────────────────

function openJSON(path) {
  currentJSONPath = path;
  jsonTitle.textContent = path;
  fetch("/files/" + path)
    .then(r => r.text())
    .then(t => {
      jsonEditor.value = JSON.stringify(JSON.parse(t), null, 2);
      jsonModal.style.display = "flex";
    });
}

function closeJSON() {
  jsonModal.style.display = "none";
}

async function saveJSON() {
  try {
    const data = JSON.parse(jsonEditor.value);
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const form = new FormData();
    form.append("file", blob);
    const res = await fetch("/upload/" + currentJSONPath, {
      method: "POST",
      body: form
    });
    jsonStatus.textContent = res.ok ? "Saved" : "Save failed";
  } catch {
    jsonStatus.textContent = "Invalid JSON";
  }
}