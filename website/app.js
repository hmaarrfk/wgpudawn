// The page: the gallery and the viewer of one example, as two views of one
// document, so that going from one example to another does not load a page
// and does not start Python again (runner.js). The address still says where
// you are: ./ is the gallery, run.html?ex=<id> an example (run.html is a copy
// of index.html), and back and forward work.
import * as runner from './runner.js';

const { supportsWebGPU, canBlock } = runner;
const $ = (id) => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v; else el.setAttribute(k, v === true ? '' : v);
  }
  el.append(...children.filter((c) => c != null));
  return el;
}
function icon(name) {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG, 'use');
  use.setAttribute('href', '#i-' + name);
  svg.append(use);
  return svg;
}
const idle = (f) => (window.requestIdleCallback ? requestIdleCallback(f, { timeout: 2000 }) : setTimeout(f, 300));

const query = new URLSearchParams(location.search);
// check.mjs: one example per page load, and the result on the console
const check = query.has('check');
if (check) document.body.classList.add('check');  // one canvas size for all screenshots

// What check.mjs found. Without it, nothing is claimed about what works.
const resultsLoaded = check ? Promise.resolve(null)
  : fetch('results.json').then((r) => (r.ok ? r.json() : null)).then((json) => (json && json.examples) || null).catch(() => null);
const manifest = await (await fetch('examples.json')).json();
runner.init(manifest);
let results = null;

const examples = manifest.examples;
const byId = new Map(examples.map((example, i) => [example.id, { example, index: i }]));
const urlOf = (example) => `run.html?ex=${encodeURIComponent(example.id)}`;
const webgpu = supportsWebGPU();
const jspi = canBlock();

// ---------------------------------------------------------------- the views

function route() {
  const params = new URLSearchParams(location.search);
  if (!params.has('ex') && !/run\.html$/.test(location.pathname)) return null;
  return (byId.get(params.get('ex')) || byId.get(examples[0].id)).example;
}

let shown;             // the example that the viewer shows; null: the gallery
let galleryScroll = -1;  // where the gallery was when it was left (-1: it was not shown yet)
let galleryUrl = './';  // with its filters
let behindIsGallery = false;  // the previous entry of the history is the gallery
try { history.scrollRestoration = 'manual'; } catch { /* not important */ }

function show(example, how = {}) {
  if (shown === null && example) galleryScroll = scrollY;
  const from = shown;
  shown = example;
  document.body.classList.toggle('run', !!example);
  document.body.classList.toggle('home', !example);
  if (example) {
    if (hero) hero.rest();
    openExample(example, how);
    scrollTo({ top: 0, behavior: 'instant' });
  } else {
    closeExample();
    document.title = 'wgpudawn: the pygfx examples, live in your browser';
    openGallery(from !== undefined);
  }
}

// A link to an example or to the gallery: the same document shows it
function navigate(example, started) {
  if (example === shown) return;
  if (example) {
    behindIsGallery = shown === null;
    history.pushState({ gallery: behindIsGallery }, '', urlOf(example));
    show(example, { started });
  } else if (behindIsGallery) {
    history.back();  // to the gallery as it was; popstate shows it
  } else {
    history.pushState(null, '', galleryUrl);
    show(null);
  }
}
addEventListener('popstate', () => {
  behindIsGallery = !!(history.state && history.state.gallery);
  const example = route();
  if (example !== shown) show(example, { started: Date.now() });
});
addEventListener('click', (event) => {
  if (event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  const link = event.target.closest && event.target.closest('a[href]');
  if (!link || link.target || link.origin !== location.origin) return;
  const here = new URL('.', location.href).pathname;
  const params = new URLSearchParams(link.search);
  if (link.pathname === here + 'run.html' && byId.has(params.get('ex'))) {
    event.preventDefault();
    navigate(byId.get(params.get('ex')).example, Date.now());
  } else if ((link.pathname === here || link.pathname === here + 'index.html') && shown !== null) {
    event.preventDefault();
    navigate(null);
  }
});
addEventListener('keydown', (event) => {
  if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
  const active = document.activeElement;
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((active && active.tagName) || '');
  if (shown) {
    // Not when the example has the keyboard (its canvas takes the focus)
    if (typing || (active && $('frame').contains(active)) || document.fullscreenElement) return;
    const other = event.key === 'ArrowLeft' ? examples[byId.get(shown.id).index - 1]
      : event.key === 'ArrowRight' ? examples[byId.get(shown.id).index + 1] : null;
    if (other) { event.preventDefault(); navigate(other, Date.now()); }
    else if (event.key === 'Escape') { event.preventDefault(); navigate(null); }
  } else if (event.key === '/' && !typing) {
    event.preventDefault();
    $('q').focus();
    $('q').select();
  } else if (event.key === 'Escape' && active === $('q')) {
    $('q').value = ''; state.q = ''; apply();
    $('q').blur();
  }
});

// A new <canvas id="canvas"> for the example that starts: rendercanvas takes
// the element with that id, and removes it when the canvas closes
function mountCanvas(frame, before, attrs) {
  const canvas = h('canvas', { id: 'canvas', ...attrs });
  frame.insertBefore(canvas, before);
  return canvas;
}

// ------------------------------------------------------------- the source

// A small Python highlighter: comments, strings, numbers, keywords, names of defs.
const KEYWORDS = new Set(('False None True and as assert async await break class continue def del elif else except finally for from '
  + 'global if import in is lambda nonlocal not or pass raise return try while with yield').split(' '));
const BUILTINS = new Set('self print len range int float str list dict tuple set bool super isinstance enumerate zip min max abs sum round open type'.split(' '));
const TOKEN = /(#.*)|((?:\b[rbfu]{1,2})?(?:"""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'))|(\b(?:0x[\da-f]+|\d[\d_]*\.?\d*(?:e[+-]?\d+)?j?)\b|\.\d+)|(@[\w.]+)|([A-Za-z_]\w*)/gi;
function highlight(code, into) {
  const out = document.createDocumentFragment();
  let at = 0, previous = '';
  for (const m of code.matchAll(TOKEN)) {
    const word = m[5];
    const cls = m[1] ? 't-c' : m[2] ? 't-s' : m[3] ? 't-n' : m[4] ? 't-d'
      : KEYWORDS.has(word) ? 't-k' : (previous === 'def' || previous === 'class') ? 't-d' : BUILTINS.has(word) ? 't-b' : '';
    if (word) previous = word;
    if (!cls) continue;
    out.append(code.slice(at, m.index));
    const span = document.createElement('span');
    span.className = cls;
    span.textContent = m[0];
    out.append(span);
    at = m.index + m[0].length;
  }
  out.append(code.slice(at));
  into.replaceChildren(out);
}
const sources = new Map();
function sourceOf(example) {
  if (!sources.has(example.id)) {
    const text = fetch(`src/${example.id}.py`).then((r) => (r.ok ? r.text() : Promise.reject(new Error(r.status))));
    text.catch(() => sources.delete(example.id));
    sources.set(example.id, text);
  }
  return sources.get(example.id);
}

// ---------------------------------------------------------------- the viewer

let sourceText = '';
let visit = 0;         // counts the examples that the viewer showed: what is late for one is dropped
let failed = false;    // the example reported an error
let running = false;
let step = 0;
let logged = 0;
let slowTimer = 0;
let attempted = false;  // this page load asked for an example to run
const LOG_LINES = 400;
// For check.mjs --warm: what happened to the example that is shown
const nav = { id: '', state: 'idle', count: 0 };
window.__nav = nav;

function showTab(name) {
  for (const tab of ['source', 'log']) {
    $('tab-' + tab).setAttribute('aria-selected', String(tab === name));
    $(tab + '-pane').hidden = tab !== name;
  }
  if (name === 'log') $('log-dot').hidden = true;
}
$('tab-source').onclick = () => showTab('source');
$('tab-log').onclick = () => showTab('log');
$('copy').onclick = async () => {
  const text = $('log-pane').hidden ? sourceText : $('log').textContent;
  try { await navigator.clipboard.writeText(text); } catch { return; }
  const label = $('copy').querySelector('span');
  label.textContent = 'Copied';
  setTimeout(() => { label.textContent = 'Copy'; }, 1400);
};
$('restart').onclick = () => { if (shown) openExample(shown, { started: Date.now() }); };
$('full').onclick = () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else $('frame').requestFullscreen?.().catch(() => {});
};

// An example that asks for a window size gets a canvas of exactly that size in
// CSS pixels, and the page scales the picture to fit the frame (also in full
// screen). Pointer positions stay right: they are relative to the canvas.
function fit() {
  const frame = $('frame');
  const canvas = frame.querySelector('canvas');
  if (!shown || !shown.fixed_size || !canvas) return;
  const [width, height] = shown.size;
  const scale = Math.min(frame.clientWidth / width, frame.clientHeight / height);
  const x = (frame.clientWidth - width * scale) / 2;
  const y = (frame.clientHeight - height * scale) / 2;
  canvas.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
}
new ResizeObserver(fit).observe($('frame'));

function fact(name, value, cls) {
  const dd = h('dd', { class: cls }, value);
  $('facts').append(h('div', null, h('dt', null, name), dd));
  return dd;
}
// Why it cannot run in a browser (skip), or does not work yet (note)
function why(title, text, error) {
  $('why-title').textContent = title;
  $('why-text').textContent = text;
  $('why').hidden = false;
  $('why-raw').hidden = !error;
  if (error) $('why-error').textContent = error;
}
function say(pill, cls, text) {
  $('pill').textContent = pill;
  $('pill').className = 'pill ' + cls;
  if (text != null) $('state').textContent = text;
}

// The page loads itself again: the one sure way to a new interpreter. The
// address says why, until the page that it loads has read it.
function reload(example, reason, retry, error) {
  try {
    sessionStorage.setItem('wgpudawn-nav', JSON.stringify({ id: example.id, started: nav.started, reason, retry, count: nav.count, error }));
  } catch { /* only for the statistics */ }
  location.replace(`${urlOf(example)}&fresh=${retry ? 'retry' : 'new'}`);
}

function openExample(example, how) {
  const mine = ++visit;
  const { index } = byId.get(example.id);
  const current = () => mine === visit;
  // An earlier page that could not use its interpreter for this example
  let carried = null;
  if (query.has('fresh') && mine === 1) {
    try {
      carried = JSON.parse(sessionStorage.getItem('wgpudawn-nav') || 'null');
      sessionStorage.removeItem('wgpudawn-nav');
    } catch { /* only for the statistics */ }
    if (carried && carried.id !== example.id) carried = null;
    history.replaceState(history.state, '', urlOf(example));
  }
  Object.assign(nav, {
    id: example.id, state: 'loading', count: carried ? carried.count : nav.count + 1,
    started: carried ? carried.started : how.started || (mine === 1 ? Math.round(performance.timeOrigin) : Date.now()),
    fresh: carried ? carried.reason : '', retried: !!(carried && carried.retry),
    before: (carried && carried.error) || '',  // the error that made the page start over
    frame: null, ran: null, run: 0, lazy: [], error: '', memory: null,
  });
  failed = false; running = false; step = 0; logged = 0;

  // The shape of the window that the example asks for; never extreme
  const aspect = Math.min(3.2, Math.max(0.6, example.size[0] / example.size[1]));
  document.documentElement.style.setProperty('--aspect', String(aspect));
  const frame = $('frame');
  frame.classList.toggle('fixed', example.fixed_size);
  frame.style.setProperty('--canvas-w', example.size[0] + 'px');
  frame.style.setProperty('--canvas-h', example.size[1] + 'px');

  document.title = `${example.title} - wgpudawn`;
  $('title').textContent = example.title;
  $('description').textContent = example.description;
  $('category').textContent = manifest.categories.find((c) => c.id === example.category).title;
  $('lines').textContent = `${example.lines} lines`;
  $('github').href = `${manifest.versions.pygfx_repository || 'https://github.com/pygfx/pygfx'}/blob/${manifest.versions.pygfx_commit}/examples/${example.id}.py`;
  for (const [id, other] of [['prev', examples[index - 1]], ['next', examples[index + 1]]]) {
    for (const el of [$(id), $(id + '2')]) {
      el.hidden = !other;
      if (!other) continue;
      el.href = urlOf(other);
      el.querySelector('span').textContent = other.title;
    }
  }

  // The source
  sourceText = '';
  $('source').textContent = '';
  $('nums').textContent = '';
  sourceOf(example).then((text) => {
    if (!current()) return;
    sourceText = text.replace(/\n+$/, '');
    const count = sourceText.split('\n').length;
    $('nums').textContent = Array.from({ length: count }, (_, i) => i + 1).join('\n');
    try { highlight(sourceText, $('source')); } catch { $('source').textContent = sourceText; }
  }).catch(() => { if (current()) $('source').textContent = 'The source could not be loaded. It is on GitHub (the link above).'; });
  showTab('source');
  $('log').textContent = '';
  $('log-dot').hidden = true;
  $('log-dot').classList.remove('err');

  // What is known about it
  $('facts').textContent = '';
  $('why').hidden = true;
  fact('File', `${example.id}.py`);
  if (example.animated) fact('Kind', 'animated');
  const extra = [...example.packages, ...example.pypi].map((p) => p.split('==')[0]);
  if (extra.length) fact('Packages', extra.join(', '));
  const lastCheck = fact('Last check', example.skip ? 'not run' : 'unknown');
  if (example.skip) why('Cannot run in a browser', example.skip);
  else if (example.note) why('Does not work yet', example.note);

  // The stage: the screenshot of the last check, until the example draws
  const overlay = $('overlay');
  overlay.className = 'overlay';
  overlay.hidden = true;
  $('hint').textContent = '';
  $('toast').hidden = true;
  $('sign').firstElementChild.setAttribute('href', '#i-alert');
  $('restart').hidden = $('full').hidden = !!example.skip;
  [...$('steps').children].forEach((el) => el.classList.remove('done'));
  frame.classList.remove('slow');
  frame.classList.toggle('waiting', !check);
  const poster = $('poster');
  poster.hidden = true;
  poster.onload = () => { if (current() && !running && !overlay.classList.contains('failed')) poster.hidden = false; };
  poster.onerror = () => { poster.hidden = true; };
  poster.removeAttribute('src');
  // The overlay with the progress is for a start that takes a while
  clearTimeout(slowTimer);
  slowTimer = setTimeout(() => { if (current() && !running) frame.classList.add('slow'); }, check ? 0 : 350);

  resultsLoaded.then((loaded) => {
    results = loaded;
    const result = results && results[example.id];
    if (!current() || !result || example.skip) return;
    // Something to look at while it loads: what the last check saw
    if (result.ok && result.shot && !running && nav.frame == null) poster.src = result.shot;
    const bad = !result.ok || example.note;
    lastCheck.textContent = bad ? 'does not work yet' : `ran, in ${result.seconds} s`;
    lastCheck.className = bad ? 'bad' : 'good';
    if (!result.ok) {
      const lines = String(result.error || '').trim().split('\n').map((l) => l.trim()).filter(Boolean);
      let last = lines[lines.length - 1] || 'it raised an error.';
      if (!/^[\w.]*(Error|Exception)\b/.test(last)) last = lines.find((l) => l.startsWith('ERROR:')) || last;
      why('Does not work yet', example.note || `The last check of this example failed: ${last}`, result.error);
    }
  });

  // ---------------------------------------------------------------- run it

  // An error in an interpreter that ran other examples before may be theirs:
  // the example gets a new interpreter before a failure is shown
  const retry = (error) => {
    if (check || runner.stats().runs <= 1) return false;
    reload(example, 'it failed after other examples', true, String(error).trim().split('\n').pop().slice(0, 300));
    return true;
  };
  function log(text, kind) {
    if (!current()) return;
    if (kind === 'status') {
      $('status').textContent = text;
      overlay.hidden = !text;
      if (text) {
        step += 1;
        [...$('steps').children].forEach((el, i) => el.classList.toggle('done', i < step));
        say('Loading', 'busy', text);
      }
      return;
    }
    // An error in the draw function repeats every frame: keep the page light
    logged += 1;
    if (check || logged <= LOG_LINES) {
      const line = document.createElement('span');
      line.textContent = text + '\n';
      if (kind === 'err' || kind === 'console') line.className = 'err';
      $('log').append(line);
      if ($('log-pane').hidden) $('log-dot').hidden = false;
    } else if (logged === LOG_LINES + 1) {
      $('log').append(`(More output is not shown, after ${LOG_LINES} lines.)\n`);
    }
    // Errors while drawing are only logged (those of the GPU arrive later, as "ERROR:" lines)
    if (kind === 'err' && /Traceback|Error|ERROR:/.test(text)) {
      $('log-dot').classList.add('err');
      if (!failed) {
        failed = true;
        if (retry(text)) return;
        runner.taint('the previous example reported an error');
        nav.state = 'failed';
        nav.error = nav.error || text;
        showTab('log');
        // The canvas stays: the example may still draw (a part of) its scene
        say('Error', 'bad', 'It reported an error');
        $('toast').hidden = false;
      }
    }
  }
  function fail(message, detail, hint) {
    overlay.hidden = false;
    overlay.classList.add('failed');
    frame.classList.add('slow');
    poster.hidden = true;
    $('status').textContent = message;
    $('hint').textContent = hint || '';
    say('Error', 'bad', 'It did not start.');
    nav.state = 'failed';
    nav.error = nav.error || message;
    if (detail) {
      const line = document.createElement('span');
      line.className = 'err';
      line.textContent = detail + '\n';
      $('log').append(line);
      showTab('log');
    }
    if (check) console.log('EXAMPLE FAIL: ' + message + (detail ? '\n' + detail : ''));
  }
  // The canvas takes the place of the screenshot
  const reveal = () => {
    if (!current()) return;
    frame.classList.remove('waiting');
    poster.hidden = true;
  };

  if (example.skip) {
    runner.stop();
    overlay.hidden = false;
    overlay.classList.add('skipped');
    frame.classList.add('slow');
    $('sign').firstElementChild.setAttribute('href', '#i-desktop');
    $('status').textContent = 'This example cannot run in a browser';
    $('hint').textContent = example.skip;
    say('Not run', '', 'The source is below; it runs on a desktop.');
    nav.state = 'skipped';
    if (check) console.log('EXAMPLE FAIL: This example cannot run in a browser. ' + example.skip);
    return;
  }
  if (!webgpu) {
    say('Loading', 'busy', '');
    fail('This browser does not have WebGPU. Try a recent Chrome or Edge.', '',
      'The example draws with the WebGPU of the browser, through Dawn.');
    return;
  }
  // The interpreter that is there cannot be used for this example, or is stuck
  // (never the one of this page load: a page that cannot start says so)
  const reason = attempted ? runner.mustReload(example) : '';
  if (reason && !check) { reload(example, reason, false); return; }
  attempted = true;
  say('Loading', 'busy', '');
  // Python cannot be interrupted: an example that is still starting holds up the next
  const stuck = setTimeout(() => {
    if (current() && runner.isBlocked()) reload(example, 'the previous example was still starting', false);
  }, 3000);

  (async () => {
    log(runner.describeBrowser(), 'out');
    if (!jspi) {
      log('This browser has no JSPI (WebAssembly stack switching), so Python cannot wait for the browser in the middle of a call. Examples that only draw run; reading back from the GPU, such as picking, raises an error. Recent Chrome, Edge and Safari have it.', 'out');
    }
    try {
      const info = await runner.run(example, {
        log,
        mount: () => { mountCanvas(frame, $('toast')); fit(); nav.run = runner.stats().runs + 1; },
        frame: () => { if (current()) { nav.frame = Date.now() - nav.started; reveal(); } },
      });
      if (!current()) return;
      // Without its GPU device, it draws nothing and reports nothing
      const lost = () => {
        if (!retry('the GPU device was lost')) log('ERROR: The GPU device was lost: the example cannot draw (anymore).', 'err');
      };
      // (check.mjs is not told: without a GPU, headless Chrome loses every device, and CI records what runs)
      if (info.lost && !check) { lost(); if (info.run > 1) return; }
      running = true;
      nav.run = info.run;
      nav.lazy = info.lazy;
      nav.ran = Date.now() - nav.started;
      nav.memory = runner.stats();
      overlay.hidden = true;
      frame.classList.remove('slow');
      const seconds = (nav.ran / 1000).toFixed(nav.ran < 995 ? 2 : 1);
      if (!failed) {
        say('Running', 'on', `Started in ${seconds} s`);
        nav.state = 'running';
      }
      // The first picture comes with the next frame; one that draws nothing must not keep the screenshot
      setTimeout(reveal, check ? 0 : 1500);
      if (!check && !info.lost) {
        setTimeout(async () => { if (current() && !(await runner.hasDevice()) && current()) lost(); }, 1200);
      }
      // Let it draw a few frames; errors while drawing end up in the log
      if (check) {
        await new Promise((resolve) => setTimeout(resolve, 2500));
        console.log(failed ? 'EXAMPLE FAIL: error while drawing\n' + $('log').textContent : 'EXAMPLE OK');
        return;
      }
      // The examples that are likely to be opened next
      idle(() => { if (current()) for (const other of [examples[index + 1], examples[index - 1]]) warmUp(other); });
    } catch (err) {
      if (err instanceof runner.Superseded || !current()) return;
      if (err instanceof runner.Unusable && !check) { reload(example, err.message, false); return; }
      if (retry(err)) return;
      runner.taint('the previous example failed');
      const text = String(err);
      const last = text.trim().split('\n').pop();
      fail(last.length < 200 ? last : 'The example raised an error.', text,
        example.note || 'The full error is in the output below.');
    } finally {
      clearTimeout(stuck);
    }
    if (!current()) return;
    // Which GPU drew it
    try {
      const info = (await navigator.gpu.requestAdapter())?.info;
      const name = info && (info.description || [info.vendor, info.architecture].filter(Boolean).join(' '));
      if (name && current()) fact('GPU', name);
    } catch { /* not important */ }
  })();
}

function closeExample() {
  visit += 1;
  clearTimeout(slowTimer);
  Object.assign(nav, { id: '', state: 'idle' });
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

// What an example needs, into the caches of the browser, before it is opened
function warmUp(example) {
  if (!example || example.skip) return;
  runner.prefetch(example);
  sourceOf(example).catch(() => {});
  const result = results && results[example.id];
  if (result && result.ok && result.shot) new Image().src = result.shot;
}

// ---------------------------------------------------------------- the gallery

// One line of an error: the exception of a traceback, else the first error that was logged
function summary(text) {
  const lines = String(text || '').trim().split('\n').map((l) => l.trim()).filter(Boolean);
  const last = lines[lines.length - 1] || 'It raised an error.';
  if (/^[\w.]*(Error|Exception)\b/.test(last)) return last;
  return (lines.find((l) => l.startsWith('ERROR:')) || last).replace(/: Runtime\.\w+ timed out.*$/, '.');
}

const state = { c: 'all', q: '', off: true };
let apply = () => {};
let built = false;
let hero = null;       // { example, start(), wanted }

function buildGallery() {
  built = true;
  const cards = examples.map((example) => {
    const result = results && results[example.id];
    // skip: why it cannot run in any browser; note: why it does not work yet
    let status = 'unknown', reason = '';
    if (example.skip) {
      status = 'skip';
      reason = example.skip;
    } else if (example.note || (result && !result.ok)) {
      status = 'fail';  // also when the (maybe stale) results say that it ran
      reason = example.note || summary(result.error);
    } else if (result) {
      status = 'ok';
    }
    return {
      ...example, example, state: status, reason,
      shot: result && result.ok && result.shot ? result.shot : '',
      url: urlOf(example),
      text: `${example.title} ${example.name} ${example.id} ${example.description}`.toLowerCase(),
    };
  });
  const byState = (status) => cards.filter((e) => e.state === status).length;
  const total = cards.length;
  const n = { ok: byState('ok'), fail: byState('fail'), skip: byState('skip'), unknown: byState('unknown') };
  const isOff = (e) => e.state === 'fail' || e.state === 'skip';

  // ----------------------------------------------------------------- hero

  if (results) {
    $('tally-num').append(String(n.ok), h('small', null, `of ${total}`));
    $('tally-what').textContent = 'examples run in the browser';
    const parts = [['ok', n.ok, 'run'], ['fail', n.fail, 'do not work yet'], ['skip', n.skip, 'cannot run in a browser'], ['unknown', n.unknown, 'not checked']]
      .filter(([, count]) => count);
    for (const [cls, count, label] of parts) {
      $('meter').append(h('i', { class: cls, style: `flex:${count}` }));
      $('legend').append(h('span', { class: cls }, `${count} ${label}`));
    }
    $('meter').setAttribute('aria-label', parts.map(([, count, label]) => `${count} ${label}`).join(', '));
  } else {
    $('tally-num').textContent = String(total);
    $('tally-what').textContent = 'examples';
    $('meter').hidden = true;
  }
  $('tally').hidden = false;

  const v = manifest.versions;
  const short = (sha) => String(sha || '').slice(0, 7);
  const versions = [
    ['wgpudawn', v.wgpudawn, v.wgpudawn_commit && `https://github.com/hmaarrfk/wgpudawn/tree/${v.wgpudawn_commit}`],
    ['Dawn', v.dawn],
    // A fork, when the site needs fixes that are not in pygfx yet
    ['pygfx', [v.pygfx, v.pygfx_commit && '@ ' + short(v.pygfx_commit), v.pygfx_upstream && '(with fixes)'].filter(Boolean).join(' '),
      v.pygfx_commit && `${v.pygfx_repository || 'https://github.com/pygfx/pygfx'}/tree/${v.pygfx_commit}`],
    ['wgpu-py API', v.wgpu_py],
    ['Pyodide', manifest.pyodide.version],
  ];
  for (const [name, value, href] of versions) {
    if (!value) continue;
    const inner = [h('b', null, name), value];
    $('versions').append(h('li', null, href ? h('a', { href, target: '_blank', rel: 'noopener' }, ...inner) : inner[0], href ? null : value));
  }
  $('fine').textContent = `Built from wgpudawn ${v.wgpudawn} (Dawn ${v.dawn}, the API of wgpu-py ${v.wgpu_py}) and pygfx ${v.pygfx}. `
    + `Python runs in Pyodide ${manifest.pyodide.version}, in this page.`;

  if (!webgpu) {
    $('browser').textContent = 'This browser does not have WebGPU, so the examples cannot run here: you are looking at screenshots. Recent versions of Chrome and Edge have it.';
  } else if (!jspi) {
    $('browser').textContent = 'This browser has WebGPU, but not JSPI (WebAssembly stack switching), so Python cannot wait for the browser in the middle of a call. Examples that only draw run; those that read back from the GPU, such as picking, do not. Recent versions of Chrome, Edge and Safari have both.';
  }

  // One example runs live in the hero: animated, good looking, and known to work.
  // (pbr2 fetches a sample image for its environment map; the others need nothing extra.)
  const WISHES = ['feature_demo/pbr2', 'feature_demo/skinned_mesh', 'feature_demo/look_at_instanced',
    'feature_demo/morph_targets', 'introductory/cube'];
  const light = (e) => e.animated && !e.needs_data && !e.pypi.length && !e.imageio.length;
  const chosen = WISHES.map((id) => cards.find((e) => e.id === id && e.state === 'ok')).find(Boolean)
    || cards.find((e) => e.state === 'ok' && light(e))
    || (!results && WISHES.map((id) => cards.find((e) => e.id === id && !e.skip)).find(Boolean))
    || cards.find((e) => e.shot);
  if (chosen) {
    const live = $('live');
    const sayLive = (pill, cls, status) => {
      $('live-pill').textContent = pill;
      $('live-pill').className = 'pill ' + cls;
      $('live-status').textContent = status;
    };
    live.hidden = false;
    $('live-title').textContent = chosen.title;
    $('live-cover').href = $('live-go').href = chosen.url;
    $('live-cover').setAttribute('aria-label', `Open the example: ${chosen.title}`);
    if (chosen.shot) {
      $('live-poster').src = chosen.shot;
      $('live-poster').hidden = false;
      $('live-poster').onerror = () => { $('live-poster').hidden = true; };
    }
    const still = () => sayLive(chosen.shot ? 'Screenshot' : 'Example', '', webgpu ? '' : 'No WebGPU in this browser');
    still();

    hero = {
      example: chosen.example,
      wanted: false,  // the visitor (or the page, where that is welcome) started it
      // Run it in the hero. Again when the gallery is shown again: the
      // interpreter is there, so it is back in a moment.
      async start() {
        hero.wanted = true;
        if (shown !== null) return;
        if (attempted && runner.mustReload(chosen.example)) { hero.rest(); return; }
        attempted = true;
        $('play').hidden = true;
        live.classList.remove('running');
        sayLive('Starting', 'busy', '');
        try {
          await runner.run(chosen.example, {
            log: (text, kind) => {
              if (kind === 'status') { if (text && shown === null) $('live-status').textContent = text; return; }
              console.debug(text);
              // Its error must not become the error of the example that is opened next
              if (kind === 'err' && /Traceback|Error|ERROR:/.test(text)) runner.taint('the example of the gallery reported an error');
            },
            mount: () => mountCanvas($('live-frame'), $('live-cover'), { 'aria-hidden': 'true' }),
            frame: () => { if (shown === null) live.classList.add('running'); },
          });
          if (shown !== null) return;
          live.classList.add('running');
          sayLive('Live', 'on', '');
        } catch (err) {
          if (err instanceof runner.Superseded) return;
          console.warn(err);
          runner.taint('the example of the gallery failed');
          sayLive(chosen.shot ? 'Screenshot' : 'Example', '', 'It could not start here');
        }
      },
      // The gallery is left: its picture is the screenshot again
      rest() {
        live.classList.remove('running');
        still();
      },
    };
    if (webgpu) {
      // Start by itself where that is cheap and welcome; otherwise offer a button.
      const calm = matchMedia('(prefers-reduced-motion: reduce)').matches;
      const frugal = navigator.connection && navigator.connection.saveData;
      const roomy = matchMedia('(min-width: 981px)').matches;
      $('play').onclick = hero.start;
      if (jspi && !calm && !frugal && roomy) {
        const seen = new IntersectionObserver((entries) => {
          if (!entries.some((entry) => entry.isIntersecting)) return;
          seen.disconnect();
          const go = () => idle(() => { if (!hero.wanted) hero.start(); });
          if (document.readyState === 'complete') go(); else addEventListener('load', go, { once: true });
        }, { threshold: 0.4 });
        seen.observe(live);
      } else {
        $('play').hidden = false;
      }
    }
  }

  // Python starts while the visitor looks at the gallery, so that the first
  // example opens as the next ones do. Where the live example started by
  // itself this is done already; this is for where it did not (a phone, a
  // visitor who scrolled past it). Not when the browser asks to save data:
  // it is tens of megabytes.
  if (webgpu && !(navigator.connection && navigator.connection.saveData)) {
    const early = () => setTimeout(() => idle(() => runner.boot().catch(() => {})), 1500);
    if (document.readyState === 'complete') early(); else addEventListener('load', early, { once: true });
  }

  // -------------------------------------------------------------- gallery

  // A screenshot of a canvas on which nothing was drawn (yet) is not a picture
  const probe = document.createElement('canvas');
  probe.width = 32; probe.height = 20;
  function isEmpty(img) {
    if (img.naturalWidth < 16) return true;
    try {
      const ctx = probe.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(img, 0, 0, 32, 20);
      const data = ctx.getImageData(0, 0, 32, 20).data;
      for (let i = 0; i < data.length; i += 4) if (data[i] > 14 || data[i + 1] > 14 || data[i + 2] > 14) return false;
      return true;
    } catch { return false; }
  }

  function card(e) {
    const off = isOff(e);
    const thumb = h('span', { class: 'thumb' + (e.shot ? '' : ' empty') });
    const blank = () => {
      thumb.classList.add('empty');
      thumb.querySelector('img')?.remove();
      thumb.prepend(icon('image'));
    };
    if (e.shot) {
      const img = h('img', { src: e.shot, alt: '', loading: 'lazy', decoding: 'async', width: 960, height: 600 });
      // A very wide or tall example is shown whole rather than cropped
      const shape = e.size ? e.size[0] / e.size[1] : 1.6;
      if (shape > 2.1 || shape < 1.05) { img.style.objectFit = 'contain'; img.style.background = '#000'; }
      img.addEventListener('error', blank);
      img.addEventListener('load', () => { if (isEmpty(img)) blank(); });
      thumb.append(img);
    } else {
      thumb.append(icon(e.state === 'skip' ? 'desktop' : e.state === 'fail' ? 'alert' : 'image'));
    }
    if (e.state === 'fail') thumb.append(h('span', { class: 'tag' }, 'Not yet'));
    else if (e.state === 'skip') thumb.append(h('span', { class: 'tag' }, 'Desktop only'));
    else if (e.animated) thumb.append(h('span', { class: 'tag anim' }, icon('play'), 'Animated'));
    const hover = off ? e.reason : e.description;
    if (hover) thumb.append(h('span', { class: 'desc' }, h('span', null, hover)));
    const el = h('a', { class: `card ${e.state}` + (off ? ' off' : ''), href: e.url },
      thumb,
      h('span', { class: 'cap' },
        h('span', { class: 'name' }, e.title),
        h('span', { class: 'sub' }, off ? e.reason : `${e.name}.py`)));
    if (off) el.setAttribute('aria-label', `${e.title}. ${e.state === 'skip' ? 'Cannot run in a browser' : 'Does not work yet'}. ${e.reason}`);
    // About to be opened: fetch what it needs
    const intent = () => warmUp(e.example);
    el.addEventListener('pointerenter', intent);
    el.addEventListener('focus', intent);
    el.addEventListener('touchstart', intent, { passive: true });
    // Pressed: Python can start while the finger is still down
    el.addEventListener('pointerdown', () => { if (webgpu && !e.skip) runner.boot(e.example).catch(() => {}); });
    e.el = el;
    return el;
  }

  // Per category: what works first, what does not at the end.
  const rank = { ok: 0, unknown: 1, fail: 2, skip: 3 };
  const groups = manifest.categories.map((category) => {
    const members = cards.filter((e) => e.category === category.id);
    if (!members.length) return null;
    const ordered = [...members].sort((a, b) => rank[a.state] - rank[b.state]);
    const count = h('span');
    const el = h('section', { class: 'group', id: 'c-' + category.id },
      h('header', null, h('h2', null, category.title), count),
      h('div', { class: 'grid' }, ...ordered.map(card)));
    $('groups').append(el);
    return { ...category, members, el, count };
  }).filter(Boolean);

  const chips = [{ id: 'all', title: 'All', members: cards }, ...groups].map((group) => {
    const count = h('small');
    const el = h('button', { class: 'chip', type: 'button', 'aria-pressed': 'false' }, group.title, count);
    el.addEventListener('click', () => { state.c = group.id; apply(); });
    $('chips').append(el);
    return { ...group, chip: el, chipCount: count };
  });

  const offTotal = n.fail + n.skip;
  if (offTotal) {
    $('off-switch').hidden = false;
    $('off-count').textContent = String(offTotal);
  }

  // The filters are in the address of the gallery
  readFilters = () => {
    const params = new URLSearchParams(location.search);
    state.c = chips.some((c) => c.id === params.get('c')) ? params.get('c') : 'all';
    state.q = params.get('q') || '';
    state.off = params.get('off') !== '0';
    $('q').value = state.q;
    $('off').checked = state.off;
  };

  apply = () => {
    const words = state.q.toLowerCase().split(/\s+/).filter(Boolean);
    const passes = (e) => (state.off || !isOff(e)) && words.every((w) => e.text.includes(w));
    let visible = 0;
    for (const e of cards) e.match = passes(e);
    for (const group of groups) {
      const inCategory = state.c === 'all' || state.c === group.id;
      let count = 0;
      for (const e of group.members) {
        const on = inCategory && e.match;
        e.el.hidden = !on;
        if (on) count += 1;
      }
      group.el.hidden = !count;
      group.count.textContent = String(count);
      visible += count;
    }
    for (const chip of chips) {
      chip.chip.setAttribute('aria-pressed', String(chip.id === state.c));
      chip.chipCount.textContent = String(chip.members.filter((e) => e.match).length);
    }
    $('count').textContent = `${visible} example${visible === 1 ? '' : 's'} shown`;
    $('none').hidden = visible > 0;
    $('none-what').textContent = state.q ? `Nothing matches “${state.q}”` : 'Nothing to show here';

    const params = new URLSearchParams();
    if (state.c !== 'all') params.set('c', state.c);
    if (state.q) params.set('q', state.q);
    if (!state.off) params.set('off', '0');
    const search = params.toString();
    galleryUrl = './' + (search ? '?' + search : '');
    if (shown === null) history.replaceState(history.state, '', galleryUrl + location.hash);
  };

  $('q').addEventListener('input', () => { state.q = $('q').value.trim(); apply(); });
  $('off').addEventListener('change', () => { state.off = $('off').checked; apply(); });
  $('reset').addEventListener('click', () => {
    state.c = 'all'; state.q = ''; state.off = true;
    $('q').value = ''; $('off').checked = true;
    apply();
  });
}
let readFilters = () => {};

// Show the gallery: as it was left, when it was shown before
function openGallery(again) {
  const ready = () => {
    if (shown !== null) return;
    if (!built) buildGallery();
    readFilters();
    apply();
    if (again && galleryScroll >= 0) scrollTo({ top: galleryScroll, behavior: 'instant' });
    else if (again || location.hash === '#gallery' || query.has('c') || query.has('q')) $('gallery').scrollIntoView({ behavior: 'instant' });
    if (hero) {
      // The example that was open stops; the one of the gallery is live again
      if (hero.wanted) hero.start();
      else { hero.rest(); if (again) runner.stop(); }
    } else if (again) {
      runner.stop();
    }
  };
  if (results !== null || built) ready();
  else resultsLoaded.then((loaded) => { results = loaded; ready(); });
}

show(route(), {});
// The gallery, ready for when the viewer is left
if (shown) resultsLoaded.then((loaded) => { results = loaded; idle(() => { if (!built) buildGallery(); }); });
