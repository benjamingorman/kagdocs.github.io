const {test} = require('node:test');
const assert = require('node:assert/strict');
const {prepare, search, init} = require('../js/search.js');

const declarations = [
  {id: 'map', section: 'map', name: 'CMap', label: 'CMap', kind: 'section'},
  {id: 'tile-vector', section: 'map', name: 'getTile', label: 'CMap::getTile', kind: 'method', declaration: 'Tile getTile(Vec2f)'},
  {id: 'tile-offset', section: 'map', name: 'getTile', label: 'CMap::getTile', kind: 'method', declaration: 'Tile getTile(uint)'},
  {id: 'size', section: 'map', name: 'tilesize', label: 'CMap::tilesize', kind: 'property'},
  {id: 'string', section: 'string', name: 'string', label: 'string', kind: 'section'},
  {id: 'print', section: 'globals', name: 'print', label: 'print', kind: 'function'},
  {id: 'enum', section: 'map', name: 'TileEnum', label: 'CMap::TileEnum', kind: 'enum'},
];

test('case-insensitive exact, qualified and signature searches distinguish overloads', () => {
  const items = prepare(declarations);
  assert.equal(search(items, 'GETTILE')[0].id, 'tile-vector');
  assert.equal(search(items, 'CMap.getTile uint')[0].id, 'tile-offset');
  assert.equal(search(items, 'CMap::getTile Vec2f')[0].id, 'tile-vector');
});

test('an overload family is one result searchable by any of its signatures', () => {
  const items = prepare([{id: 'tiles', section: 'map', name: 'getTile', label: 'CMap::getTile',
    kind: 'method', declaration: 'Tile getTile(Vec2f)\nTile getTile(uint)'}]);
  for (const query of ['getTile', 'getTile Vec2f', 'getTile uint']) {
    assert.deepEqual(search(items, query).map(item => item.id), ['tiles']);
  }
});

test('community guides are searchable alongside API declarations', () => {
  const items = prepare([...declarations, {id: 'guide-tcpr-article', section: 'guide-tcpr', name: 'TCPR protocol', label: 'TCPR protocol', kind: 'guide'}]);
  assert.equal(search(items, 'tcpr')[0].id, 'guide-tcpr-article');
  assert.equal(search(items, 'protocol')[0].kind, 'guide');
});

test('functions, variables, enums and top-level types are all searchable', () => {
  const items = prepare(declarations);
  for (const [query, id] of [['print', 'print'], ['tilesize', 'size'], ['TileEnum', 'enum'], ['string', 'string']]) {
    assert.equal(search(items, query)[0].id, id);
  }
});

test('fuzzy abbreviations work, missing results are empty and output is bounded', () => {
  const items = prepare(declarations);
  assert.equal(search(items, 'gtt')[0].id, 'tile-vector');
  assert.equal(search(items, 'nothing matches xyz').length, 0);
  const many = prepare(Array.from({length: 100}, (_, i) => ({name: 'test' + i, label: 'test' + i, kind: 'function'})));
  assert.equal(search(many, 'test').length, 40);
  assert.equal(search(many, 'test', 5).length, 5);
  assert.ok(search(items, '').every(item => item.kind === 'section'));
});

function setup(platform = 'Win32') {
  const ids = new Map(), events = new Map(), navigated = [];
  let document;
  function node(id = '') {
    const handlers = new Map(), attrs = new Map();
    const n = {
      id, dataset: {}, children: [], value: '', hidden: false, open: false, isConnected: true,
      classList: {contains: cls => cls === 'nav-group-link' && n.dataset.searchKind === 'section'},
      addEventListener(name, callback) { handlers.set(name, callback); },
      fire(name, extra = {}) { handlers.get(name)?.({target: n, preventDefault() {}, ...extra}); },
      setAttribute(name, value) { attrs.set(name, value); },
      removeAttribute(name) { attrs.delete(name); },
      getAttribute(name) { return attrs.get(name) ?? null; },
      append(...children) { n.children.push(...children); },
      replaceChildren() { n.children = []; },
      focus() { document.activeElement = n; },
      select() { n.selected = true; },
      scrollIntoView() {},
      scrollTo(position) { n.scrollTop = position.top; n.scrollBehavior = position.behavior; },
      showModal() { n.open = true; },
      close() { n.open = false; n.fire('close'); },
      querySelector() { return n.caret || (n.caret = {}); },
      closest(selector) {
        if (selector === 'details') return n.category || null;
        return selector === '[data-result-index]' && n.dataset.resultIndex !== undefined ? n : null;
      },
      getBoundingClientRect() {
        const top = n.top ?? 10;
        const height = n.height ?? 40;
        return {left: 10, right: 600, top, bottom: top + height, height, width: 590};
      },
    };
    if (id) ids.set(id, n);
    return n;
  }
  for (const id of ['quick-search', 'search-open', 'search-input', 'search-results', 'search-status', 'search-close', 'search-shortcut']) node(id);
  const links = declarations.map(item => {
    const n = node();
    n.hash = '#' + item.id;
    n.dataset = {section: item.section, searchName: item.name, searchLabel: item.label, searchKind: item.kind};
    n.setAttribute('title', item.declaration || item.label);
    if (item.kind === 'section') {
      n.setAttribute('aria-controls', 'nav-' + item.section);
      n.setAttribute('aria-expanded', 'false');
      node('nav-' + item.section).hidden = true;
    }
    return n;
  });
  const rail = node('navigation');
  rail.scrollTop = 0;
  const category = node('category-globals');
  category.open = false;
  for (const link of links) link.category = category;
  document = {
    activeElement: ids.get('search-open'), body: {style: {overflow: ''}},
    getElementById: id => ids.get(id), querySelectorAll: () => links,
    createElement: () => node(), addEventListener(name, callback) { events.set(name, callback); },
  };
  const window = {navigator: {platform}, KAGDocs: {navigate: id => navigated.push(id)}};
  init(document, window);
  return {document, links, navigated, get: id => ids.get(id),
    key(key, extra = {}) { events.get('keydown')?.({key, preventDefault() {}, ...extra}); },
    query(value) { ids.get('search-input').value = value; ids.get('search-input').fire('input'); },
  };
}

test('navbar opens a modal, focuses the input, locks scrolling and restores focus on Escape', () => {
  const s = setup();
  s.get('search-open').fire('click');
  assert.equal(s.get('quick-search').open, true);
  assert.equal(s.document.activeElement, s.get('search-input'));
  assert.equal(s.document.body.style.overflow, 'hidden');
  s.key('Escape');
  assert.equal(s.get('quick-search').open, false);
  assert.equal(s.document.body.style.overflow, '');
  assert.equal(s.document.activeElement, s.get('search-open'));
});

test('Cmd-K and Ctrl-K open search and display the platform shortcut', () => {
  for (const [platform, modifier, label] of [['MacIntel', 'metaKey', '⌘ K'], ['Win32', 'ctrlKey', 'Ctrl K']]) {
    const s = setup(platform);
    s.key('k', {[modifier]: true});
    assert.equal(s.get('quick-search').open, true);
    assert.equal(s.get('search-shortcut').textContent, label);
    s.query('getTile');
    s.key('k', {[modifier]: true});
    assert.equal(s.get('search-input').value, 'getTile');
    assert.equal(s.get('search-input').selected, true);
  }
});

test('keyboard selection jumps to an unloaded method and expands its collapsed group', () => {
  const s = setup();
  const rail = s.get('navigation');
  rail.scrollTop = 80;
  rail.top = 100;
  rail.height = 400;
  const link = s.links.find(entry => entry.hash === '#tile-offset');
  link.top = 960;
  link.height = 24;
  s.key('k', {ctrlKey: true});
  s.query('getTile');
  assert.equal(s.get('search-results').children.length, 2);
  s.get('search-input').fire('keydown', {key: 'ArrowDown'});
  assert.equal(s.get('search-input').getAttribute('aria-activedescendant'), 'search-result-1');
  s.get('search-input').fire('keydown', {key: 'Enter'});
  assert.deepEqual(s.navigated, ['tile-offset']);
  assert.equal(link.getAttribute('aria-current'), 'location');
  assert.equal(s.links.find(entry => entry.hash === '#tile-vector').getAttribute('aria-current'), null);
  assert.equal(rail.scrollTop, 80 + 960 - 100 - 100);
  assert.equal(rail.scrollBehavior, 'smooth');
  assert.equal(s.get('nav-map').hidden, false);
  assert.equal(s.get('category-globals').open, true);
  assert.equal(s.get('quick-search').open, false);
});

test('empty results clear active selection and Enter does not navigate', () => {
  const s = setup();
  s.get('search-open').fire('click');
  s.query('nothing matches xyz');
  assert.equal(s.get('search-results').children.length, 0);
  assert.equal(s.get('search-input').getAttribute('aria-activedescendant'), null);
  assert.equal(s.get('search-status').textContent, 'No matching API names');
  s.get('search-input').fire('keydown', {key: 'Enter'});
  assert.deepEqual(s.navigated, []);
});

test('mouse selection and backdrop dismissal work without loading other sections', () => {
  const s = setup();
  s.get('search-open').fire('click');
  s.query('tilesize');
  const row = s.get('search-results').children[0];
  s.get('search-results').fire('click', {target: row});
  assert.deepEqual(s.navigated, ['size']);
  s.get('search-open').fire('click');
  s.get('quick-search').fire('click', {clientX: 0, clientY: 0});
  assert.equal(s.get('quick-search').open, false);
});
