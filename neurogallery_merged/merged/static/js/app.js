/* NeuroGallery – app.js */
'use strict';

// ── Dark mode toggle ─────────────────────────────────────────────────────────
const darkBtn = document.getElementById('darkToggle');
if (darkBtn) {
  darkBtn.addEventListener('click', () => {
    fetch('/profile/dark-mode/', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCookie('csrftoken') },
    })
      .then(r => r.json())
      .then(data => {
        document.getElementById('html-root').dataset.theme =
          data.dark_mode ? 'dark' : '';
      });
  });
}

// ── Sidebar mobile toggle ────────────────────────────────────────────────────
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar       = document.getElementById('sidebar');
if (sidebarToggle && sidebar) {
  sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('open'));
  document.addEventListener('click', e => {
    if (!sidebar.contains(e.target) && !sidebarToggle.contains(e.target)) {
      sidebar.classList.remove('open');
    }
  });
}

// ── Auto-dismiss alerts ──────────────────────────────────────────────────────
document.querySelectorAll('.alert').forEach(el => {
  setTimeout(() => el.style.opacity = '0', 4500);
  setTimeout(() => el.remove(), 5000);
});

// ── CSRF helper ──────────────────────────────────────────────────────────────
function getCookie(name) {
  const v = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return v ? v.pop() : '';
}
