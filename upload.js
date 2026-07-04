/**
 * Py2APK – Upload page: drag-and-drop, file validation, XHR upload with progress.
 */
(function () {
  const dropZone        = document.getElementById('dropZone');
  const fileInput       = document.getElementById('fileInput');
  const dropContent     = document.getElementById('dropZoneContent');
  const fileSelectedEl  = document.getElementById('fileSelected');
  const fileNameEl      = document.getElementById('fileName');
  const fileSizeEl      = document.getElementById('fileSize');
  const fileIconEl      = document.getElementById('fileIcon');
  const removeFileBtn   = document.getElementById('removeFile');
  const submitBtn       = document.getElementById('submitBtn');
  const iconInput       = document.getElementById('iconInput');
  const iconPreview     = document.getElementById('iconPreview');
  const iconPlaceholder = document.querySelector('.icon-preview-placeholder');
  const uploadProgress  = document.getElementById('uploadProgress');
  const uploadBar       = document.getElementById('uploadBar');
  const uploadPct       = document.getElementById('uploadPct');
  const uploadError     = document.getElementById('uploadError');
  const uploadForm      = document.getElementById('uploadForm');

  const MAX_SIZE = 100 * 1024 * 1024; // 100 MB
  const ALLOWED  = ['.py', '.zip'];

  let selectedFile = null;

  // ── Helpers ─────────────────────────────────────────────────────────────
  function formatBytes(b) {
    if (b < 1024)       return b + ' B';
    if (b < 1048576)    return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
  }

  function showError(msg) {
    uploadError.textContent = msg;
    uploadError.classList.remove('hidden');
  }
  function clearError() { uploadError.classList.add('hidden'); }

  function getExt(name) {
    const i = name.lastIndexOf('.');
    return i >= 0 ? name.slice(i).toLowerCase() : '';
  }

  // ── File selection ───────────────────────────────────────────────────────
  function selectFile(file) {
    clearError();
    const ext = getExt(file.name);
    if (!ALLOWED.includes(ext)) {
      showError(`Unsupported file type "${ext}". Only .py and .zip files are accepted.`);
      resetFile();
      return;
    }
    if (file.size > MAX_SIZE) {
      showError(`File is too large (${formatBytes(file.size)}). Maximum size is 100 MB.`);
      resetFile();
      return;
    }
    selectedFile = file;
    fileNameEl.textContent  = file.name;
    fileSizeEl.textContent  = formatBytes(file.size);
    fileIconEl.textContent  = ext === '.zip' ? '📦' : '🐍';
    dropContent.classList.add('hidden');
    fileSelectedEl.classList.remove('hidden');
    submitBtn.disabled = false;
  }

  function resetFile() {
    selectedFile = null;
    fileInput.value = '';
    dropContent.classList.remove('hidden');
    fileSelectedEl.classList.add('hidden');
    submitBtn.disabled = true;
  }

  // ── Click to browse ──────────────────────────────────────────────────────
  dropZone.addEventListener('click', e => {
    if (e.target.closest('#removeFile')) return;
    fileInput.click();
  });
  dropZone.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  removeFileBtn.addEventListener('click', e => { e.stopPropagation(); resetFile(); });
  fileInput.addEventListener('change', () => {
    if (fileInput.files[0]) selectFile(fileInput.files[0]);
  });

  // ── Drag & Drop ──────────────────────────────────────────────────────────
  ['dragenter','dragover'].forEach(evt =>
    dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.add('dragover'); })
  );
  ['dragleave','dragend'].forEach(evt =>
    dropZone.addEventListener(evt, () => dropZone.classList.remove('dragover'))
  );
  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files[0]) selectFile(e.dataTransfer.files[0]);
  });

  // ── Icon preview ─────────────────────────────────────────────────────────
  iconInput.addEventListener('change', () => {
    const file = iconInput.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
      iconPreview.src = e.target.result;
      iconPreview.classList.remove('hidden');
      iconPlaceholder.classList.add('hidden');
    };
    reader.readAsDataURL(file);
  });

  // ── Splash screen preview ─────────────────────────────────────────────────
  const splashInput   = document.getElementById('splashInput');
  const splashPreview = document.getElementById('splashPreview');
  const splashPlaceholder = document.getElementById('splashPlaceholder');
  if (splashInput) {
    splashInput.addEventListener('change', () => {
      const file = splashInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = e => {
        splashPreview.src = e.target.result;
        splashPreview.classList.remove('hidden');
        splashPlaceholder && splashPlaceholder.classList.add('hidden');
      };
      reader.readAsDataURL(file);
    });
  }

  // ── Form submit ──────────────────────────────────────────────────────────
  uploadForm.addEventListener('submit', async e => {
    e.preventDefault();
    clearError();

    if (!selectedFile) { showError('Please select a file.'); return; }

    const formData = new FormData(uploadForm);
    // Ensure the file is included (FormData from the form already has it via input[name=file])
    // but we overwrite with the selectedFile in case of D&D without using the input element
    formData.set('file', selectedFile, selectedFile.name);

    submitBtn.disabled = true;
    submitBtn.querySelector('.btn-text').classList.add('hidden');
    submitBtn.querySelector('.btn-spinner').classList.remove('hidden');
    submitBtn.querySelector('.btn-spinner').classList.add('spinning');
    uploadProgress.classList.remove('hidden');

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');

    xhr.upload.addEventListener('progress', e => {
      if (e.lengthComputable) {
        const pct = Math.round((e.loaded / e.total) * 100);
        uploadBar.style.width = pct + '%';
        uploadPct.textContent = pct + '%';
      }
    });

    xhr.addEventListener('load', async () => {
      uploadProgress.classList.add('hidden');
      let data;
      try { data = JSON.parse(xhr.responseText); } catch { data = {}; }

      if (xhr.status === 201 && data.build_id) {
        // Auto-start the build
        try {
          await fetch(`/api/builds/${data.build_id}/start`, { method: 'POST' });
        } catch (err) {
          console.warn('Auto-start failed:', err);
        }
        window.location.href = `/builds/${data.build_id}`;
      } else {
        showError(data.error || `Upload failed (HTTP ${xhr.status})`);
        submitBtn.disabled = false;
        submitBtn.querySelector('.btn-text').classList.remove('hidden');
        submitBtn.querySelector('.btn-spinner').classList.add('hidden');
      }
    });

    xhr.addEventListener('error', () => {
      uploadProgress.classList.add('hidden');
      showError('Network error. Please check your connection and try again.');
      submitBtn.disabled = false;
      submitBtn.querySelector('.btn-text').classList.remove('hidden');
      submitBtn.querySelector('.btn-spinner').classList.add('hidden');
    });

    xhr.send(formData);
  });
})();
