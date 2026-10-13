// Run one pygfx example in Pyodide, on wgpudawn (Dawn's Emdawnwebgpu, i.e. the
// WebGPU of this browser). Used by run.html and by the hero of index.html.

const BASE_PACKAGES = ['cffi', 'numpy', 'micropip', 'jinja2'];

const BOOTSTRAP = `
import os, sys, logging
import importlib.abc, importlib.util
os.makedirs("/tmp/pygfx", exist_ok=True)
os.environ["PYGFX_DATA_DIR"] = "/tmp/pygfx"  # pygfx does not know this platform
os.environ["IMAGEIO_USERDIR"] = "/imageio"  # where the site puts imageio's sample images


class LazyPackages(importlib.abc.MetaPathFinder):
    """Load a package when it is imported, if Pyodide or the site knows it.

    The packages that an example imports itself are loaded up front. This is
    for the rest: imports inside functions, and of dependencies.
    """

    def __init__(self):
        self._busy = set()

    def find_spec(self, fullname, path=None, target=None):
        if "." in fullname or fullname in self._busy:
            return None
        import micropip, pyodide_js
        from pyodide.ffi import run_sync

        self._busy.add(fullname)
        try:
            package = pyodide_js._api._import_name_to_package_name.get(fullname)
            if package:
                print(f"Loading {package} (imported by the example)")
                run_sync(pyodide_js.loadPackage(package))
            elif fullname in pypi_by_import:
                print(f"Installing {pypi_by_import[fullname]} (imported by the example)")
                run_sync(micropip.install(pypi_by_import[fullname]))
            else:
                return None
            return importlib.util.find_spec(fullname)
        except Exception as err:
            print(f"Could not load {fullname}: {err}", file=sys.stderr)
            return None
        finally:
            self._busy.discard(fullname)


sys.meta_path.append(LazyPackages())


class ReportErrors(logging.Handler):
    """Errors that are logged, as "ERROR:" lines on stderr.

    In a browser, validation errors of the GPU arrive after the call that
    caused them, so they are logged instead of raised. The page counts these
    lines to know that an example does not really work.
    """

    def emit(self, record):
        print(f"ERROR: {record.name}: {record.getMessage()}", file=sys.stderr)


logging.getLogger().addHandler(ReportErrors(level=logging.ERROR))

import wgpudawn
wgpudawn.install_as_wgpu()  # pygfx and rendercanvas import wgpu by name
`;

const RUN = `
import os, sys, runpy
path = "/examples/" + example_id + ".py"
os.chdir(os.path.dirname(path))
sys.path.insert(0, os.path.dirname(path))
sys.argv = [path]
runpy.run_path(path, run_name="__main__")
`;

async function fetchBytes(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Could not fetch ${url}: ${response.status}`);
  return new Uint8Array(await response.arrayBuffer());
}

export function supportsWebGPU() {
  return typeof navigator !== 'undefined' && !!navigator.gpu;
}

export function supportsJSPI() {
  return typeof WebAssembly !== 'undefined' && typeof WebAssembly.Suspending === 'function';
}

// Returns once the example has run (it keeps drawing afterwards).
//   manifest: examples.json; example: one of its examples
//   options.log(text, kind): kind is 'out', 'err' or 'status'
export async function runExample(manifest, example, options = {}) {
  const log = options.log || (() => {});
  const status = (text) => log(text, 'status');

  status('Loading Pyodide');
  const { loadPyodide } = await import(manifest.pyodide.url + 'pyodide.mjs');
  const py = await loadPyodide({
    indexURL: manifest.pyodide.url,
    stdout: (text) => log(text, 'out'),
    stderr: (text) => log(text, 'err'),
  });

  status('Loading packages');
  const packages = [...BASE_PACKAGES, ...example.packages];
  await py.loadPackage(packages, { messageCallback: () => {}, errorCallback: (m) => log(m, 'err') });

  status('Installing wgpudawn and pygfx');
  const sitePackages = py.runPython('import site; site.getsitepackages()[0]');
  const wheels = await Promise.all(
    manifest.wheels.map((name) => fetchBytes('wheels/' + encodeURIComponent(name))));
  for (const data of wheels) py.unpackArchive(data, 'wheel', { extractDir: sitePackages });
  py.globals.set('pypi_packages', py.toPy([...manifest.pyodide.pypi_always, ...example.pypi]));
  py.globals.set('pypi_by_import', py.toPy(manifest.pyodide.pypi_by_import));
  await py.runPythonAsync('import micropip\nawait micropip.install(pypi_packages)');

  status('Fetching the examples');
  py.unpackArchive(await fetchBytes('examples.zip'), 'zip', { extractDir: '/' });
  if (example.needs_data) {
    status('Fetching the data files of the examples');
    py.unpackArchive(await fetchBytes('examples-data.zip'), 'zip', { extractDir: '/' });
  }

  if (example.imageio.length) {
    py.unpackArchive(await fetchBytes('imageio.zip'), 'zip', { extractDir: '/' });
  }

  status('Starting');
  await py.runPythonAsync(BOOTSTRAP);
  py.globals.set('example_id', example.id);
  // runPythonAsync, so that the blocking API of wgpu works (via JSPI)
  await py.runPythonAsync(RUN);
  status('');
  return py;
}
