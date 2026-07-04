/**
 * Py2APK – Build status page.
 * Connects via WebSocket to stream live logs.
 * Falls back to polling if WebSocket fails.
 */
(function () {
  const terminal      = document.getElementById('terminal');
  const placeholder   = document.getElementById('terminalPlaceholder');
  const progressSec   = document.getElementById('progressSection');
  const progressText  = document.getElementById('progressText');
  const buildStatus   = document.getElementById('buildStatus');
  const buildDuration = document.getElementById('buildDuration');
  const buildError    = document.getElementById('buildError');
  const autoScrollBtn = document.getElementById('autoScrollBtn');
  const clearLogsBtn  = document.getElementById('clearLogsBtn');
  const retryBtn      = document.getElementById('retryBtn');
  const cancelBtn     = document.getElementById('cancelBtn');

  let autoScroll = true;
  let ws = null;
  let pollTimer = null;
  let lastLogId = 0;

  const TERMINAL_STATUSES = ['queued', 'building'];
  const FINAL_STATUSES    = ['success', 'failed', 'cancelled'];

  // ── Log rendering ───────────────────────────────────────────────────────
  function appendLogLine(entry) {
    if (placeholder) placeholder.remove();
    const span = document.createElement('span');
    span.className = `log-line ${entry.level || 'INFO'}`;
    const ts = (entry.ts || '').slice(11, 19); // HH:MM:SS
    span.innerHTML = `<span class="log-ts">[${ts}]</span>${escapeHtml(entry.message)}`;
    terminal.appendChild(span);
    if (autoScroll) terminal.scrollTop = terminal.scrollHeight;
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Status update ───────────────────────────────────────────────────────
  function updateStatus(status, data) {
    // Badge
    if (buildStatus) {
      buildStatus.textContent = status;
      buildStatus.className = `badge badge--${status} badge--lg`;
    }
    // Progress bar
    if (progressSec) {
      if (TERMINAL_STATUSES.includes(status)) {
        progressSec.style.display = '';
        if (progressText) progressText.textContent = status === 'queued' ? 'Queued…' : 'Building…';
      } else {
        progressSec.style.display = 'none';
      }
    }
    // Duration
    if (buildDuration && data && data.duration_seconds) {
      buildDuration.textContent = data.duration_seconds + 's';
    }
    // Error
    if (buildError && data && data.error_message) {
      buildError.textContent = data.error_message;
    }

    // Action buttons
    if (FINAL_STATUSES.includes(status)) {
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (status === 'success' && !document.querySelector('.btn-success[href]')) {
        const hdr = document.querySelector('.header-actions');
        if (hdr) {
          const dl = document.createElement('a');
          dl.href      = `/download/${BUILD_ID}`;
          dl.className = 'btn btn-success';
          dl.textContent = '⬇ Download APK';
          hdr.prepend(dl);
        }
      }
      if ((status === 'failed' || status === 'cancelled') && !retryBtn) {
        // button already injected by template
      }
    }
  }

  // ── WebSocket connection ─────────────────────────────────────────────────
  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url   = `${proto}://${location.host}/ws/builds/${BUILD_ID}/logs`;

    ws = new WebSocket(url);

    ws.onopen = () => console.log('WS connected');

    ws.onmessage = e => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }

      if (msg.type === 'log') {
        appendLogLine(msg);
        lastLogId = Math.max(lastLogId, msg.id || 0);
      } else if (msg.type === 'status') {
        updateStatus(msg.status, null);
        if (FINAL_STATUSES.includes(msg.status)) {
          fetchFullStatus(); // get duration / error
        }
      }
    };

    ws.onclose = e => {
      console.log('WS closed', e.code);
      ws = null;
      // Fall back to polling if build not yet finished
      if (!FINAL_STATUSES.includes(INITIAL_STATUS)) {
        startPolling();
      }
    };

    ws.onerror = () => {
      ws && ws.close();
      startPolling();
    };
  }

  // ── Polling fallback ─────────────────────────────────────────────────────
  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(poll, 2000);
    poll(); // immediate first call
  }

  async function poll() {
    try {
      const r = await fetch(`/api/builds/${BUILD_ID}/logs/json?after=${lastLogId}`);
      if (!r.ok) return;
      const data = await r.json();

      // Render new log lines
      (data.logs || []).forEach(entry => {
        appendLogLine(entry);
        lastLogId = Math.max(lastLogId, entry.id || 0);
      });

      // Update status
      if (data.status) {
        updateStatus(data.status, null);
        if (FINAL_STATUSES.includes(data.status)) {
          clearInterval(pollTimer);
          pollTimer = null;
          fetchFullStatus(); // fetch duration / error_message
        }
      }
    } catch (err) {
      console.warn('Poll error:', err);
    }
  }

  async function fetchFullStatus() {
    try {
      const r = await fetch(`/api/builds/${BUILD_ID}/status`);
      if (r.ok) {
        const data = await r.json();
        updateStatus(data.status, data);
      }
    } catch {}
  }

  // ── Auto-scroll toggle ──────────────────────────────────────────────────
  if (autoScrollBtn) {
    autoScrollBtn.addEventListener('click', () => {
      autoScroll = !autoScroll;
      autoScrollBtn.textContent = autoScroll ? '⬇ Auto-scroll' : '↕ Manual';
      autoScrollBtn.classList.toggle('btn-primary', autoScroll);
    });
    terminal.addEventListener('scroll', () => {
      const atBottom = terminal.scrollHeight - terminal.clientHeight - terminal.scrollTop < 40;
      if (!atBottom && autoScroll) {
        autoScroll = false;
        autoScrollBtn.textContent = '↕ Manual';
        autoScrollBtn.classList.remove('btn-primary');
      }
    });
  }

  // ── Clear logs ──────────────────────────────────────────────────────────
  if (clearLogsBtn) {
    clearLogsBtn.addEventListener('click', () => {
      terminal.innerHTML = '';
    });
  }

  // ── Retry button ────────────────────────────────────────────────────────
  if (retryBtn) {
    retryBtn.addEventListener('click', async () => {
      retryBtn.disabled = true;
      retryBtn.textContent = '⟳ Retrying…';
      const r = await fetch(`/api/builds/${BUILD_ID}/retry`, { method: 'POST' });
      if (r.ok) {
        location.reload();
      } else {
        const e = await r.json();
        window.showFlash && window.showFlash(e.error || 'Retry failed', 'error');
        retryBtn.disabled = false;
        retryBtn.textContent = '⟳ Retry Build';
      }
    });
  }

  // ── Cancel button ────────────────────────────────────────────────────────
  if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
      if (!confirm('Cancel this build?')) return;
      const r = await fetch(`/api/builds/${BUILD_ID}/cancel`, { method: 'POST' });
      if (r.ok) location.reload();
    });
  }

  // ── Initialise ──────────────────────────────────────────────────────────
  if (FINAL_STATUSES.includes(INITIAL_STATUS)) {
    // Build already done – just show the terminal for historical log viewing
    if (progressSec) progressSec.style.display = 'none';
  } else {
    connectWS();
  }
})();
