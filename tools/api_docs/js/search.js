// Offline command palette. The sidebar is the whole index, including symbols
// inside collapsed groups and sections that have not been loaded yet.
((root, factory) => {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else {
    root.KAGSearch = api;
    api.init(root.document, root);
  }
})(typeof window !== 'undefined' ? window : globalThis, () => {
  function normalize(text) {
    return text.toLowerCase().replace(/[^\p{L}\p{N}_]+/gu, ' ').trim();
  }

  function prepare(items) {
    return items.map((item, order) => ({
      ...item,
      order,
      nameKey: normalize(item.name),
      labelKey: normalize(item.label),
      textKey: normalize(`${item.label} ${item.declaration || ''} ${item.kind}`),
    }));
  }

  // How many characters were skipped between the letters of a fuzzy abbreviation.
  function subsequence(needle, haystack) {
    let position = 0;
    let gaps = 0;
    for (const letter of needle) {
      const next = haystack.indexOf(letter, position);
      if (next < 0) return Infinity;
      gaps += next - position;
      position = next + 1;
    }
    return gaps;
  }

  // Lower scores win: exact name, exact label, prefixes, then terms found
  // anywhere in the signature, then a fuzzy abbreviation of the bare name.
  function scoreItem(item, key, terms) {
    if (item.nameKey === key) return 0;
    if (item.labelKey === key) return 1;
    if (item.nameKey.startsWith(key)) return 10;
    if (item.labelKey.startsWith(key)) return 20;
    if (terms.every(term => item.textKey.includes(term))) return 40 + item.labelKey.length / 100;
    if (terms.length === 1 && key.length >= 2) return 100 + subsequence(key, item.nameKey);
    return Infinity;
  }

  function search(items, query, limit = 40) {
    const key = normalize(query).slice(0, 160);
    // An empty query offers sections, not every symbol in the index.
    if (!key) return items.filter(item => item.kind === 'section').slice(0, limit);

    const terms = key.split(/\s+/);
    const matches = [];
    for (const item of items) {
      const score = scoreItem(item, key, terms);
      if (Number.isFinite(score)) matches.push({item, score});
    }
    matches.sort((a, b) => a.score - b.score
      || a.item.labelKey.localeCompare(b.item.labelKey)
      || a.item.order - b.item.order);
    return matches.slice(0, limit).map(match => match.item);
  }

  function init(document, window) {
    const dialog = document.getElementById('quick-search');
    if (!dialog) return;

    const opener = document.getElementById('search-open');
    const input = document.getElementById('search-input');
    const results = document.getElementById('search-results');
    const status = document.getElementById('search-status');
    const closeButton = document.getElementById('search-close');
    const nodes = [...document.querySelectorAll('#navigation a[data-section]')];
    const headers = new Map(nodes
      .filter(link => link.classList.contains('nav-group-link'))
      .map(link => [link.dataset.section, link]));
    const items = prepare(nodes.map(link => ({
      id: link.hash.slice(1),
      section: link.dataset.section,
      name: link.dataset.searchName,
      label: link.dataset.searchLabel,
      kind: link.dataset.searchKind,
      declaration: link.getAttribute('title') || link.dataset.searchLabel,
    })));
    const shortcut = document.getElementById('search-shortcut');
    shortcut.textContent = /Mac|iPhone|iPad/.test(window.navigator?.platform || '') ? '⌘ K' : 'Ctrl K';

    let hits = [];
    let selected = 0;
    let returnFocus;
    let oldOverflow;

    function select(index) {
      if (!hits.length) {
        input.removeAttribute('aria-activedescendant');
        return;
      }
      selected = (index + hits.length) % hits.length;
      [...results.children].forEach((row, i) => row.setAttribute('aria-selected', String(i === selected)));
      const row = results.children[selected];
      input.setAttribute('aria-activedescendant', row.id);
      row.scrollIntoView({block: 'nearest'});
    }

    function resultRow(item, index) {
      const row = document.createElement('div');
      row.id = `search-result-${index}`;
      row.className = 'search-result';
      row.dataset.resultIndex = String(index);
      row.setAttribute('role', 'option');

      const heading = document.createElement('div');
      heading.className = 'flex items-center justify-between gap-3';
      const label = document.createElement('span');
      label.className = 'truncate font-mono text-sm text-paper';
      label.textContent = item.label;
      const kind = document.createElement('span');
      kind.className = 'shrink-0 text-[10px] text-aqua';
      kind.textContent = item.kind;
      heading.append(label, kind);

      const signature = document.createElement('p');
      signature.className = 'mt-1 truncate font-mono text-[11px] text-muted';
      signature.textContent = item.declaration;
      row.append(heading, signature);
      return row;
    }

    function render() {
      hits = search(items, input.value);
      results.replaceChildren();
      hits.forEach((item, index) => results.append(resultRow(item, index)));
      if (!hits.length) status.textContent = 'No matching API names';
      else if (!input.value.trim()) status.textContent = 'Browse sections or type any API name';
      else status.textContent = `${hits.length === 40 ? 'Top ' : ''}${hits.length} results`;
      select(0);
    }

    function open() {
      if (!dialog.open) {
        returnFocus = document.activeElement;
        oldOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        dialog.showModal();
        input.value = '';
        input.setAttribute('aria-expanded', 'true');
        render();
      }
      input.focus();
      input.select();
    }

    // Highlight the chosen entry and park it a quarter of the way down the
    // rail, clear of the sticky category header.
    function reveal(id) {
      const link = nodes.find(node => node.hash.slice(1) === id);
      const rail = document.getElementById('navigation');
      if (!link || !rail) return;

      for (const node of nodes) node.removeAttribute('aria-current');
      link.setAttribute('aria-current', 'location');

      const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
      const railBounds = rail.getBoundingClientRect();
      const linkBounds = link.getBoundingClientRect();
      rail.scrollTo({
        top: Math.max(0, rail.scrollTop + linkBounds.top - railBounds.top - railBounds.height * 0.25),
        behavior: reduced ? 'instant' : 'smooth',
      });
    }

    function choose(index = selected) {
      const item = hits[index];
      if (!item) return;

      const header = headers.get(item.section);
      if (header) {
        const category = header.closest('details');
        if (category) category.open = true;
        header.setAttribute('aria-expanded', 'true');
        document.getElementById(header.getAttribute('aria-controls')).hidden = false;
        header.querySelector('.nav-caret').textContent = '▾';
      }

      dialog.close();
      window.KAGDocs.navigate(item.id);
      reveal(item.id);
    }

    opener.addEventListener('click', open);
    closeButton.addEventListener('click', () => dialog.close());

    dialog.addEventListener('close', () => {
      document.body.style.overflow = oldOverflow;
      input.setAttribute('aria-expanded', 'false');
      input.removeAttribute('aria-activedescendant');
      // preventScroll keeps the navbar where reveal() just placed it.
      if (returnFocus?.isConnected !== false) returnFocus?.focus({preventScroll: true});
    });

    // A click on the backdrop hits the dialog element, not the panel inside it.
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      const outside = event.clientX < box.left || event.clientX > box.right
        || event.clientY < box.top || event.clientY > box.bottom;
      if (outside) dialog.close();
    });

    input.addEventListener('input', render);
    input.addEventListener('keydown', event => {
      if (event.isComposing) return;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        select(selected + (event.key === 'ArrowDown' ? 1 : -1));
      } else if (event.key === 'Enter') {
        event.preventDefault();
        choose();
      }
    });

    results.addEventListener('click', event => {
      const row = event.target.closest('[data-result-index]');
      if (row) choose(Number(row.dataset.resultIndex));
    });
    results.addEventListener('mousemove', event => {
      const row = event.target.closest('[data-result-index]');
      if (row && selected !== Number(row.dataset.resultIndex)) select(Number(row.dataset.resultIndex));
    });

    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && dialog.open) {
        event.preventDefault();
        dialog.close();
      } else if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        open();
      }
    });
  }

  return {normalize, prepare, search, init};
});
