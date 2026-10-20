// Sidebar navigation, lazy section loading, and the source-file viewer.
(() => {
  const positionParams = ['doc-x', 'doc-y', 'doc-nav'];
  const pageParams = new URLSearchParams(location.search);
  // Letter hotkeys must ignore the search box and every other typing surface.
  const typingTarget = [
    'input', 'textarea', 'select',
    '[role="textbox"]', '[role="searchbox"]', '[role="combobox"]',
    '[role="spinbutton"]', '[role="slider"]', '[role="listbox"]',
    '[role="menu"]', '[role="tree"]', '[role="grid"]',
  ].join(', ');

  function hasScrollPosition(key) {
    const value = Number(pageParams.get(key));
    return pageParams.has(key) && Number.isFinite(value) && value >= 0;
  }

  function reducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  // Source pages. Back returns to the docs with the theme and the exact scroll
  // position the reader left, including the navbar.
  const sourceBack = document.getElementById('source-back');
  if (sourceBack) {
    const back = new URL('../index.html', location.href);
    if (/^[A-Za-z0-9_-]+$/.test(pageParams.get('ref') || '')) back.hash = pageParams.get('ref');
    back.searchParams.set('theme', window.KAGTheme.get());
    for (const key of positionParams) {
      if (hasScrollPosition(key)) back.searchParams.set(key, pageParams.get(key));
    }
    sourceBack.href = back.href;

    function centerSourceLine() {
      if (!/^#L[1-9]\d*$/.test(location.hash)) return;
      const line = document.getElementById(location.hash.slice(1));
      if (!line) return;
      // Wait until the browser's own fragment scroll and the font layout settle.
      requestAnimationFrame(() => {
        const bounds = line.getBoundingClientRect();
        window.scrollTo({
          top: Math.max(0, window.scrollY + bounds.top + bounds.height / 2 - window.innerHeight / 2),
          behavior: 'instant',
        });
      });
    }

    window.addEventListener('load', () => (document.fonts?.ready || Promise.resolve()).then(centerSourceLine));
    window.addEventListener('hashchange', centerSourceLine);
  }

  function stampSourceLink(link) {
    const url = new URL(link.getAttribute('href'), location.href);
    url.searchParams.set('theme', window.KAGTheme.get());
    url.searchParams.set('doc-x', String(window.scrollX));
    url.searchParams.set('doc-y', String(window.scrollY));
    url.searchParams.set('doc-nav', String(document.getElementById('navigation')?.scrollTop || 0));
    link.href = url.href;
  }

  async function copySnippet(button) {
    if (!button) return;
    const text = document.getElementById(button.getAttribute('data-copy'))?.textContent;
    if (text == null) return;

    const label = button.querySelector('[data-copy-label]');
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch {
      // The Clipboard API is often disabled on offline file:// pages.
      copied = copyWithSelection(text);
    }

    label.textContent = copied ? 'Copied' : 'Copy failed';
    button.setAttribute('title', copied ? 'Copied' : 'Copy failed');
    if (!copied) return;

    button.getAnimations?.().forEach(animation => animation.cancel());
    const reduced = reducedMotion();
    button.animate?.([
      {transform: 'scale(1)'},
      {transform: reduced ? 'scale(1)' : 'scale(1.18)', color: 'var(--color-green)', offset: 0.35},
      {transform: 'scale(1)', color: 'var(--color-green)', offset: 0.8},
      {transform: 'scale(1)'},
    ], {duration: 600, easing: 'ease-out'});
  }

  function copyWithSelection(text) {
    const previousFocus = document.activeElement;
    const field = document.createElement('textarea');
    field.value = text;
    field.setAttribute('readonly', '');
    field.className = 'fixed left-0 top-0 opacity-0';
    document.body.append(field);
    field.select();
    let copied = false;
    try {
      copied = document.execCommand('copy');
    } catch {
      copied = false;
    } finally {
      field.remove();
      previousFocus?.focus({preventScroll: true});
    }
    return copied;
  }

  document.addEventListener('click', async event => {
    const source = event.target.closest('[data-source-link]');
    if (source) {
      stampSourceLink(source);
      return;
    }
    await copySnippet(event.target.closest('[data-copy]'));
  });

  const rail = document.querySelector('#navigation');
  const menu = document.querySelector('#menu');
  const themeToggle = document.querySelector('#theme-toggle');

  function syncSourceThemes() {
    document.getElementById('api-content')?.querySelectorAll('[data-source-link]').forEach(link => {
      const url = new URL(link.getAttribute('href'), location.href);
      url.searchParams.set('theme', window.KAGTheme.get());
      link.href = url.href;
    });
  }

  function updateThemeToggle() {
    syncSourceThemes();
    if (!themeToggle) return;
    const next = window.KAGTheme.next();
    const name = next[0].toUpperCase() + next.slice(1);
    themeToggle.setAttribute('aria-label', `Switch to Kanagawa ${name} theme`);
    themeToggle.setAttribute('title', `Switch to Kanagawa ${name}`);
  }

  themeToggle?.addEventListener('click', () => {
    window.KAGTheme.set(window.KAGTheme.next());
    updateThemeToggle();
  });
  updateThemeToggle();

  function closeMenu() {
    menu?.setAttribute('aria-expanded', 'false');
    rail?.classList.add('max-lg:hidden');
  }

  function expandGroup(header, expanded) {
    header.setAttribute('aria-expanded', String(expanded));
    document.getElementById(header.getAttribute('aria-controls')).hidden = !expanded;
    header.querySelector('.nav-caret').textContent = expanded ? '▾' : '▸';
  }

  menu?.addEventListener('click', () => {
    const open = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(open));
    rail.classList.toggle('max-lg:hidden', !open);
  });

  rail?.addEventListener('click', event => {
    // Modified clicks keep their normal "open in a new tab" behavior.
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button > 0) return;

    const header = event.target.closest('.nav-group-link');
    if (header) {
      event.preventDefault();
      const expanded = header.getAttribute('aria-expanded') !== 'true';
      expandGroup(header, expanded);
      // The same hash does not fire hashchange, so route the current page directly.
      if (location.hash === header.hash) route();
      else location.hash = header.hash;
    }

    const entry = event.target.closest('.nav-entry');
    if (entry) {
      event.preventDefault();
      window.KAGDocs.navigate(entry.hash.slice(1));
    }

    if (event.target.closest('a') && window.matchMedia('(width < 64rem)').matches) closeMenu();
  });

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || document.getElementById('quick-search')?.open) return;
    if (menu?.getAttribute('aria-expanded') !== 'true') return;
    closeMenu();
    menu.focus();
  });

  // Source pages stop here. Everything below is the API reference.
  const content = document.querySelector('#api-content');
  if (!content) return;

  const intro = document.getElementById('overview');
  const links = new Map([...rail.querySelectorAll('a[data-section]')].map(link => [link.hash.slice(1), link]));
  // Each overload signature is an alias of the one navbar entry for that family.
  for (const link of [...links.values()]) {
    for (const alias of (link.dataset.aliases || '').split(/\s+/).filter(Boolean)) links.set(alias, link);
  }
  const headers = new Map([...rail.querySelectorAll('.nav-group-link')].map(link => [link.dataset.section, link]));

  document.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
    if (!/^[a-z]$/i.test(event.key)) return;
    if (document.getElementById('quick-search')?.open || event.target?.isContentEditable) return;
    if (event.target?.closest?.(typingTarget)) return;

    const railBounds = rail.getBoundingClientRect();
    if (!railBounds.height) return;

    const letter = event.key.toUpperCase();
    let nearest;
    let distance = Infinity;
    for (const header of headers.values()) {
      if (header.querySelector('.nav-letter')?.textContent !== letter) continue;
      if (!header.closest('details')?.open) continue;
      const offset = Math.abs(header.getBoundingClientRect().top - railBounds.top);
      if (offset < distance) {
        nearest = header;
        distance = offset;
      }
    }
    if (!nearest) return;

    event.preventDefault();
    const reduced = reducedMotion();
    expandGroup(nearest, true);
    window.KAGDocs.navigate(nearest.hash.slice(1));
    // A quarter of the way down, so the sticky category header does not cover the badge.
    rail.scrollTo({
      top: Math.max(0, rail.scrollTop + nearest.getBoundingClientRect().top - railBounds.top - railBounds.height * 0.25),
      behavior: reduced ? 'instant' : 'smooth',
    });
    nearest.focus({preventScroll: true});

    const badge = nearest.querySelector('.nav-letter');
    badge.getAnimations?.().forEach(animation => animation.cancel());
    if (reduced) return;
    badge.animate?.([
      {transform: 'scale(1)', backgroundColor: 'var(--color-panel)', borderColor: 'var(--color-border)'},
      {transform: 'scale(1.22)', backgroundColor: 'var(--color-selection)', borderColor: 'var(--color-aqua)', color: 'var(--color-paper)', offset: 0.35},
      {transform: 'scale(1)', backgroundColor: 'var(--color-panel)', borderColor: 'var(--color-border)'},
    ], {duration: 480, easing: 'cubic-bezier(.2,.7,.2,1)'});
  });

  const cache = new Map();
  let activeSection;
  let mountedSection;
  let pendingScript;
  let current;
  let currentHeader;
  let observer;
  let viewed;
  // Ignore a partial or negative return position rather than jumping to a guess.
  let restorePosition = pageParams.has('doc-y') && positionParams.every(hasScrollPosition);

  function activate(id) {
    current?.removeAttribute('aria-current');
    current = links.get(id);
    current?.setAttribute('aria-current', 'location');
  }

  function markViewed(id) {
    viewed?.removeAttribute('data-viewed');
    viewed = links.get(id);
    viewed?.setAttribute('data-viewed', 'true');
  }

  function targetId() {
    try {
      return decodeURIComponent(location.hash.slice(1));
    } catch {
      return 'overview';
    }
  }

  function scrollToTarget() {
    const id = targetId();
    requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView();
      if (!restorePosition) return;
      window.scrollTo({
        left: Number(pageParams.get('doc-x')),
        top: Number(pageParams.get('doc-y')),
        behavior: 'instant',
      });
      rail.scrollTop = Number(pageParams.get('doc-nav'));
      restorePosition = false;
      const clean = new URL(location.href);
      for (const key of positionParams) clean.searchParams.delete(key);
      window.history.replaceState(window.history.state, '', clean.href);
    });
  }

  function mount(section, html) {
    if (section !== activeSection) return;
    observer?.disconnect();
    content.innerHTML = html;
    syncSourceThemes();
    content.removeAttribute('aria-busy');
    mountedSection = section;
    intro.hidden = true;
    markViewed();

    // Callbacks report changes, not the full set of visible headings, so the
    // set is kept here. The eye follows whichever entry sits in the top band.
    const inView = new Set();
    const watching = new IntersectionObserver(entries => {
      if (observer !== watching) return;
      for (const entry of entries) {
        if (entry.isIntersecting) inView.add(entry.target);
        else inView.delete(entry.target);
      }
      const visible = [...inView].sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
      markViewed(visible[0]?.id);
    }, {rootMargin: '-5% 0px -70% 0px'});
    observer = watching;
    content.querySelectorAll('.api-entry, header.api-section').forEach(block => observer.observe(block));
    scrollToTarget();
  }

  function showOverview(id) {
    observer?.disconnect();
    observer = undefined;
    markViewed();
    content.replaceChildren();
    content.removeAttribute('aria-busy');
    intro.hidden = false;
    mountedSection = undefined;
    activate('overview');
    if (id === 'overview') intro.scrollIntoView();
  }

  function loadSection(section) {
    observer?.disconnect();
    observer = undefined;
    markViewed();
    content.replaceChildren();
    mountedSection = undefined;
    intro.hidden = true;

    if (cache.has(section)) {
      mount(section, cache.get(section));
      return;
    }

    content.setAttribute('aria-busy', 'true');
    const script = document.createElement('script');
    script.src = `sections/${section}.js`;
    script.onload = () => script.remove();
    script.onerror = () => {
      script.remove();
      if (activeSection !== section) return;
      content.removeAttribute('aria-busy');
      content.textContent = 'Unable to load this section. Rebuild the docs with make build and reload.';
    };
    pendingScript = script;
    document.head.append(script);
  }

  function route() {
    const id = targetId();
    activate(id);
    const section = links.get(id)?.dataset.section;
    activeSection = section;
    currentHeader?.removeAttribute('data-active');
    currentHeader = headers.get(section);
    currentHeader?.setAttribute('data-active', 'true');
    const category = currentHeader?.closest('details');
    if (category) category.open = true;

    pendingScript?.remove();
    pendingScript = null;
    if (!section) {
      showOverview(id);
      return;
    }
    if (section === mountedSection) {
      scrollToTarget();
      return;
    }
    loadSection(section);
  }

  window.KAGDocs = {
    // Assigning the current hash does not fire hashchange.
    navigate(id) {
      if (targetId() === id) route();
      else location.hash = '#' + id;
    },
    sectionLoaded(section, html) {
      cache.delete(section);
      cache.set(section, html);
      // A short cache is enough for Back. Reinserting moves a section to the front.
      while (cache.size > 4) cache.delete(cache.keys().next().value);
      mount(section, html);
    },
  };

  window.addEventListener('hashchange', route);
  route();
})();
