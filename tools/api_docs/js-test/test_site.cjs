// Exercise routing and interaction without a browser or external DOM packages.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const vm = require('node:vm');
const script = readFileSync(join(__dirname, '../js/site.js'), 'utf8');
const themeScript = readFileSync(join(__dirname, '../js/theme.js'), 'utf8');

function setup(hash = '', options = {}) {
  const events = {}, loaded = [], nodes = new Map(), observers = [];
  function element(id) {
    const attrs = new Map();
    const classes = new Set();
    const node = {
      id, hidden: false, textContent: '', scrolled: 0,
      setAttribute(k, v) { attrs.set(k, v); },
      getAttribute(k) { return attrs.get(k) ?? null; },
      removeAttribute(k) { attrs.delete(k); },
      addEventListener(k, fn) { this[k] = fn; },
      classList: {add(k) { classes.add(k); }, toggle(k, state) { state ? classes.add(k) : classes.delete(k); }},
      scrollIntoView() { this.scrolled++; },
      getBoundingClientRect() { return {top: this.top || 0, height: this.height ?? 24}; },
      scrollTo(position) { this.position = position; this.scrollTop = position.top; },
      focus(options) { this.focused = true; this.focusOptions = options; },
      select() { this.selected = true; },
      animate(frames, options) { this.animation = {frames, options}; },
      remove() { this.removed = true; },
      querySelectorAll() { return []; },
      closest(selector) { return selector === 'details' ? this.category : null; },
    };
    nodes.set(id, node);
    return node;
  }
  const rail = element('navigation'), menu = element('menu'), intro = element('overview'), content = element('api-content');
  rail.scrollTop = 0;
  const themeToggle = element('theme-toggle');
  const themeIcons = ['wave', 'lotus', 'dragon'].map(themeIcon => ({dataset: {themeIcon}}));
  themeToggle.querySelectorAll = () => themeIcons;
  menu.setAttribute('aria-expanded', 'false');
  const links = ['section-A', 'method-A', 'section-B', 'method-B'].map(id => {
    const node = element(id);
    node.hash = '#' + id;
    node.dataset = {section: id.endsWith('A') ? 'section-A' : 'section-B'};
    node.caret = {};
    node.querySelector = selector => selector === '.nav-letter' ? node.letter : node.caret;
    if (id.startsWith('section-')) {
      const children = element('nav-' + id);
      children.hidden = true;
      node.setAttribute('aria-controls', children.id);
      node.setAttribute('aria-expanded', 'false');
    }
    return node;
  });
  const category = element('category-objects');
  category.open = false;
  const categorySummary = element('category-summary');
  category.querySelector = () => categorySummary;
  for (const link of links) link.category = category;
  links.find(a => a.id === 'method-A').dataset.aliases = 'signature-A signature-A2';
  element('signature-A');
  element('signature-A2');
  rail.querySelectorAll = selector => selector === '.nav-group-link' ? links.filter(a => a.id.startsWith('section-')) : links;
  let markup = '';
  Object.defineProperty(content, 'innerHTML', {get: () => markup, set: value => { markup = value; }});
  content.replaceChildren = () => { markup = ''; content.textContent = ''; };
  let currentHash = hash;
  const baseUrl = new URL(options.url || 'file:///C:/docs/index.html');
  const location = {search: baseUrl.search, get href() { const url = new URL(baseUrl); url.hash = currentHash; return url.href; },
    get hash() { return currentHash; }, set hash(value) { currentHash = value; events.hashchange?.(); }};
  const window = {scrollX: 0, scrollY: 0, innerHeight: 800, scrollTo(position) { this.position = position; },
    history: {replaceState(state, title, url) { this.replacedUrl = url; }},
    matchMedia: () => ({matches: false}), addEventListener(k, fn) { events[k] = fn; }};
  const document = {
    documentElement: {dataset: {}},
    querySelector: selector => nodes.get(selector.slice(1)),
    getElementById: id => nodes.get(id),
    addEventListener(k, fn) {
      const previous = events[k];
      events[k] = previous ? event => { previous(event); fn(event); } : fn;
    },
    createElement: tag => element(tag === 'textarea' ? 'clipboard-field' : 'script-' + loaded.length),
    head: {append(node) { loaded.push(node); }},
    body: {append() {}},
    execCommand(command) { return options.copyFallback?.(command) ?? false; },
  };
  const storage = new Map(options.savedTheme ? [['kag-docs-theme', options.savedTheme]] : []);
  const localStorage = {getItem(key) { if (options.storageBlocked) throw Error('Blocked'); return storage.get(key); },
    setItem(key, value) { if (options.storageBlocked) throw Error('Blocked'); storage.set(key, value); }};
  if (options.sourcePage) {
    element('source-back').href = '../index.html';
    for (const id of ['L1', 'L74', 'L80']) element(id);
    nodes.delete('api-content');
  }
  const context = vm.createContext({window, document, location, localStorage, URL, URLSearchParams, navigator: {clipboard: options.clipboard}, requestAnimationFrame: fn => fn(), IntersectionObserver: class {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe() {}
    disconnect() { this.disconnected = true; }
  }});
  vm.runInContext(themeScript, context);
  vm.runInContext(script, context);
  return {window, document, nodes, loaded, content, intro, rail, menu, themeToggle, storage, themeIcons, observers,
    navigate(id) { location.hash = '#' + id; },
    receive(section, html) { window.KAGDocs.sectionLoaded(section, html); },
    key(event) { events.keydown(event); },
    async load() { await events.load?.(); },
    async source(href) {
      const link = element('source-link');
      link.setAttribute('href', href);
      await events.click({target: {closest: selector => selector === '[data-source-link]' ? link : null}});
      return link.href;
    },
    copy(text) {
      const code = element('hook-signature');
      code.textContent = text;
      const button = element('copy-button'), label = element('copy-label');
      button.setAttribute('data-copy', code.id);
      button.querySelector = () => label;
      return events.click({target: {closest: selector => selector === '[data-copy]' ? button : null}}).then(() => label.textContent);
    },
  };
}

test('linked source lines center after load and on subsequent line navigation', async () => {
  const s = setup('#L74', {sourcePage: true});
  s.window.scrollY = 1000;
  s.nodes.get('L74').top = 300;
  assert.equal(s.window.position, undefined);
  await s.load();
  assert.equal(s.window.position.top, 912);
  s.nodes.get('L80').top = 500;
  s.navigate('L80');
  assert.equal(s.window.position.top, 1112);
  s.navigate('L1');
  assert.equal(s.window.position.top, 612);
});

test('source visits without a valid line fragment leave scrolling unchanged', async () => {
  const s = setup('', {sourcePage: true});
  await s.load();
  assert.equal(s.window.position, undefined);
  s.navigate('L999');
  assert.equal(s.window.position, undefined);
});

test('source links and API return links preserve the signature and exact scroll position', async () => {
  const docs = setup('#method-A');
  docs.window.scrollY = 1234;
  docs.rail.scrollTop = 345;
  const sourceUrl = await docs.source('source/test.html?ref=signature-A#L74');
  const source = setup('#L74', {url: sourceUrl, sourcePage: true});
  const backUrl = source.nodes.get('source-back').href;
  assert.equal(new URL(backUrl).hash, '#signature-A');
  const returned = setup('#signature-A', {url: backUrl});
  assert.equal(returned.window.position, undefined);
  returned.receive('section-A', 'A');
  assert.equal(returned.window.position.top, 1234);
  assert.equal(returned.rail.scrollTop, 345);
  assert.equal(new URL(returned.window.history.replacedUrl).search, '?theme=wave');
  returned.navigate('method-A');
  assert.equal(returned.nodes.get('method-A').scrolled, 1);
});

test('direct source visits keep the overview fallback and reject invalid return metadata', () => {
  const direct = new URL(setup('', {sourcePage: true}).nodes.get('source-back').href);
  assert.equal(direct.pathname, '/C:/index.html');
  assert.equal(direct.hash, '');
  const source = setup('', {sourcePage: true, url: 'file:///C:/docs/source/test.html?ref=method-A&doc-y=NaN'});
  const back = new URL(source.nodes.get('source-back').href);
  assert.equal(back.hash, '#method-A');
  assert.equal(back.search, '?theme=wave');
});

test('theme survives source navigation and return with isolated or blocked local-file storage', async () => {
  for (const storageBlocked of [false, true]) {
    const docs = setup('#method-A', {storageBlocked});
    docs.themeToggle.click();
    const url = await docs.source('source/test.html?ref=method-A#L1');
    const source = setup('#L1', {url, sourcePage: true, storageBlocked});
    assert.equal(source.document.documentElement.dataset.theme, 'lotus');
    const backUrl = source.nodes.get('source-back').href;
    const returned = setup('#method-A', {url: backUrl, storageBlocked});
    assert.equal(returned.document.documentElement.dataset.theme, 'lotus');
    returned.themeToggle.click();
    assert.equal(new URL(returned.window.history.replacedUrl).searchParams.get('theme'), 'dragon');
    const dragonUrl = await returned.source('source/test.html?ref=method-A#L1');
    const dragonSource = setup('#L1', {url: dragonUrl, sourcePage: true, storageBlocked});
    assert.equal(dragonSource.document.documentElement.dataset.theme, 'dragon');
  }
});

test('invalid navigation themes defer to the saved preference', () => {
  const s = setup('', {url: 'file:///C:/docs/index.html?theme=invalid', savedTheme: 'lotus'});
  assert.equal(s.document.documentElement.dataset.theme, 'lotus');
});

test('hook copy writes the complete signature through the Clipboard API', async () => {
  const writes = [];
  const s = setup('', {clipboard: {async writeText(text) { writes.push(text); }}});
  const signature = 'void onCommand(CBlob@ this, u8 cmd, CBitStream@ params)';
  assert.equal(await s.copy(signature), 'Copied');
  assert.deepEqual(writes, [signature]);
  const button = s.nodes.get('copy-button');
  assert.equal(button.animation.options.duration, 600);
  assert.equal(button.animation.frames[1].color, 'var(--color-green)');
  assert.equal(button.getAttribute('title'), 'Copied');
});

test('offline clipboard fallback selects the signature, cleans up and restores focus', async () => {
  const s = setup('', {clipboard: {async writeText() { throw Error('Blocked'); }},
    copyFallback(command) { assert.equal(command, 'copy'); return true; }});
  s.document.activeElement = s.menu;
  assert.equal(await s.copy('void onTick(CBlob@)'), 'Copied');
  const field = s.nodes.get('clipboard-field');
  assert.equal(field.value, 'void onTick(CBlob@)');
  assert.equal(field.selected, true);
  assert.equal(field.removed, true);
  assert.equal(s.menu.focused, true);
});

test('unavailable clipboard reports failure without claiming a copy succeeded', async () => {
  const s = setup();
  assert.equal(await s.copy('void onTick(CBlob@)'), 'Copy failed');
  assert.equal(s.nodes.get('clipboard-field').removed, true);
  assert.equal(s.nodes.get('copy-button').animation, undefined);
});

test('overview renders no API section or payload', () => {
  const s = setup();
  assert.equal(s.loaded.length, 0);
  assert.equal(s.content.innerHTML, '');
  assert.equal(s.intro.hidden, false);
});

test('deep link loads only its group and same-group navigation reuses DOM', () => {
  const s = setup('#method-A');
  assert.equal(s.loaded.length, 1);
  assert.equal(s.loaded[0].src, 'sections/section-A.js');
  s.receive('section-A', '<section>A</section>');
  assert.equal(s.content.innerHTML, '<section>A</section>');
  assert.equal(s.nodes.get('method-A').scrolled, 1);
  assert.equal(s.intro.hidden, true);
  s.navigate('section-A');
  assert.equal(s.loaded.length, 1);
  assert.equal(s.content.innerHTML, '<section>A</section>');
});

test('old signature links load their family and retain the single active navbar entry', () => {
  const s = setup('#signature-A');
  assert.equal(s.loaded[0].src, 'sections/section-A.js');
  s.receive('section-A', 'A');
  assert.equal(s.nodes.get('signature-A').scrolled, 1);
  assert.equal(s.nodes.get('method-A').getAttribute('aria-current'), 'location');
  s.window.KAGDocs.navigate('signature-A2');
  assert.equal(s.nodes.get('signature-A2').scrolled, 1);
  assert.equal(s.nodes.get('method-A').getAttribute('aria-current'), 'location');
  assert.equal(s.loaded.length, 1);
});

test('quicksearch navigation bridge can jump again to the current anchor', () => {
  const s = setup('#method-A');
  s.receive('section-A', 'A');
  const before = s.nodes.get('method-A').scrolled;
  s.window.KAGDocs.navigate('method-A');
  assert.equal(s.nodes.get('method-A').scrolled, before + 1);
  s.window.KAGDocs.navigate('method-B');
  assert.equal(s.loaded[1].src, 'sections/section-B.js');
});

test('scroll focus moves the eye without changing the selected entry', () => {
  const s = setup('#method-A');
  s.receive('section-A', 'A');
  const selected = s.nodes.get('method-A'), second = s.nodes.get('method-B');
  const observer = s.observers.at(-1);
  observer.callback([{target: second, isIntersecting: true}]);
  assert.equal(selected.getAttribute('aria-current'), 'location');
  assert.equal(selected.getAttribute('data-viewed'), null);
  assert.equal(second.getAttribute('data-viewed'), 'true');
  // Overload aliases share one navbar eye, just as they share one entry.
  observer.callback([{target: second, isIntersecting: false}, {target: s.nodes.get('signature-A2'), isIntersecting: true}]);
  assert.equal(selected.getAttribute('data-viewed'), 'true');
});

test('eye follows all visible intersections, clears on exit, and ignores stale callbacks', () => {
  const s = setup('#section-A');
  s.receive('section-A', 'A');
  const first = s.nodes.get('method-A'), second = s.nodes.get('method-B');
  first.top = -20;
  second.top = 50;
  const observer = s.observers.at(-1);
  observer.callback([{target: first, isIntersecting: true}]);
  assert.equal(first.getAttribute('data-viewed'), 'true');
  observer.callback([{target: second, isIntersecting: true}]);
  assert.equal(first.getAttribute('data-viewed'), 'true');
  assert.equal(second.getAttribute('data-viewed'), null);
  observer.callback([{target: first, isIntersecting: false}]);
  assert.equal(first.getAttribute('data-viewed'), null);
  assert.equal(second.getAttribute('data-viewed'), 'true');
  assert.equal(s.nodes.get('section-A').getAttribute('aria-current'), 'location');
  s.navigate('overview');
  assert.equal(second.getAttribute('data-viewed'), null);
  observer.callback([{target: first, isIntersecting: true}]);
  assert.equal(first.getAttribute('data-viewed'), null);
});

test('clicking an already selected navbar entry preserves selection and scrolls again', () => {
  const s = setup('#method-A');
  s.receive('section-A', 'A');
  const entry = s.nodes.get('method-A');
  const before = entry.scrolled;
  s.rail.click({preventDefault() {}, target: {closest: selector => selector === '.nav-entry' || selector === 'a' ? entry : null}});
  assert.equal(entry.getAttribute('aria-current'), 'location');
  assert.equal(entry.scrolled, before + 1);
});

test('letter hotkeys open and highlight the closest section, smoothly positioning it a quarter down the navbar', () => {
  const s = setup('#method-A');
  s.receive('section-A', 'A');
  const first = s.nodes.get('section-A'), second = s.nodes.get('section-B');
  first.letter = second.letter = {textContent: 'C'};
  first.top = -300;
  second.top = 140;
  s.rail.height = 400;
  s.rail.top = 20;
  s.rail.scrollTop = 500;
  let prevented = 0;
  s.key({key: 'c', preventDefault() { prevented++; }});
  assert.equal(second.focused, true);
  assert.equal(first.focused, undefined);
  assert.equal(second.focusOptions.preventScroll, true);
  assert.equal(s.rail.position.top, 520); // 500 + 140 - 20 - 25% of 400px
  assert.equal(s.rail.position.behavior, 'smooth');
  assert.equal(s.nodes.get('method-A').getAttribute('aria-current'), null);
  assert.equal(second.getAttribute('aria-current'), 'location');
  assert.equal(second.getAttribute('data-active'), 'true');
  assert.equal(second.getAttribute('aria-expanded'), 'true');
  assert.equal(s.nodes.get('nav-section-B').hidden, false);
  assert.equal(s.loaded.length, 2);
  s.receive('section-B', 'B');
  assert.equal(s.content.innerHTML, 'B');
  assert.equal(prevented, 1);
  first.top = -20;
  second.top = 400;
  s.key({key: 'C', preventDefault() { prevented++; }});
  assert.equal(first.focused, true);
  assert.equal(first.getAttribute('aria-current'), 'location');
  assert.equal(first.getAttribute('aria-expanded'), 'true');
  assert.equal(s.content.innerHTML, 'A');
  assert.equal(prevented, 2);
});

test('letter hotkeys keep an already open section expanded and respect reduced motion', () => {
  const s = setup('#section-A');
  s.receive('section-A', 'A');
  const header = s.nodes.get('section-A');
  header.letter = {textContent: 'A'};
  header.setAttribute('aria-expanded', 'true');
  s.nodes.get('nav-section-A').hidden = false;
  s.window.matchMedia = query => ({matches: query.includes('prefers-reduced-motion')});
  s.key({key: 'a', preventDefault() {}});
  assert.equal(s.rail.position.behavior, 'instant');
  assert.equal(header.getAttribute('aria-expanded'), 'true');
  assert.equal(s.nodes.get('nav-section-A').hidden, false);
  assert.equal(s.loaded.length, 1);
  assert.equal(s.content.innerHTML, 'A');
});

test('letter hotkeys leave typing widgets, modal search, and modified shortcuts alone', () => {
  const s = setup('#method-A');
  s.nodes.get('section-A').letter = {textContent: 'A'};
  const ignored = [
    {ctrlKey: true}, {metaKey: true}, {altKey: true}, {isComposing: true}, {defaultPrevented: true},
    {target: {isContentEditable: true}},
    {target: {closest: () => ({tagName: 'INPUT'})}},
  ];
  for (const fields of ignored) s.key({key: 'a', preventDefault() { assert.fail('Consumed a widget or shortcut key'); }, ...fields});
  s.nodes.set('quick-search', {open: true});
  s.key({key: 'a', preventDefault() { assert.fail('Consumed search input'); }});
  assert.equal(s.rail.position, undefined);
});

test('letter hotkeys ignore collapsed groups, hidden navigation, and unmatched letters', () => {
  const s = setup('#method-A');
  const header = s.nodes.get('section-A');
  header.letter = {textContent: 'A'};
  const event = {key: 'a', preventDefault() { assert.fail('Consumed a key without a visible matching header'); }};
  header.category.open = false;
  s.key(event);
  header.category.open = true;
  s.rail.height = 0;
  s.key(event);
  s.rail.height = 24;
  s.key({...event, key: 'z'});
  assert.equal(s.rail.position, undefined);
});

test('deep links reveal collapsed categories and category toggles preserve the active page', () => {
  const s = setup('#method-A');
  const category = s.nodes.get('category-objects');
  assert.equal(category.open, true);
  s.receive('section-A', 'A');
  category.open = false;
  assert.equal(s.content.innerHTML, 'A');
  s.navigate('method-B');
  assert.equal(category.open, true);
});

test('section changes discard old DOM; Back reuses a cached section', () => {
  const s = setup('#method-A');
  s.receive('section-A', 'A');
  s.navigate('method-B');
  assert.equal(s.content.innerHTML, '');
  s.receive('section-B', 'B');
  assert.equal(s.content.innerHTML, 'B');
  s.navigate('method-A');
  assert.equal(s.content.innerHTML, 'A');
  assert.equal(s.loaded.length, 2);
});

test('a stale payload response cannot replace the active section', () => {
  const s = setup('#method-A');
  s.navigate('method-B');
  s.receive('section-A', 'stale A');
  assert.equal(s.content.innerHTML, '');
  s.receive('section-B', 'current B');
  assert.equal(s.content.innerHTML, 'current B');
});

test('overview clears content and malformed hashes are handled', () => {
  const s = setup('#method-A');
  s.receive('section-A', 'A');
  s.navigate('overview');
  assert.equal(s.content.innerHTML, '');
  assert.equal(s.intro.hidden, false);
  s.navigate('%broken');
  assert.equal(s.intro.hidden, false);
});

test('load failure reports an error and allows another section', () => {
  const s = setup('#method-A');
  s.loaded[0].onerror();
  assert.match(s.content.textContent, /Unable to load/);
  assert.equal(s.content.getAttribute('aria-busy'), null);
  s.navigate('method-B');
  s.receive('section-B', 'B');
  assert.equal(s.content.innerHTML, 'B');
});

test('whole header toggles, navigates and remains active while collapsed', () => {
  const s = setup();
  const header = s.nodes.get('section-A'), children = s.nodes.get('nav-section-A');
  const event = {preventDefault() {}, target: {closest: selector => selector === '.nav-group-link' || selector === 'a' ? header : null}};
  s.rail.click(event);
  assert.equal(children.hidden, false);
  assert.equal(header.getAttribute('aria-expanded'), 'true');
  assert.equal(header.getAttribute('data-active'), 'true');
  assert.equal(s.loaded[0].src, 'sections/section-A.js');
  s.receive('section-A', 'A');
  s.rail.click(event);
  assert.equal(children.hidden, true);
  assert.equal(header.getAttribute('data-active'), 'true');
  assert.equal(s.content.innerHTML, 'A');
  s.navigate('method-B');
  assert.equal(header.getAttribute('data-active'), null);
  assert.equal(s.nodes.get('section-B').getAttribute('data-active'), 'true');
});

test('Escape closes the mobile menu and returns keyboard focus', () => {
  const s = setup();
  s.menu.click();
  assert.equal(s.menu.getAttribute('aria-expanded'), 'true');
  s.key({key: 'Escape'});
  assert.equal(s.menu.getAttribute('aria-expanded'), 'false');
  assert.equal(s.menu.focused, true);
});

test('Escape in quicksearch does not also close the underlying mobile menu', () => {
  const s = setup();
  s.nodes.set('quick-search', {open: true});
  s.menu.click();
  s.key({key: 'Escape'});
  assert.equal(s.menu.getAttribute('aria-expanded'), 'true');
});

test('theme button cycles Wave, Lotus and Dragon and saves each preference', () => {
  const s = setup();
  assert.equal(s.document.documentElement.dataset.theme, 'wave');
  assert.equal(s.themeToggle.getAttribute('aria-label'), 'Switch to Kanagawa Lotus theme');
  s.themeToggle.click();
  assert.equal(s.document.documentElement.dataset.theme, 'lotus');
  assert.equal(s.storage.get('kag-docs-theme'), 'lotus');
  assert.equal(s.themeToggle.getAttribute('aria-label'), 'Switch to Kanagawa Dragon theme');
  s.themeToggle.click();
  assert.equal(s.document.documentElement.dataset.theme, 'dragon');
  assert.equal(s.storage.get('kag-docs-theme'), 'dragon');
  assert.equal(s.themeToggle.getAttribute('aria-label'), 'Switch to Kanagawa Wave theme');
  s.themeToggle.click();
  assert.equal(s.document.documentElement.dataset.theme, 'wave');
  assert.equal(s.storage.get('kag-docs-theme'), 'wave');
});

test('saved theme is applied before rendering, and invalid values fall back', () => {
  const s = setup('', {savedTheme: 'lotus'});
  assert.equal(s.document.documentElement.dataset.theme, 'lotus');
  assert.equal(s.themeToggle.getAttribute('aria-label'), 'Switch to Kanagawa Dragon theme');
  assert.equal(setup('', {savedTheme: 'dragon'}).document.documentElement.dataset.theme, 'dragon');
  assert.equal(setup('', {savedTheme: 'invalid'}).document.documentElement.dataset.theme, 'wave');
});

test('theme toggle still works when file-origin storage is blocked', () => {
  const s = setup('', {storageBlocked: true});
  s.themeToggle.click();
  assert.equal(s.document.documentElement.dataset.theme, 'lotus');
  s.themeToggle.click();
  assert.equal(s.document.documentElement.dataset.theme, 'dragon');
  s.themeToggle.click();
  assert.equal(s.document.documentElement.dataset.theme, 'wave');
});
