// Runs the pygfx examples in Pyodide, on wgpudawn (Dawn's Emdawnwebgpu, i.e.
// the WebGPU of this browser). One interpreter serves the whole visit: it is
// started once (Pyodide, the packages, pygfx), and each example then runs in a
// fresh __main__ after what the previous one left running was ended
// (webhost.py). What a page load costs is paid once, not per example.
//
// The rule is correctness over speed. This module says when an example must
// not use the interpreter that is there (mustReload); the page then loads
// itself again, which is the one sure way to get a new interpreter.

let manifest = null;
export function init(theManifest) { manifest = theManifest; }

const mark = (name) => { try { performance.mark('phase:' + name); } catch { /* not important */ } };

// ------------------------------------------------------------------ console

// What the browser and Pyodide write to the console, in the page too: on a
// phone there is no console to look at. Pyodide reports a crash of the
// interpreter (a "fatal error") only there, and then never returns from the
// call that was running; `fatal` lets run() end instead of waiting.
let sink = null;  // log(text, kind) of the example that is running
let crashed = false;
let onFatal = null;
const fatal = new Promise((resolve, reject) => { onFatal = reject; });
fatal.catch(() => {});

function describe(value) {
  if (value instanceof Error) return value.stack || `${value.name}: ${value.message}`;
  if (typeof value === 'string') return value;
  try { return JSON.stringify(value); } catch { return String(value); }
}

function captureConsole() {
  const report = (label, values) => {
    const text = values.map(describe).join(' ');
    if (sink) sink(`[${label}] ${text}`, 'console');
    if (/fatal error/i.test(text)) {
      crashed = true;
      // The cause follows in the next console messages: let them arrive
      setTimeout(() => onFatal(new Error(
        'Pyodide crashed (a fatal error of the interpreter). The cause is in the output.')), 300);
    }
  };
  for (const name of ['error', 'warn']) {
    const original = console[name].bind(console);
    console[name] = (...values) => { original(...values); report('console.' + name, values); };
  }
  window.addEventListener('error', (event) => report('uncaught', [event.error || event.message]));
  window.addEventListener('unhandledrejection', (event) => report('unhandled rejection', [event.reason]));
}
captureConsole();

// One line that says what this browser is, for bug reports
export function describeBrowser() {
  const gpu = supportsWebGPU() ? 'yes' : 'no';
  const jspi = supportsJSPI() ? 'yes' : 'no';
  const blocking = canBlock() ? 'yes' : 'no';
  return `${navigator.userAgent} | WebGPU: ${gpu} | JSPI: ${jspi} | Python can block: ${blocking}`;
}

export function supportsWebGPU() {
  return typeof navigator !== 'undefined' && !!navigator.gpu;
}

export function supportsJSPI() {
  return typeof WebAssembly !== 'undefined' && typeof WebAssembly.Suspending === 'function';
}

// Whether Python can wait for the browser in the middle of a call (the
// blocking API of wgpu: reading back a buffer, picking). That takes JSPI.
// (In Safari on iOS it also takes the Pyodide that build.py patches: see
// IOS_TRAMPOLINE there.) ?jspi=0 runs the examples as a browser without it
// does: the device is awaited before the example starts, and what must block
// raises an error.
export function canBlock() {
  if (new URLSearchParams(location.search).get('jspi') === '0') return false;
  return supportsJSPI();
}
const blocking = canBlock();

// -------------------------------------------------------------- first frame

// When the example that runs presents its first picture: the page keeps the
// screenshot up until then. A canvas is presented by taking its texture
// (WebGPU) or by putting an image in it (the bitmap fallback of rendercanvas).
let onFrame = null;
function watchFrames() {
  const seen = () => {
    if (!onFrame) return;
    const callback = onFrame;
    onFrame = null;
    requestAnimationFrame(() => callback());  // when it is on the screen
  };
  const wrap = (proto, name) => {
    if (!proto || !proto[name]) return;
    const original = proto[name];
    proto[name] = function (...args) { seen(); return original.apply(this, args); };
  };
  try {
    if (typeof GPUCanvasContext !== 'undefined') wrap(GPUCanvasContext.prototype, 'getCurrentTexture');
    wrap(CanvasRenderingContext2D.prototype, 'putImageData');
  } catch { /* then the page waits for the end of the run instead */ }
}
watchFrames();

// -------------------------------------------------------------------- files

// The files of the site that an example needs are named after their content
// (build.py), so a copy never goes stale: they are kept in the Cache API,
// where GitHub Pages' ten minutes of HTTP caching do not apply. A new deploy
// has new names; names that the manifest does not have (anymore) are removed.
const CACHE = 'wgpudawn-files-1';
const cacheOpen = (async () => {
  try { return await caches.open(CACHE); } catch { return null; }  // not a secure context, or no storage
})();

// The copy of a file that this browser kept, if it has one
async function kept(file) {
  const cache = await cacheOpen;
  if (!cache) return null;
  try {
    const hit = await cache.match(file.url);
    if (!hit) return null;
    const data = new Uint8Array(await hit.arrayBuffer());
    if (data.length === file.size) return data;
    await cache.delete(file.url);
  } catch { /* fetch it */ }
  return null;
}

async function download(file, progress) {
  const cache = await cacheOpen;
  const had = await kept(file);
  if (had) return had;
  const response = await fetch(file.url);
  if (!response.ok) throw new Error(`Could not fetch ${file.url}: ${response.status}`);
  let data;
  if (progress && response.body) {
    const reader = response.body.getReader();
    data = new Uint8Array(file.size);
    let at = 0;
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      if (at + value.length > data.length) {  // not the size that the manifest states
        const larger = new Uint8Array(Math.max(data.length * 2, at + value.length));
        larger.set(data.subarray(0, at));
        data = larger;
      }
      data.set(value, at);
      at += value.length;
      progress(at, file.size);
    }
    data = data.subarray(0, at);
  } else {
    data = new Uint8Array(await response.arrayBuffer());
  }
  if (cache && data.length === file.size) {
    cache.put(file.url, new Response(data, { headers: { 'Content-Type': 'application/octet-stream' } })).catch(() => {});
  }
  return data;
}

// Downloads that are under way or waiting to be unpacked, by url
const fetched = new Map();
function fetchFile(file, progress) {
  if (!fetched.has(file.url)) {
    const promise = download(file, progress);
    promise.catch(() => fetched.delete(file.url));
    fetched.set(file.url, promise);
  }
  return fetched.get(file.url);
}

// Files that are in the file system of the interpreter (or on their way), by url
const installed = new Map();
function install(file, unpack, progress) {
  if (!installed.has(file.url)) {
    const promise = (async () => {
      const [py, data] = await Promise.all([core, fetchFile(file, progress)]);
      await unpack(py, data);
      fetched.delete(file.url);  // the bytes are in the file system now
    })();
    promise.catch(() => installed.delete(file.url));
    installed.set(file.url, promise);
  }
  return installed.get(file.url);
}

function removeStaleFiles() {
  cacheOpen.then(async (cache) => {
    if (!cache) return;
    const current = new Set([manifest.base, manifest.pyodide.stdlib, ...Object.values(manifest.data), ...Object.values(manifest.imageio),
      ...Object.values(manifest.extras).flatMap((extra) => extra.wheels)]
      .filter(Boolean).map((file) => new URL(file.url, location.href).href));
    for (const request of await cache.keys()) {
      if (!current.has(request.url)) await cache.delete(request);
    }
  }).catch(() => {});
}

// A wheel of the site, into the packages. Its compiled modules are loaded
// here, asynchronously: on import they would be compiled synchronously, which
// the browser refuses on the main thread for a module over 8 MB.
const libraries = new Set();
async function unpackWheel(py, data) {
  py.unpackArchive(data, 'wheel', { extractDir: '/site/packages' });
  const found = py.runPython('import glob; glob.glob("/site/packages/**/*.so", recursive=True)').toJs();
  for (const path of found) {
    if (libraries.has(path)) continue;
    libraries.add(path);
    await py._api.loadDynlib(path);
  }
}

// What an example needs besides the base: [file, how to unpack it]
function filesOf(example) {
  const files = [];
  for (const module of example.extras) {
    for (const wheel of manifest.extras[module].wheels) files.push([wheel, unpackWheel]);
  }
  for (const entry of example.data) {
    files.push([manifest.data[entry], (py, data) => py.unpackArchive(data, 'zip', { extractDir: '/site/store' })]);
  }
  for (const name of imagesOf(example)) {
    files.push([manifest.imageio[name], (py, data) => py.FS.writeFile('/site/images/' + name, data)]);
  }
  return files;
}

// The sample images of imageio that an example names ('*': the name is made
// at runtime, so it gets them all)
function imagesOf(example) {
  const all = Object.keys(manifest.imageio);
  return example.imageio.includes('*') ? all : example.imageio.filter((name) => all.includes(name));
}

const packageFiles = (names) => [...new Set(names.flatMap((name) => manifest.pyodide.files[name] || []))];

// Into the caches of the browser, for an example that is likely to be opened
// next. Nothing is kept in memory, and nothing is unpacked.
const prefetched = new Set();
export function prefetch(example) {
  if (!example || example.skip || prefetched.has(example.id)) return;
  prefetched.add(example.id);
  for (const [file] of filesOf(example)) {
    if (!installed.has(file.url) && !fetched.has(file.url)) download(file).catch(() => {});
  }
  if (!core) return;  // without an interpreter, the packages of the distribution are not known to be needed
  for (const name of packageFiles(example.packages)) {
    fetch(manifest.pyodide.url + name).then((response) => response.arrayBuffer()).catch(() => {});
  }
}

// -------------------------------------------------------------- interpreter

let core = null;    // Promise of Pyodide, with the base bundle unpacked
let booted = null;  // Promise of the interpreter, ready to run an example
let report = () => {};  // status(text) of whoever waits for the interpreter
let runs = 0;       // examples that this interpreter has started
let tainted = '';   // why the next example must not use this interpreter
let lazy = [];      // packages that the running example loaded on import

const megabytes = (bytes) => (bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0);

// Start the interpreter (once). `first` is the example that will run first,
// if that is known: its packages are fetched while Python starts.
export function boot(first) {
  if (booted) return booted;
  mark('pyodide');
  removeStaleFiles();
  const url = manifest.pyodide.url;
  // The core is the site's own copy (build.py patches it); the packages are the distribution's
  const index = manifest.pyodide.index ? new URL(manifest.pyodide.index, location.href).href : url;
  const packages = [...new Set([...manifest.pyodide.packages, ...(first ? first.packages : [])])];
  // Everything that is needed is asked for now, not when the step before it is done.
  // The standard library with bytecode is the site's (build.py); else that of the distribution
  const stdlib = manifest.pyodide.stdlib;
  for (const name of ['pyodide.asm.mjs', 'pyodide.asm.wasm', 'pyodide-lock.json']) {
    fetch(index + name).then((response) => response.arrayBuffer()).catch(() => {});
  }
  // From the Cache API when it is there; else Pyodide fetches it, and the
  // download below (the same one, for the browser) keeps it for the next visit
  const stdlibKept = stdlib ? kept(stdlib) : null;
  if (stdlib) download(stdlib).catch(() => {});
  const base = fetchFile(manifest.base, (at, size) => {
    if (!core.ready) report(`Loading Python, and pygfx (${megabytes(at)} of ${megabytes(size)} MB)`);
  });
  base.catch(() => {});
  if (first) for (const [file] of filesOf(first)) fetchFile(file).catch(() => {});

  core = (async () => {
    report('Loading Python');
    const [{ loadPyodide }, bytes] = await Promise.all([import(index + 'pyodide.mjs'), stdlibKept]);
    const blob = bytes ? URL.createObjectURL(new Blob([bytes])) : '';
    const py = await loadPyodide({
      indexURL: index,
      packageBaseUrl: url,
      stdLibURL: stdlib ? blob || new URL(stdlib.url, location.href).href : url + 'python_stdlib.zip',
      packages,  // fetched and unpacked while the interpreter starts
      stdout: (text) => (sink ? sink(text, 'out') : console.debug(text)),
      stderr: (text) => (sink ? sink(text, 'err') : console.debug(text)),
    });
    if (blob) URL.revokeObjectURL(blob);
    mark('bundle');
    report('Unpacking pygfx');
    py.unpackArchive(await base, 'zip', { extractDir: '/site' });
    fetched.delete(manifest.base.url);
    // (the compiled modules of the base are small enough to be loaded on import)
    for (const path of py.runPython('import glob; glob.glob("/site/packages/**/*.so", recursive=True)').toJs()) libraries.add(path);
    core.ready = true;
    return py;
  })();
  booted = (async () => {
    const py = await core;
    mark('import');
    report('Starting pygfx');
    const knows = (name) => !manifest.pyodide.not_on_import.includes(name)
      && !!(manifest.extras[name] || py._api._import_name_to_package_name.get(name));
    const load = async (name) => {
      lazy.push(name);
      if (sink) sink(`Loading ${name} (imported by the example)`, 'out');
      if (manifest.extras[name]) await installExtra(py, name);
      else await py.loadPackage(py._api._import_name_to_package_name.get(name), { messageCallback: () => {} });
    };
    py.globals.set('site_knows', knows);
    py.globals.set('site_load', load);
    py.globals.set('site_blocking', blocking);
    // pygfx is imported here, not by the first example: when the visitor
    // opens one, this is done
    await py.runPythonAsync(`
import sys
sys.path.insert(0, "/site/packages")
import webhost
webhost.setup(site_knows, site_load, site_blocking)
del site_knows, site_load, site_blocking
import pygfx, rendercanvas.auto
`);
    mark('ready');
    return py;
  })();
  booted.catch(() => { tainted = tainted || 'the interpreter did not start'; });
  return booted;
}

async function installExtra(py, module) {
  const extra = manifest.extras[module];
  await Promise.all([
    ...extra.wheels.map((wheel) => install(wheel, unpackWheel)),
    extra.packages.length ? py.loadPackage(extra.packages, { messageCallback: () => {} }) : null,
  ]);
}

// Wasm memory only grows. Past this, the next example gets a new interpreter.
const MEMORY_LIMIT = 1e9;
const RUNS_LIMIT = 150;
let memory = () => 0;

// Why this example cannot run in the interpreter that is there ('': it can).
// The page then loads itself again.
export function mustReload(example) {
  if (crashed) return 'the interpreter crashed';
  if (tainted) return tainted;
  if (!runs) return '';
  // It configures the GPU device, which exists by now
  if (example.isolate) return 'this example configures the interpreter';
  if (runs >= RUNS_LIMIT) return `${runs} examples ran in this interpreter`;
  if (memory() > MEMORY_LIMIT) return 'the memory of the interpreter is full';
  return '';
}

// The next example must not use this interpreter, e.g. because this one failed
export function taint(reason) { tainted = tainted || reason; }

export function stats() {
  return { runs, tainted, crashed, wasm: memory(), heap: performance.memory ? performance.memory.usedJSHeapSize : 0 };
}

export class Superseded extends Error {
  constructor() { super('Another example was opened'); this.name = 'Superseded'; }
}

// The interpreter cannot run another example (the message says why): the page loads itself again
export class Unusable extends Error {
  constructor(reason) { super(reason); this.name = 'Unusable'; }
}

// The browser can take the GPU device away. A lost device reports no errors
// and draws nothing, so what runs on it would look like it works.
const LOST = 'the GPU device was lost';
function deviceLost(py) {
  try {
    if (py.runPython('import webhost; webhost.device_lost()')) taint(LOST);
  } catch { /* then it is not known to be lost */ }
  return tainted === LOST;
}

// Whether the example that runs still has its GPU device (false: it does not draw anymore)
export async function hasDevice() {
  if (!booted || crashed) return true;
  return !deviceLost(await booted);
}

// End what the last example left running (canvases, callbacks, tasks)
async function teardown(py) {
  const previous = sink;
  sink = null;  // what it still says is not about the next example
  onFrame = null;
  try {
    await Promise.race([py.runPythonAsync('await webhost.teardown()'), fatal]);
  } catch (err) {
    taint('the previous example could not be ended');
    throw err;
  } finally {
    sink = previous;
  }
  // rendercanvas removes the canvas that it closes; one that was never used is still there
  for (const canvas of document.querySelectorAll('#canvas')) canvas.remove();
}

let wanted = 0;
let chain = Promise.resolve();
let executing = 0;  // the run whose Python code is executing

// True while an example that is not wanted anymore is still starting: Python
// cannot be interrupted, so the wanted one waits
export function isBlocked() { return executing !== 0 && executing !== wanted; }

// Run an example. Returns once it has run (it keeps drawing afterwards).
//   options.log(text, kind): kind is 'out', 'err', 'console' or 'status'
//   options.mount(): puts a new <canvas id="canvas"> in the page
//   options.frame(): called when the example has presented its first picture
// Rejects with Superseded when another example was asked for in the meantime.
export function run(example, options = {}) {
  const log = options.log || (() => {});
  const status = (text) => log(text, 'status');
  const mine = ++wanted;
  const check = () => { if (mine !== wanted) throw new Superseded(); };
  mark('run');
  // Its files: asked for now, also when Python is still starting or busy
  boot(example).catch(() => {});
  const needs = filesOf(example);
  for (const [file] of needs) if (!installed.has(file.url)) fetchFile(file).catch(() => {});

  const job = chain.then(async () => {
    check();
    try {
      report = status;
      if (!core.ready) status('Loading Python');
      const py = await Promise.race([booted, fatal]);
      memory = () => py._module.HEAPU8.length;
      check();
      if (runs) await teardown(py);
      if (deviceLost(py)) throw new Unusable(LOST);
      check();

      // What this example needs besides the base
      mark('needs');
      let done = 0;
      const total = needs.reduce((sum, [file]) => sum + file.size, 0);
      const pending = needs.filter(([file]) => !installed.has(file.url));
      if (pending.length) status(`Fetching the files of the example (${megabytes(total)} MB)`);
      const missing = example.packages.filter((name) => !py.loadedPackages[name]);
      if (missing.length && !pending.length) status('Loading packages');
      await Promise.all([
        ...needs.map(([file, unpack]) => install(file, unpack).then(() => {
          done += file.size;
          if (pending.length && done < total) status(`Fetching the files of the example (${megabytes(done)} of ${megabytes(total)} MB)`);
        })),
        missing.length ? py.loadPackage(missing, { messageCallback: () => {}, errorCallback: (m) => log(m, 'err') }) : null,
        ...example.extras.map((module) => installExtra(py, module)),
      ]);
      check();

      mark('example');
      status('Starting the example');
      for (const canvas of document.querySelectorAll('#canvas')) canvas.remove();
      if (options.mount) options.mount();
      sink = log;
      lazy = [];
      onFrame = () => { mark('frame'); if (mine === wanted && options.frame) options.frame(); };
      runs += 1;
      const number = runs;
      if (example.isolate) taint('the previous example configured the interpreter');
      py.globals.set('site_run', py.toPy([example.id, example.data, imagesOf(example)]));
      // runPythonAsync, so that the blocking API of wgpu works (via JSPI).
      // The device is awaited first: no example needs JSPI just to start
      executing = mine;
      await Promise.race([py.runPythonAsync(`import webhost\n${example.isolate ? '' : 'await webhost.warm()\n'}webhost.run(*site_run)`), fatal]);
      mark('ran');
      return { run: number, lazy: [...lazy], lost: deviceLost(py) };
    } finally {
      if (executing === mine) executing = 0;
    }
  });
  chain = job.catch(() => {});
  return job;
}

// End the example that runs, e.g. when the page shows something else
export function stop() {
  const mine = ++wanted;
  const job = chain.then(async () => {
    if (mine !== wanted || !runs || crashed || !booted) return;
    await teardown(await booted);
  });
  chain = job.catch(() => {});
  return chain;
}
