// Run every example of a built site in headless Chrome, and record the truth:
// results.json (which examples work, and the error of those that do not) and
// shots/<example>.jpg (what they draw). The gallery shows both.
//
//   node website/check.mjs <site-dir> [--only <substring>] [--failed] [--jobs N] [--timeout S]
//       [--expect <file>] [--write-expected <file>]
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
const failedOnly = args.includes('--failed');  // only what did not work last time

const types = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.py': 'text/plain',
  '.zip': 'application/zip', '.whl': 'application/zip', '.jpg': 'image/jpeg',
};
const server = http.createServer((req, res) => {
  const p = path.join(dir, decodeURIComponent(new URL(req.url, 'http://x').pathname));
  fs.readFile(p, (err, data) => {
    if (err) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': types[path.extname(p)] || 'application/octet-stream' });
    res.end(data);
  });
}).listen(0);
const origin = `http://localhost:${server.address().port}`;

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
  if (outcome.ok) {
    const shot = path.join(dir, 'shots', example.id + '.jpg');
    fs.mkdirSync(path.dirname(shot), { recursive: true });
    try {
      const canvas = await tab.$('#canvas');
      await canvas.screenshot({ path: shot, type: 'jpeg', quality: 82 });
      result.shot = `shots/${example.id}.jpg`;
    } catch (err) {
      // It ran, but the page is too busy to answer (e.g. a heavy animation)
      result.ok = false;
      result.error = 'The example ran, but the page did not respond afterwards: ' + err.message;
    }
  } else {
    // The last lines say what went wrong; the gallery shows them
    const lines = outcome.error.trim().split('\n');
    result.error = lines.slice(-12).join('\n').slice(-1500);
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
server.close();

const counts = { ok: 0, failed: 0, skipped: manifest.examples.filter((e) => e.skip).length };
for (const example of manifest.examples) {
  if (results[example.id]) counts[results[example.id].ok ? 'ok' : 'failed'] += 1;
}
fs.writeFileSync(resultsFile, JSON.stringify({ counts, examples: results }, null, 1));
console.log(`${counts.ok} ok, ${counts.failed} failed, ${counts.skipped} cannot run in a browser`);

const working = Object.keys(results).filter((id) => results[id].ok).sort();
const writeExpected = option('--write-expected', '');
if (writeExpected) fs.writeFileSync(writeExpected, JSON.stringify(working, null, 1) + '\n');

const regressions = expected.filter((id) => results[id] && !results[id].ok);
const fixed = working.filter((id) => expectFile && !expected.includes(id));
if (fixed.length) console.log(`Work, but are not in ${expectFile}:\n  ${fixed.join('\n  ')}`);
if (regressions.length) {
  console.log(`Expected to work (${expectFile}), but failed:\n  ${regressions.join('\n  ')}`);
}
process.exit(regressions.length ? 1 : 0);
