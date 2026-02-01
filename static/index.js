// ─── Folder Toggle (animated via CSS max-height) ─────
document.querySelectorAll(".dir").forEach(dir => {
  dir.onclick = () => {
    const children = dir.nextElementSibling;
    dir.classList.toggle("open");
    children.classList.toggle("open");
  };
});

// ─── File Count Badge ─────────────────────────────────
(function () {
  const count = document.querySelectorAll(".file").length;
  const el = document.getElementById("fileCount");
  if (el) el.textContent = count + " file" + (count !== 1 ? "s" : "");
})();

// ─── Drag & Drop ──────────────────────────────────────
const dropZone = document.getElementById("dropZone");

dropZone.addEventListener("click", e => {
  if (e.target.closest("button") || e.target.closest("input")) return;
  document.getElementById("fileInput").click();
});

dropZone.addEventListener("dragover", e => {
  e.preventDefault();
  dropZone.classList.add("dragover");
});

dropZone.addEventListener("dragleave", e => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
});

dropZone.addEventListener("drop", e => {
  e.preventDefault();
  dropZone.classList.remove("dragover");
  const file = e.dataTransfer.files[0];
  if (!file) return;
  document.getElementById("fileInput").files = e.dataTransfer.files;
  upload();
});

// ─── JSON Link Interception ───────────────────────────
document.addEventListener("click", e => {
  const a = e.target.closest("a[data-path]");
  if (!a) return;
  if (a.dataset.path.endsWith(".json")) {
    e.preventDefault();
    openJSON(a.dataset.path);
  }
});

// ─── Upload ───────────────────────────────────────────
function upload() {
  const file = document.getElementById("fileInput").files[0];
  let path = document.getElementById("uploadPath").value.trim();
  if (!file) return alert("Select a file");
  if (!path) path = file.name;

  const form = new FormData();
  form.append("file", file);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/upload/" + path);
  xhr.upload.onprogress = e => {
    if (e.lengthComputable)
      document.getElementById("progressBar").style.width =
        (e.loaded / e.total * 100) + "%";
  };
  xhr.onload = () => location.reload();
  xhr.send(form);
}

// ─── JSON Editor ──────────────────────────────────────
let currentJSONPath = null;

function openJSON(path) {
  currentJSONPath = path;
  document.getElementById("jsonTitle").textContent = path;
  fetch("/files/" + path)
    .then(r => r.text())
    .then(t => {
      document.getElementById("jsonEditor").value =
        JSON.stringify(JSON.parse(t), null, 2);
      document.getElementById("jsonModal").classList.add("open");
    });
}

function closeJSON() {
  document.getElementById("jsonModal").classList.remove("open");
  const s = document.getElementById("jsonStatus");
  s.textContent = "";
  s.className = "modal-status";
}

async function saveJSON() {
  const statusEl = document.getElementById("jsonStatus");
  try {
    const data = JSON.parse(document.getElementById("jsonEditor").value);
    const blob = new Blob(
      [JSON.stringify(data, null, 2)],
      { type: "application/json" }
    );
    const form = new FormData();
    form.append("file", blob);

    const res = await fetch("/upload/" + currentJSONPath, {
      method: "POST",
      body: form
    });

    statusEl.textContent = res.ok ? "Saved ✓" : "Save failed";
    statusEl.className = "modal-status" + (res.ok ? "" : " error");
  } catch {
    statusEl.textContent = "Invalid JSON";
    statusEl.className = "modal-status error";
  }
}