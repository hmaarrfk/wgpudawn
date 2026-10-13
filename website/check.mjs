// Run every example of a built site in headless Chrome, and record the truth:
// results.json (which examples work, and the error of those that do not) and
// shots/<example>.jpg (what they draw). The gallery shows both.
//
//   node website/check.mjs <site-dir> [--only <substring>] [--failed] [--jobs N] [--timeout S]
//       [--expect <file>] [--write-expected <file>] [--keep-shots]
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
const failedOnly = args.includes('--failed');
// Headless Chrome without a GPU (CI) runs WebGPU in software, but its canvas
// stays black, on screen and when read back. There, keep the pictures that the
// site already has (website/shots, taken on a machine with a GPU) and only
// record what works.
const keepShots = args.includes('--keep-shots');  // only what did not work last time

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
