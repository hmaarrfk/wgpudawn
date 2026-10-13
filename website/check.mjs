// Run every example of a built site in headless Chrome, and record the truth:
// results.json (which examples work, and the error of those that do not) and
// shots/<example>.jpg (what they draw). The gallery shows both.
//
//   node website/check.mjs <site-dir> [--only <substring>] [--failed] [--jobs N] [--timeout S]
//       [--expect <file>] [--write-expected <file>] [--keep-shots]
//   node website/check.mjs <site-dir> --warm [--only <substring>] [--settle MS] [--warm-out <dir>] [--keep-shots]
//
// The first form is the truth about what works: every example in a page load
// (and so a Python interpreter) of its own. --warm checks the fast path that
// visitors take instead: all examples in ONE page, one after another through
// the page's own navigation (the "next" link), in one interpreter. It reports
// per example whether it ran, whether the page had to fall back to a new
// interpreter (a page load), and the time from the click to the first frame;
// and it fails when an example does not do what it did on its own (the
// results.json of the first form). It writes <dir>/warm.json and screenshots,
// outside the site.
//
// Env: CHROME_PATH (default: /usr/bin/google-chrome), CHROME_FLAGS (extra
// flags, e.g. "--use-angle=vulkan --ignore-gpu-blocklist" for a hardware GPU).
// Without a GPU, Chrome uses SwiftShader, which is what CI does.
//
// --expect <file>: a JSON list of the examples that are known to work. Exits
// with 1 when one of those fails, so that a regression fails the build.
// --write-expected <file>: write that list, from this run.
import puppeteer from 'puppeteer-core';
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
const dir = path.resolve(args[0]);
const option = (name, fallback) => {
  const i = args.indexOf(name);
  return i < 0 ? fallback : args[i + 1];
};
const only = option('--only', '');
const jobs = Number(option('--jobs', '4'));
const timeout = Number(option('--timeout', '180')) * 1000;
// A JPEG of one flat color is about 0.0073 bytes per pixel (4.2 kB at 960x600);
// a dark scene with a few thin lines is already over 0.0082
const BLANK_BYTES_PER_PIXEL = 0.0077;
const failedOnly = args.includes('--failed');  // only what did not work last time
// Headless Chrome without a GPU (CI) runs WebGPU in software, but its canvas
// stays black, on screen and when read back. There, keep the pictures that the
// site already has (website/shots, taken on a machine with a GPU) and only
// record what works.
const keepShots = args.includes('--keep-shots');

const types = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.py': 'text/plain',
  '.zip': 'application/zip', '.whl': 'application/zip', '.jpg': 'image/jpeg',
};
const server = http.createServer((req, res) => {
  const p = path.join(dir, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  if (path.relative(path.resolve(dir), path.resolve(p)).startsWith('..')) { res.writeHead(403); res.end(); return; }
  fs.readFile(p, (err, data) => {
    if (err) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(0, '127.0.0.1');
await new Promise((resolve) => server.once('listening', resolve));
const origin = `http://127.0.0.1:${server.address().port}`;

const manifest = JSON.parse(fs.readFileSync(path.join(dir, 'examples.json'), 'utf8'));
const resultsFile = path.join(dir, 'results.json');
const previous = fs.existsSync(resultsFile) ? JSON.parse(fs.readFileSync(resultsFile, 'utf8')).examples : {};
const results = { ...previous };

// One browser per job: Chrome only draws the tab that is in front, and an
// example that is not drawing cannot be screenshotted.
const launch = () => puppeteer.launch({
  executablePath: process.env.CHROME_PATH || '/usr/bin/google-chrome',
  headless: true,
  protocolTimeout: 120000,
  args: ['--enable-unsafe-webgpu', '--enable-features=Vulkan', '--no-sandbox',
         ...(process.env.CHROME_FLAGS || '').split(' ').filter(Boolean)],
});

async function checkExample(browser, example) {
  const tab = await browser.newPage();
  await tab.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 });
  const started = Date.now();
  const outcome = await new Promise((resolve) => {
    const timer = setTimeout(() => resolve({ ok: false, error: 'timeout' }), timeout);
    const done = (value) => { clearTimeout(timer); resolve(value); };
    tab.on('console', (m) => {
      const text = m.text();
      if (text.startsWith('EXAMPLE OK')) done({ ok: true });
      else if (text.startsWith('EXAMPLE FAIL: ')) done({ ok: false, error: text.slice(14) });
    });
    tab.on('pageerror', (e) => done({ ok: false, error: 'pageerror: ' + e.message }));
    tab.goto(`${origin}/run.html?check=1&ex=${encodeURIComponent(example.id)}`)
      .catch((e) => done({ ok: false, error: String(e) }));
  });
  const result = { ok: outcome.ok, seconds: Math.round((Date.now() - started) / 100) / 10 };
  const shot = path.join(dir, 'shots', example.id + '.jpg');
  if (outcome.ok && keepShots) {
    if (fs.existsSync(shot)) result.shot = `shots/${example.id}.jpg`;
  } else if (outcome.ok) {
    fs.mkdirSync(path.dirname(shot), { recursive: true });
    try {
      const canvas = await tab.$('#canvas');
      const box = await canvas.boundingBox();
      const BLANK_BYTES = BLANK_BYTES_PER_PIXEL * box.width * box.height;
      let image = await canvas.screenshot({ type: 'jpeg', quality: 82 });
      // A flat image compresses to almost nothing: nothing was drawn (yet).
      // Some examples need a moment; look once more before believing it.
      if (image.length < BLANK_BYTES) {
        await new Promise((resolve) => setTimeout(resolve, 4000));
        image = await canvas.screenshot({ type: 'jpeg', quality: 82 });
      }
      fs.writeFileSync(shot, image);
      result.shot = `shots/${example.id}.jpg`;
      if (image.length < BLANK_BYTES) result.blank = true;
    } catch (err) {
      // It ran, but the page is too busy to answer (e.g. a heavy animation)
      result.ok = false;
      result.error = 'The example ran, but the page did not respond afterwards: ' + err.message;
    }
  } else {
    // The last lines say what went wrong; the gallery shows them
    // The first error is the cause, the last lines are where it surfaced
    const lines = outcome.error.trim().split('\n');
    const first = lines.findIndex((line) => /Traceback|ERROR:/.test(line));
    const head = first < 0 ? [] : lines.slice(first, first + 12);
    const tail = lines.slice(-12).filter((line) => !head.includes(line));
    const gap = head.length && tail.length ? ['...'] : [];
    result.error = [...head, ...gap, ...tail].join('\n').slice(0, 3000);
  }
  await tab.close().catch(() => {});
  return result;
}

// ------------------------------------------------------------------ --warm

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const quantile = (values, q) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted.length ? sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] : NaN;
};

async function warmWalk() {
  const settle = Number(option('--settle', '1500'));
  const out = path.resolve(option('--warm-out', path.join(os.tmpdir(), 'wgpudawn-warm')));
  fs.mkdirSync(out, { recursive: true });
  // The examples in the order of the page, from the first to the last that is asked for
  const matches = manifest.examples.map((e, i) => (e.id.includes(only) ? i : -1)).filter((i) => i >= 0);
  const list = manifest.examples.slice(matches[0], matches[matches.length - 1] + 1);
  console.log(`Walking through ${list.length} examples in one page`);
  const browser = await launch();
  const tab = await browser.newPage();
  await tab.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 });
  let loads = 0;  // page loads: the first, and every fallback to a new interpreter
  tab.on('load', () => { loads += 1; });
  // What the page says about the example that it shows (null while it loads itself again)
  const read = () => tab.evaluate(() => (window.__nav ? JSON.parse(JSON.stringify(window.__nav)) : null)).catch(() => null);
  const done = (nav, id) => nav && nav.id === id && ['running', 'failed', 'skipped'].includes(nav.state);
  const rows = [];
  await tab.goto(`${origin}/run.html?ex=${encodeURIComponent(list[0].id)}`);
  for (const [i, example] of list.entries()) {
    if (i) await tab.evaluate(() => document.getElementById('next').click());
    const before = loads;
    const deadline = Date.now() + timeout;
    let nav = null;
    while (Date.now() < deadline) {
      nav = await read();
      if (done(nav, example.id)) {
        if (nav.state === 'skipped') break;
        // Errors of the GPU arrive later; an error makes the page start over when it can.
        // Longer for what is in doubt: no picture yet, an example that does not
        // work on its own, or one that the page already gave a second try.
        const doubt = nav.frame == null || nav.retried || (previous[example.id] && !previous[example.id].ok);
        await sleep(doubt ? Math.max(settle, 4000) : settle);
        const later = await read();
        if (done(later, example.id) && later.state === nav.state) { nav = later; break; }
      }
      await sleep(25);
    }
    const row = { id: example.id, state: done(nav, example.id) ? nav.state : 'timeout' };
    if (nav && nav.id === example.id) {
      Object.assign(row, {
        ms: nav.frame ?? nav.ran, frame: nav.frame, ran: nav.ran, run: nav.run, lazy: nav.lazy, error: nav.error,
        fallback: nav.fresh || '', retried: !!nav.retried, before: nav.before || '', memory: nav.memory,
      });
    }
    row.reloaded = loads > before && i > 0;
    if (row.state === 'running' && !keepShots) {
      try {
        const canvas = await tab.$('#view-run #canvas');
        const box = await canvas.boundingBox();
        const image = await canvas.screenshot({ type: 'jpeg', quality: 82 });
        const file = path.join(out, example.id + '.jpg');
        fs.mkdirSync(path.dirname(file), { recursive: true });
        fs.writeFileSync(file, image);
        row.blank = image.length < BLANK_BYTES_PER_PIXEL * box.width * box.height;
      } catch (err) {
        row.blank = true;
        row.error = 'no canvas to look at: ' + err.message;
      }
    }
    rows.push(row);
    if (row.state !== 'skipped') {
      const mb = row.memory ? ` wasm ${Math.round(row.memory.wasm / 1e6)} MB, js ${Math.round(row.memory.heap / 1e6)} MB` : '';
      console.log(`${row.state === 'running' ? 'ok  ' : 'FAIL'} ${example.id} ${row.ms ?? '-'} ms (run ${row.run || '-'} of its interpreter)` +
        (row.fallback ? ` [new interpreter: ${row.fallback}${row.before ? ': ' + row.before : ''}]` : '') + (row.blank ? ' [blank]' : '') +
        (row.lazy && row.lazy.length ? ` [on import: ${row.lazy.join(', ')}]` : '') + mb +
        (row.state === 'running' ? '' : '\n      ' + String(row.error || '').split('\n').pop()));
    }
    if (row.state === 'timeout') {  // the page is stuck: go on from the next example
      const next = list[i + 1];
      if (next) await tab.goto(`${origin}/run.html?ex=${encodeURIComponent(example.id)}`).catch(() => {});
    }
  }
  await browser.close();
  server.close();

  const ran = rows.filter((r) => r.state !== 'skipped');
  const ok = ran.filter((r) => r.state === 'running');
  // The fast path: the interpreter that was there (not the first of a page load)
  const fast = ok.filter((r) => r.run > 1 && !r.fallback);
  const fallbacks = ran.filter((r) => r.fallback);
  const line = (name, set) => `${name}: ${set.length} examples, median ${quantile(set.map((r) => r.ms), 0.5)} ms, ` +
    `p90 ${quantile(set.map((r) => r.ms), 0.9)} ms, max ${quantile(set.map((r) => r.ms), 1)} ms`;
  console.log(`${ok.length} ok, ${ran.length - ok.length} failed, ${rows.length - ran.length} cannot run in a browser`);
  console.log('Time from the click to the first frame');
  console.log('  ' + line('in the interpreter that was there', fast));
  console.log('  ' + line('with a new interpreter (a page load)', ok.filter((r) => r.run === 1)));
  // An example that only works in an interpreter of its own: the fast path lost something
  const rescued = ok.filter((r) => r.retried);
  console.log(`New interpreters: ${fallbacks.length}, of which ${rescued.length} for an example that failed in the one that was there and then worked` +
    (rescued.length ? `:\n  ${rescued.map((r) => `${r.id}: ${r.before}`).join('\n  ')}` : ''));
  const reasons = {};
  for (const r of fallbacks) (reasons[r.fallback] ||= []).push(r.id);
  for (const [reason, ids] of Object.entries(reasons)) console.log(`  ${reason}: ${ids.length} (${ids.slice(0, 6).join(', ')}${ids.length > 6 ? ', ...' : ''})`);
  const lazy = ran.filter((r) => r.lazy && r.lazy.length);
  console.log(`Loaded a package on import (a switch of the stack, JSPI): ${lazy.length}` +
    (lazy.length ? ` (${[...new Set(lazy.flatMap((r) => r.lazy))].join(', ')})` : ''));
  const memory = ran.filter((r) => r.memory).map((r) => r.memory);
  if (memory.length) {
    console.log(`Memory: wasm ${Math.round(memory[0].wasm / 1e6)} -> ${Math.round(Math.max(...memory.map((m) => m.wasm)) / 1e6)} MB (largest), ` +
      `JS heap ${Math.round(memory[0].heap / 1e6)} -> ${Math.round(Math.max(...memory.map((m) => m.heap)) / 1e6)} MB (largest)`);
  }
  fs.writeFileSync(path.join(out, 'warm.json'), JSON.stringify({ examples: rows }, null, 1));
  console.log(`Details and screenshots: ${out}`);

  // The truth is the check of each example on its own: this must agree with it
  const wrong = [];
  for (const row of ran) {
    const cold = previous[row.id];
    if (!cold) continue;
    if (cold.ok && row.state !== 'running') wrong.push(`${row.id}: works on its own, but not here (${row.state})`);
    if (!cold.ok && row.state === 'running') wrong.push(`${row.id}: does not work on its own, but is shown as running here`);
    if (cold.ok && !cold.blank && row.blank) wrong.push(`${row.id}: draws on its own, but nothing here`);
  }
  if (!Object.keys(previous).length) console.log('No results.json to compare with: run the check without --warm first.');
  if (wrong.length) console.log(`Differences with results.json:\n  ${wrong.join('\n  ')}`);
  return wrong.length ? 1 : 0;
}
if (args.includes('--warm')) process.exit(await warmWalk());

// ---------------------------------------------- each example on its own

const expectFile = option('--expect', '');
const expected = expectFile && fs.existsSync(expectFile)
  ? JSON.parse(fs.readFileSync(expectFile, 'utf8')) : [];
for (const example of manifest.examples) {
  if (example.skip) delete results[example.id];  // not something to run (anymore)
}

const queue = manifest.examples.filter((e) => !e.skip && e.id.includes(only)
  && !(failedOnly && previous[e.id] && previous[e.id].ok));
console.log(`Checking ${queue.length} examples, ${jobs} at a time`);
async function worker() {
  const browser = await launch();
  for (let example = queue.shift(); example; example = queue.shift()) {
    const result = await checkExample(browser, example);
    results[example.id] = result;
    console.log(`${result.ok ? 'ok  ' : 'FAIL'} ${example.id} (${result.seconds}s)` +
      (result.ok ? '' : '\n      ' + result.error.split('\n').pop()));
  }
  await browser.close();
}
await Promise.all(Array.from({ length: jobs }, worker));

// A timeout or a lost device can be the machine (software rendering, several
// browsers at once: the GPU process of Chrome gives up) rather than the
// example: try those once more, one at a time
const transient = (result) => result && !result.ok &&
  (result.error === 'timeout' || /device was lost|did not respond/i.test(result.error));
const again = manifest.examples.filter((e) => transient(results[e.id]));
if (again.length) {
  console.log(`Trying ${again.length} examples with a transient failure once more, one at a time`);
  queue.push(...again);
  await worker();
}

const counts = { ok: 0, failed: 0, blank: 0, skipped: manifest.examples.filter((e) => e.skip).length };
for (const example of manifest.examples) {
  const result = results[example.id];
  if (!result) continue;
  counts[result.ok ? 'ok' : 'failed'] += 1;
  if (result.ok && result.blank) counts.blank += 1;
}
fs.writeFileSync(resultsFile, JSON.stringify({ counts, examples: results }, null, 1));
console.log(`${counts.ok} ok (${counts.blank} of them drew nothing visible), ${counts.failed} failed, ` +
  `${counts.skipped} cannot run in a browser`);

const working = Object.keys(results).filter((id) => results[id].ok).sort();
const writeExpected = option('--write-expected', '');
if (writeExpected) fs.writeFileSync(writeExpected, JSON.stringify(working, null, 1) + '\n');

// When most pictures are flat, it is not the examples: this browser does not put
// the WebGPU canvas on screen (headless Chrome without a GPU: use --keep-shots
// there), and the gallery would be all black
if (!keepShots && counts.blank > 0.2 * counts.ok) {
  console.log(`${counts.blank} of ${counts.ok} screenshots are blank: the browser is not showing the canvas.`);
  process.exit(1);
}

const regressions = expected.filter((id) => results[id] && !results[id].ok);
const fixed = working.filter((id) => expectFile && !expected.includes(id));
if (fixed.length) console.log(`Work, but are not in ${expectFile}:\n  ${fixed.join('\n  ')}`);
if (regressions.length) {
  console.log(`Expected to work (${expectFile}), but failed:\n  ${regressions.join('\n  ')}`);
}
process.exit(regressions.length ? 1 : 0);
