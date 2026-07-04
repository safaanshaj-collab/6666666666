/**
 * Py2APK – Global JS (sidebar toggle, flash messages)
 */
document.addEventListener('DOMContentLoaded', function () {
  // ── Sidebar mobile toggle ───────────────────────────────────────────
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('overlay');
  const menuBtn  = document.getElementById('menuToggle');
  const closeBtn = document.getElementById('sidebarClose');

  function openSidebar()  { sidebar.classList.add('open');  overlay.classList.add('show'); }
  function closeSidebar() { sidebar.classList.remove('open'); overlay.classList.remove('show'); }

  if (menuBtn)  menuBtn.addEventListener('click',  openSidebar);
  if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
  if (overlay)  overlay.addEventListener('click',  closeSidebar);

  // Close sidebar on navigation (mobile)
  sidebar && sidebar.querySelectorAll('.nav-link').forEach(a =>
    a.addEventListener('click', closeSidebar)
  );

  // ── Flash message helper (used by other scripts) ────────────────────
  window.showFlash = function (message, type = 'info') {
    const container = document.getElementById('flash-container');
    if (!container) return;
    const el = document.createElement('div');
    el.className = `alert alert--${type}`;
    el.style.cssText = 'margin-bottom:.75rem;animation:fadeIn .2s ease';
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  };

  // ── Keyboard: close sidebar on Escape ──────────────────────────────
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeSidebar();
  });
});
