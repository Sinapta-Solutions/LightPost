import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../web/theme.js', import.meta.url), 'utf8');
function browser({ saved, dark = false, blocked = false, noSystem = false } = {}) {
  const listeners = {};
  const system = {
    matches: dark,
    addEventListener: (name, fn) => {
      listeners[name] = fn;
    },
  };
  const values = new Map(saved === undefined ? [] : [['lightpost-theme', saved]]);
  const button = {
    attributes: {},
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
  };
  const meta = {
    setAttribute(name, value) {
      this[name] = value;
    },
  };
  const document = {
    documentElement: { dataset: {} },
    querySelector: () => meta,
    querySelectorAll: () => [button],
  };
  const window = {
    matchMedia: noSystem ? undefined : () => system,
    localStorage: {
      getItem(key) {
        if (blocked) throw Error('Storage blocked');
        return values.get(key) ?? null;
      },
      setItem(key, value) {
        if (blocked) throw Error('Storage blocked');
        values.set(key, value);
      },
    },
    addEventListener(name, fn) {
      listeners[name] = fn;
    },
  };
  vm.runInNewContext(source, { window, document });
  return { window, document, values, button, meta, system, listeners };
}

test('initial theme uses device preference unless a valid saved choice exists', () => {
  assert.equal(browser({ dark: true }).window.lightpostTheme.current(), 'dark');
  assert.equal(browser({ dark: true, saved: 'light' }).window.lightpostTheme.current(), 'light');
  assert.equal(browser({ dark: false, saved: 'dark' }).window.lightpostTheme.current(), 'dark');
  assert.equal(browser({ dark: true, saved: 'invalid' }).window.lightpostTheme.current(), 'dark');
  assert.equal(browser({ noSystem: true }).window.lightpostTheme.current(), 'light');
});

test('toggle persists across page loads and updates switch and browser colors', () => {
  const page = browser();
  page.window.lightpostTheme.toggle();
  assert.equal(page.document.documentElement.dataset.theme, 'dark');
  assert.equal(page.button.attributes['aria-checked'], 'true');
  assert.equal(page.button.title, 'Switch to light theme');
  assert.equal(page.meta.content, '#101722');
  assert.equal(
    browser({ saved: page.values.get('lightpost-theme') }).window.lightpostTheme.current(),
    'dark',
  );
  page.window.lightpostTheme.toggle();
  assert.equal(page.window.lightpostTheme.current(), 'light');
  assert.equal(page.button.attributes['aria-checked'], 'false');
  assert.equal(page.values.get('lightpost-theme'), 'light');
  assert.equal(page.meta.content, '#fafaf8');
});

test('blocked storage does not break theme loading or switching', () => {
  const page = browser({ blocked: true, dark: true });
  page.window.lightpostTheme.toggle();
  assert.equal(page.window.lightpostTheme.current(), 'light');
  page.window.lightpostTheme.toggle();
  assert.equal(page.window.lightpostTheme.current(), 'dark');
});

test('device changes apply only until the user chooses a theme', () => {
  const page = browser();
  page.system.matches = true;
  page.listeners.change();
  assert.equal(page.window.lightpostTheme.current(), 'dark');
  page.window.lightpostTheme.toggle();
  page.listeners.change();
  assert.equal(page.window.lightpostTheme.current(), 'light');
});

test('theme preferences synchronize between tabs and reset to device on storage clear', () => {
  const page = browser({ dark: true, saved: 'light' });
  page.listeners.storage({ key: 'unrelated', newValue: 'dark' });
  assert.equal(page.window.lightpostTheme.current(), 'light');
  page.listeners.storage({ key: 'lightpost-theme', newValue: 'dark' });
  assert.equal(page.window.lightpostTheme.current(), 'dark');
  page.listeners.storage({ key: 'lightpost-theme', newValue: 'light' });
  assert.equal(page.window.lightpostTheme.current(), 'light');
  page.listeners.storage({ key: null, newValue: null });
  assert.equal(page.window.lightpostTheme.current(), 'dark');
});

test('theme is loaded before the stylesheet to avoid a light flash on reload', () => {
  const html = readFileSync(new URL('../web/index.html', import.meta.url), 'utf8');
  assert.ok(html.indexOf('src="/theme.js"') < html.indexOf('href="/styles.css"'));
});
