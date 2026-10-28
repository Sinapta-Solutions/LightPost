// Run before styles load so the saved theme is applied before the first paint.
(() => {
  const key = 'lightpost-theme';
  const system = window.matchMedia?.('(prefers-color-scheme: dark)');
  const valid = (value) => value === 'light' || value === 'dark';
  let preference = null;
  try {
    const saved = window.localStorage.getItem(key);
    if (valid(saved)) preference = saved;
  } catch {
    // The toggle still works when browser storage is unavailable.
  }
  function apply() {
    const theme = preference || (system?.matches ? 'dark' : 'light');
    document.documentElement.dataset.theme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'dark' ? '#101722' : '#fafaf8');
    document.querySelectorAll('[data-action="toggle-theme"]').forEach((button) => {
      button.setAttribute('aria-checked', String(theme === 'dark'));
      button.title = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
    });
  }
  window.lightpostTheme = {
    current: () => document.documentElement.dataset.theme,
    toggle() {
      preference = this.current() === 'dark' ? 'light' : 'dark';
      try {
        window.localStorage.setItem(key, preference);
      } catch {
        // Keep the choice for this page even if it cannot be saved.
      }
      apply();
    },
  };
  system?.addEventListener?.('change', () => {
    if (!preference) apply();
  });
  window.addEventListener('storage', (event) => {
    if (event.key !== key && event.key !== null) return;
    preference = valid(event.newValue) ? event.newValue : null;
    apply();
  });
  apply();
})();
