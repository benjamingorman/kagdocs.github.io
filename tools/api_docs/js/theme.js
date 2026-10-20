// Apply the saved theme before the stylesheet loads, so the page does not flash Wave.
(() => {
  const storageKey = 'kag-docs-theme';
  const themes = ['wave', 'lotus', 'dragon'];
  let current = 'wave';

  function set(theme, persist = true) {
    current = themes.includes(theme) ? theme : 'wave';
    document.documentElement.dataset.theme = current;
    if (!persist) return;

    try {
      localStorage.setItem(storageKey, current);
    } catch {
      // file:// pages may block storage.
    }

    // Source links carry ?theme= because file:// storage is isolated per page.
    // Keep that parameter in step when the reader toggles the theme.
    const url = new URL(location.href);
    if (!url.searchParams.has('theme')) return;
    url.searchParams.set('theme', current);
    try {
      window.history.replaceState(window.history.state, '', url.href);
    } catch {
      // Some file origins reject history edits.
    }
  }

  try {
    current = localStorage.getItem(storageKey) || current;
  } catch {
    // Keep Wave when storage cannot be read.
  }

  const navigationTheme = new URLSearchParams(location.search).get('theme');
  if (themes.includes(navigationTheme)) current = navigationTheme;
  set(current, false);

  window.KAGTheme = {
    get: () => current,
    set,
    next: () => themes[(themes.indexOf(current) + 1) % themes.length],
  };
})();
