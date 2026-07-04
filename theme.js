/**
 * Theme (dark / light) management.
 * Reads preference from localStorage and syncs all toggle buttons.
 */
(function () {
  const STORAGE_KEY = 'py2apk-theme';

  function getPreferred() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) return saved;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    // Update all theme icon buttons
    document.querySelectorAll('.theme-icon').forEach(el => {
      el.textContent = theme === 'dark' ? '☀' : '🌙';
    });
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    applyTheme(current === 'dark' ? 'light' : 'dark');
  }

  // Apply on load (before paint)
  applyTheme(getPreferred());

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.theme-toggle').forEach(btn => {
      btn.addEventListener('click', toggleTheme);
    });
    // Re-sync icons after DOM is ready
    applyTheme(getPreferred());
  });
})();
