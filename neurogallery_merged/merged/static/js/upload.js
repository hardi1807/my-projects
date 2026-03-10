/* NeuroGallery – upload.js
   Handles drag-and-drop, file preview, and form submission for the upload page.
*/
'use strict';

const dropZone     = document.getElementById('drop-zone');
const previewGrid  = document.getElementById('preview-grid');
const fileCount    = document.getElementById('file-count');
const uploadBtn    = document.getElementById('upload-btn');
const form         = document.getElementById('upload-form');
const browseInput  = document.getElementById('photo-input');

let selectedFiles = [];

// ── Helpers ──────────────────────────────────────────────────────────────────
function updateCount() {
  fileCount.textContent = `${selectedFiles.length} file${selectedFiles.length !== 1 ? 's' : ''} selected`;
  uploadBtn.disabled = selectedFiles.length === 0;
}

function addFiles(files) {
  Array.from(files).forEach(file => {
    if (!file.type.startsWith('image/')) return;
    if (selectedFiles.some(f => f.name === file.name && f.size === file.size)) return;
    selectedFiles.push(file);

    const item = document.createElement('div');
    item.className = 'preview-item';

    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    img.onload = () => URL.revokeObjectURL(img.src);

    const btn = document.createElement('button');
    btn.className = 'remove-btn';
    btn.innerHTML = '×';
    btn.title = 'Remove';
    btn.addEventListener('click', () => {
      selectedFiles = selectedFiles.filter(f => f !== file);
      item.remove();
      updateCount();
    });

    item.appendChild(img);
    item.appendChild(btn);
    previewGrid.appendChild(item);
  });
  updateCount();
}

// ── Browse button ────────────────────────────────────────────────────────────
browseInput.addEventListener('change', e => addFiles(e.target.files));

// ── Drag & drop ──────────────────────────────────────────────────────────────
['dragenter', 'dragover'].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.add('dragover'); })
);
['dragleave', 'drop'].forEach(ev =>
  dropZone.addEventListener(ev, e => { e.preventDefault(); dropZone.classList.remove('dragover'); })
);
dropZone.addEventListener('drop', e => addFiles(e.dataTransfer.files));
dropZone.addEventListener('click', () => browseInput.click());

// ── Form submit: inject files into FormData ──────────────────────────────────
form.addEventListener('submit', e => {
  if (selectedFiles.length === 0) { e.preventDefault(); return; }

  e.preventDefault();
  const fd = new FormData(form);
  // Remove any existing 'images' entries and re-add from our array
  fd.delete('images');
  selectedFiles.forEach(f => fd.append('images', f));

  uploadBtn.disabled = true;
  uploadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Uploading…';

  fetch(form.action || window.location.href, {
    method: 'POST',
    body: fd,
    headers: { 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value },
  })
    .then(resp => {
      // Django returns a redirect – follow it
      if (resp.redirected) { window.location.href = resp.url; }
      else { window.location.reload(); }
    })
    .catch(() => {
      uploadBtn.disabled = false;
      uploadBtn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up"></i> Upload Photos';
      alert('Upload failed. Please try again.');
    });
});
