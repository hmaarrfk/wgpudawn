"""Build the website: the examples of pygfx, running in the browser on wgpudawn.

    python website/build.py --pygfx ../pygfx-src --wheels <dir> --out site

``--wheels`` is a directory with the wheels that the pages install: wgpudawn
for Pyodide, pygfx (pure Python) and freetype-py (``build_freetype.sh``).
The other packages are pinned in ``pyodide.json``: those of PyPI are
downloaded here (into ``--cache``) and served by the site, so that a page
asks PyPI nothing; those of the Pyodide distribution come from its CDN.

The site is static. It is one page with two views, the gallery and the
viewer that runs one example (``index.html``; ``run.html`` is a copy, so that
``run.html?ex=<id>`` is an address of its own), ``examples.json`` (the list of
examples with what the page needs to know about each), and the files that an
example needs: ``base-<hash>.zip`` (the packages that every example imports,
and the examples), ``wheels/`` (packages that only some examples import),
``examples-data.zip`` and ``imageio/``. Whether an example actually works in
the browser is not decided here: ``check.mjs`` runs them all in headless
Chrome, and writes ``results.json`` and the screenshots that the gallery
shows.
"""

import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

IMAGEIO_URL = "https://github.com/imageio/imageio-binaries/raw/master/images/"

# The pages, as they are
STATIC = (
    "index.html",
    "site.css",
    "app.js",
    "runner.js",
    "logo.svg",
    "diagnose.html",
)

CATEGORIES = ["introductory", "feature_demo", "validation", "other"]
CATEGORY_TITLES = {
    "introductory": "Introductory",
    "feature_demo": "Feature demos",
    "validation": "Validation",
    "other": "Other",
}

# Imported module -> the package of the Pyodide distribution that provides it
PYODIDE_PACKAGES = {
    "imageio": "imageio",
    "PIL": "pillow",
    "skimage": "scikit-image",
    "scipy": "scipy",
    "sklearn": "scikit-learn",
    "httpx": "httpx",
    "requests": "requests",
    "tqdm": "tqdm",
}
# What an example imports without saying so: pygfx imports these when the
# example calls the function. (pattern in the source, imported modules.)
# Loaded up front, a package costs a download; loaded on import, it also costs
# a switch of the WebAssembly stack (JSPI) in the middle of the example.
IMPLIED_IMPORTS = [
    (r"\bload_gltf|\bload_gltf_mesh|\bprint_scene_graph", ["gltflib", "imageio"]),
    (r"\bload_mesh(es)?\b|\bload_scene\b", ["trimesh"]),
    # ... a glTF file from the web
    (r"(?s)\bload_gltf.*https?://|https?://.*\bload_gltf", ["httpx"]),
]
# Calls that configure the GPU device of the whole interpreter. An example
# that makes one gets an interpreter of its own (see runner.js).
ISOLATE = (
    r"\b(select_power_preference|select_adapter|enable_wgpu_features"
    r"|preconfigure_default_device)\(|os\.environ\[[^\]]+\]\s*=|\batexit\b"
)

# Imported module -> why an example that needs it cannot run in a browser.
# Full sentences: the website shows them as they are.
UNAVAILABLE = {
    "PySide6": "Opens a Qt window. Qt has no build for Pyodide, and a browser tab has no native windows.",
    "wx": "Opens a wxPython window. wxPython has no build for Pyodide, and a browser tab has no native windows.",
    "glfw": "Opens a glfw window. A browser tab has no native windows.",
    "open3d": "Needs open3d, a large C++ library that has no build for WebAssembly.",
    "torch": "Needs PyTorch, which has no build for Pyodide.",
    "torch_geometric": "Needs PyTorch (torch_geometric), which has no build for Pyodide.",
    "lightning": "Needs PyTorch (lightning), which has no build for Pyodide.",
    "sam2": "Needs PyTorch and the pretrained SAM 2 model, which has no build for Pyodide.",
    "zmq": "Talks to another process over ZeroMQ sockets. A browser tab cannot open sockets.",
    "sounddevice": "Plays audio through PortAudio, which needs an audio device of the operating system.",
    "soundfile": "Reads audio with libsndfile, which has no build for Pyodide.",
    "psutil": "Reads the CPU usage of the machine with psutil. A browser tab has no access to that.",
    "av": "Decodes video with PyAV (FFmpeg), which has no build for Pyodide.",
    "pytest": "This is a test, not an example.",
    "unittest": "This is a test, not an example.",
}


# Example -> why it cannot run in a browser, where the reason is more specific
# than the modules that it imports
SKIP_REASONS = {
    "other/integration_pytorch": (
        "Trains in one process and renders in a second one (torch.multiprocessing); "
        "a browser tab has no processes or threads for Python. It also needs libigl, "
        "which has no build for WebAssembly. PyTorch itself only exists for Pyodide "
        "as an unofficial, CPU-only build."
    ),
    "other/sam2_point_segmentation": (
        "A Qt application that runs the SAM 2 model in a background thread and "
        "downloads its PyTorch checkpoint at startup. Qt, threads and that download "
        "are not available in a browser tab."
    ),
}


def parse_example(path):
    with open(path, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)

    doc = ast.get_docstring(tree) or ""
    lines = [line.rstrip() for line in doc.strip().splitlines()]
    title = lines[0] if lines else os.path.basename(path)
    rest = [ln for ln in lines[1:] if not re.fullmatch(r"[=\-~^*]{3,}", ln.strip())]
    paragraphs = re.split(r"\n\s*\n", "\n".join(rest).strip())
    description = " ".join(paragraphs[0].split()) if paragraphs[0] else ""

    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            modules.add(node.module)
    top = {m.split(".")[0] for m in modules}
    for module in modules:
        # The window-system backends of rendercanvas
        if re.fullmatch(r"rendercanvas\.(qt|pyside\d|pyqt\d)", module):
            top.add("PySide6")
        elif module in ("rendercanvas.wx", "rendercanvas.glfw"):
            top.add(module.split(".")[1])
    if any(m.startswith("wgpu.utils.imgui") for m in modules):
        top.add("imgui_bundle")

    def setting(name):
        m = re.search(rf"^# sphinx_gallery_pygfx_{name} = '(.*)'", source, re.M)
        return m.group(1) if m else ""

    # The size of the window that the example asks for (logical pixels): the
    # page gives the canvas that shape. 640x480 is the default of rendercanvas.
    size = re.search(r"\bsize=\((\d+),\s*(\d+)\)", source)
    width, height = (int(size.group(1)), int(size.group(2))) if size else (640, 480)

    for pattern, implied in IMPLIED_IMPORTS:
        if re.search(pattern, source):
            top.update(implied)

    return {
        "title": title,
        "size": [width, height],
        # Asked for explicitly: the example may lay out for exactly this size
        "fixed_size": bool(size),
        "description": description,
        "lines": source.count("\n") + 1,
        "modules": top,
        # Changes the interpreter for whatever runs after it
        "isolate": bool(re.search(ISOLATE, source)),
        # In pygfx's own gallery: 'screenshot', 'animate 4s', 'code', 'hidden'
        "docs": setting("docs"),
        "needs_data": bool(
            re.search(
                r"""["']data["']|data_dir|model_dir|["']screenshots["']""", source
            )
        ),
        "source": source,
        # Sample images that imageio would download: the site has them
        # Also names that are only combined with "imageio:" at runtime
        "imageio": sorted(
            set(re.findall(r"imageio:([\w.\-]+)", source))
            | set(re.findall(r"""["']([\w\-]+\.(?:png|jpg|npz))["']""", source))
        )
        or ["*"]  # the name is made at runtime: what the other examples use
        if "imageio:" in source
        else [],
    }


def data_entries(examples_dir):
    """The files that examples read, as the units that the site serves.

    "data/<name>" for every file or directory in examples/data, and
    "screenshots" (pygfx's reference screenshots, which an example compares).
    """
    names = sorted(os.listdir(os.path.join(examples_dir, "data")))
    return [f"data/{name}" for name in names] + ["screenshots"]


def used_data(source, entries):
    """The data entries that an example reads: those that its source names."""
    used = [e for e in entries if os.path.basename(e) in source]
    lists = re.search(r"glob\(|iterdir\(|listdir\(|os\.walk\(|scandir\(", source)
    if lists or not used:  # the names are made at runtime: all of the data
        return sorted(set(used) | {e for e in entries if e != "screenshots"})
    return used


def collect_examples(examples_dir, pyodide):
    pypi_by_import = pyodide["pypi_by_import"]
    with open(os.path.join(HERE, "notes.json"), encoding="utf-8") as f:
        notes = json.load(f)
    entries = data_entries(examples_dir)
    examples = []
    for category in CATEGORIES:
        names = sorted(os.listdir(os.path.join(examples_dir, category)))
        local_modules = {n[:-3] for n in names if n.endswith(".py")}
        for name in names:
            if not name.endswith(".py"):
                continue
            info = parse_example(os.path.join(examples_dir, category, name))
            modules = info.pop("modules")
            source = info.pop("source")
            extras = sorted(m for m in modules if m in pypi_by_import)
            packages = {PYODIDE_PACKAGES[m] for m in modules if m in PYODIDE_PACKAGES}
            for module in extras:
                # What the wheels of this module need of the Pyodide distribution
                packages.update(extra_requires(pyodide, module)[1])
            skip = sorted({UNAVAILABLE[m] for m in modules if m in UNAVAILABLE})
            examples.append(
                {
                    "id": f"{category}/{name[:-3]}",
                    "category": category,
                    "name": name[:-3],
                    **info,
                    "animated": info["docs"].startswith("animate"),
                    "packages": sorted(packages),
                    # Modules whose wheels (of PyPI) the site serves: manifest.extras
                    "extras": extras,
                    "pypi": sorted(pypi_by_import[m] for m in extras),
                    "data": used_data(source, entries) if info["needs_data"] else [],
                    "imports_examples": sorted(modules & (local_modules - {name[:-3]})),
                    "skip": SKIP_REASONS.get(f"{category}/{name[:-3]}", " ".join(skip)),
                    # Why it does not work (yet), for the examples that are run
                    "note": notes.get(f"{category}/{name[:-3]}", ""),
                }
            )
    return examples


def normalize(name):
    return re.sub(r"[-_.]+", "-", name).lower()


# CPython calls C functions through a trampoline. Where it thinks it is on iOS
# it uses one written in JavaScript (a workaround for a WebKit bug in iOS
# 18.3.1), and WebAssembly cannot suspend through a JavaScript frame: in
# Safari on an iPhone the first pyodide.ffi.run_sync was a fatal error
# ("SuspendError: JavaScript frames found between WebAssembly.Suspending and
# WebAssembly.promising"). A browser that has JSPI gets the WebAssembly
# trampoline here. See https://github.com/hmaarrfk/wgpudawn/issues/1
IOS_TRAMPOLINE = (
    "if(isIOS){return 0}",
    'if(isIOS&&typeof WebAssembly.Suspending!=="function"){return 0}',
)


def host_pyodide(out, pyodide, cache_dir):
    """The core of Pyodide, served by the site, with ``IOS_TRAMPOLINE`` applied.

    The packages of the distribution still come from where it is published.
    Returns the directory, relative to the site.
    """
    files = {}
    for name in (
        "pyodide.mjs",
        "pyodide.asm.mjs",
        "pyodide.asm.wasm",
        "pyodide-lock.json",
    ):
        path = download(
            pyodide["url"] + name,
            os.path.join(cache_dir, "pyodide", pyodide["version"], name),
        )
        with open(path, "rb") as f:
            files[name] = f.read()
    before, after = (text.encode() for text in IOS_TRAMPOLINE)
    if files["pyodide.asm.mjs"].count(before) != 1:
        raise SystemExit(
            "pyodide.asm.mjs does not have the iOS trampoline check as expected: "
            "see IOS_TRAMPOLINE in website/build.py (a newer Pyodide may not need it)"
        )
    files["pyodide.asm.mjs"] = files["pyodide.asm.mjs"].replace(before, after)
    name = "pyodide-{}-{}".format(
        pyodide["version"], digest(b"".join(files[k] for k in sorted(files)))
    )
    os.makedirs(os.path.join(out, name), exist_ok=True)
    for filename, data in files.items():
        with open(os.path.join(out, name, filename), "wb") as f:
            f.write(data)
    return name + "/"


def digest(data):
    return hashlib.sha256(data).hexdigest()[:12]


def download(url, path):
    """Fetch a URL into the cache, once."""
    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print(f"Downloading {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "wgpudawn-site"})
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


def pypi_wheel(spec, lock, cache_dir):
    """The wheel of a pinned package ("name==version") for this Pyodide.

    From PyPI, checked against the sha256 that PyPI states. A package with
    compiled code must have a wheel for the platform of the pinned Pyodide.
    """
    if "==" not in spec:
        raise SystemExit(f"pyodide.json: '{spec}' must be pinned (name==version)")
    name, version = spec.split("==")
    info = lock["info"]
    platform = f"pyemscripten_{info['abi_version']}_{info['arch']}"
    minor = int(info["python"].split(".")[1])
    meta_path = os.path.join(cache_dir, "pypi", f"{normalize(name)}-{version}.json")
    download(f"https://pypi.org/pypi/{name}/{version}/json", meta_path)
    with open(meta_path, encoding="utf-8") as f:
        files = json.load(f)["urls"]

    def fits(filename):
        if not filename.endswith(".whl"):
            return False
        python, abi, plat = filename[:-4].split("-")[-3:]
        if plat != "any" and plat != platform:
            return False
        if abi == "abi3":  # the stable ABI, of this Python or an older one
            return any(
                re.fullmatch(r"cp3(\d+)", tag) and int(tag[3:]) <= minor
                for tag in python.split(".")
            )
        return abi in ("none", f"cp3{minor}") and bool(
            {"py3", f"cp3{minor}"} & set(python.split("."))
        )

    found = [f for f in files if fits(f["filename"])]
    if not found:
        raise SystemExit(
            f"PyPI has no wheel of {spec} for {platform}, Python 3.{minor}"
        )
    # A wheel for this platform over a pure one
    chosen = sorted(found, key=lambda f: f["filename"].endswith("-any.whl"))[0]
    path = download(chosen["url"], os.path.join(cache_dir, "pypi", chosen["filename"]))
    with open(path, "rb") as f:
        if hashlib.sha256(f.read()).hexdigest() != chosen["digests"]["sha256"]:
            os.remove(path)
            raise SystemExit(f"{path} does not have the sha256 that PyPI states")
    return path


def wheel_requires(path):
    """The packages that a wheel always needs (no extras, no markers)."""
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.endswith(".dist-info/METADATA")]
        metadata = zf.read(names[0]).decode("utf-8", "replace") if names else ""
    requires = []
    for line in metadata.split("\n\n")[0].splitlines():
        if line.startswith("Requires-Dist:") and ";" not in line:
            requires.append(normalize(re.match(r"[\w.\-]+", line[14:].strip()).group()))
    return requires


def closure(lock, names):
    """Packages of the Pyodide distribution, with what they depend on."""
    done = []
    todo = [normalize(n) for n in names]
    known = {normalize(k): v for k, v in lock["packages"].items()}
    while todo:
        name = todo.pop(0)
        if name in done:
            continue
        if name not in known:
            raise SystemExit(f"The Pyodide distribution has no package '{name}'")
        done.append(name)
        todo += [normalize(d) for d in known[name]["depends"]]
    return done


def extra_requires(pyodide, module):
    """What an optional module needs: (pinned wheels of PyPI, Pyodide packages)."""
    spec = pyodide["pypi_by_import"][module]
    requires = pyodide.get("requires", {}).get(spec.split("==")[0], [])
    return (
        [spec] + [r for r in requires if "==" in r],
        [r for r in requires if "==" not in r],
    )


def check_requires(wheels, provided, what):
    """Nothing is resolved in the browser: every dependency must be listed."""
    have = {normalize(os.path.basename(w).split("-")[0]) for w in wheels}
    have |= {normalize(p) for p in provided}
    for wheel in wheels:
        missing = [r for r in wheel_requires(wheel) if r not in have]
        if missing:
            raise SystemExit(
                f"{os.path.basename(wheel)} requires {', '.join(missing)}, which "
                f"{what} does not list. Add it to website/pyodide.json: pinned "
                "(name==version) if it is on PyPI, by name if it is a package of "
                "the Pyodide distribution."
            )


def find_python(version):
    """A Python of this version (e.g. "3.14"), to compile for the Python of Pyodide."""
    if "%d.%d" % sys.version_info[:2] == version:
        return sys.executable
    return shutil.which(f"python{version}")


def compile_wheels(wheels, python, prefix):
    """The bytecode of the modules in these wheels, as {path in the bundle: bytes}.

    Without it, Python compiles every module that it imports, each time a page
    starts. The files are those that Python would write itself
    (``__pycache__/<module>.cpython-<version>.pyc``), with the path that the
    module has in the browser, and are used whatever the date of the source
    (unchecked hash). Bytecode is specific to the minor version of Python,
    hence ``python``: an interpreter with the version of the one in Pyodide.
    """
    compiled = {}
    with tempfile.TemporaryDirectory() as tmp:
        for wheel in wheels:
            with zipfile.ZipFile(wheel) as zf:
                zf.extractall(tmp)
        command = [python, "-m", "compileall", "-q", "-s", tmp, "-p", "/site/" + prefix]
        subprocess.run(
            [*command, "--invalidation-mode", "unchecked-hash", tmp],
            check=False,  # a file that does not compile is not ours to fix
            stdout=subprocess.DEVNULL,
        )
        for base, _dirs, files in os.walk(tmp):
            for name in files:
                if name.endswith(".pyc"):
                    path = os.path.join(base, name)
                    with open(path, "rb") as f:
                        compiled[prefix + os.path.relpath(path, tmp)] = f.read()
    return compiled


# Run by the Python of find_python(): the standard library of Pyodide (a zip
# of sources, which Python compiles on every start) with bytecode instead, as
# `pyodide py-compile` makes it. zipimport takes <module>.pyc where the source
# was. (The CDN has such a distribution, .../pyc/ instead of .../full/, but
# few use it: its files are often not at the edge, and then take seconds.)
COMPILE_STDLIB = """
import importlib.util, sys, zipfile
from importlib._bootstrap_external import _code_to_hash_pyc
src, dst, root = sys.argv[1:]
with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
    for item in sorted(zin.infolist(), key=lambda i: i.filename):
        name, data = item.filename, zin.read(item)
        if name.endswith(".py"):
            try:
                code = compile(data, root + name, "exec", dont_inherit=True)
                data = bytes(_code_to_hash_pyc(code, importlib.util.source_hash(data), False))
                name += "c"
            except SyntaxError:
                pass
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        info.external_attr = item.external_attr
        info.compress_type = zipfile.ZIP_DEFLATED
        zout.writestr(info, data, compresslevel=9)
"""


def compile_stdlib(path, python, version):
    """The standard library of Pyodide, compiled: the bytes of the new zip."""
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, "python_stdlib.zip")
        root = f"/lib/python{version.replace('.', '')}.zip/"
        subprocess.run([python, "-c", COMPILE_STDLIB, path, dst, root], check=True)
        with open(dst, "rb") as f:
            return f.read()


class Bundle:
    """A zip that is the same for the same content, named after its content."""

    def __init__(self):
        self.buffer = io.BytesIO()
        self.zf = zipfile.ZipFile(
            self.buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9
        )
        self.names = set()

    def add(self, arcname, data):
        if arcname in self.names:
            return
        self.names.add(arcname)
        info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
        info.external_attr = 0o644 << 16
        # Already compressed: do not spend time on it, here or in the browser
        packed = arcname.lower().endswith((".png", ".jpg", ".glb", ".npz", ".mp4"))
        info.compress_type = zipfile.ZIP_STORED if packed else zipfile.ZIP_DEFLATED
        self.zf.writestr(info, data)

    def add_wheel(self, path, prefix):
        with zipfile.ZipFile(path) as wheel:
            for name in sorted(wheel.namelist()):
                if not name.endswith("/"):
                    self.add(prefix + name, wheel.read(name))

    def add_tree(self, src, prefix, keep=lambda path: True):
        if os.path.isfile(src):
            with open(src, "rb") as f:
                self.add(prefix, f.read())
            return
        for base, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                path = os.path.join(base, name)
                if keep(path):
                    with open(path, "rb") as f:
                        self.add(prefix + "/" + os.path.relpath(path, src), f.read())

    def bytes(self):
        self.zf.close()
        return self.buffer.getvalue()


def write_hashed(out, pattern, data):
    """Write out/<pattern, with the hash of the data>: a name for this content."""
    name = pattern.format(digest(data))
    os.makedirs(os.path.dirname(os.path.join(out, name)), exist_ok=True)
    with open(os.path.join(out, name), "wb") as f:
        f.write(data)
    return {"url": name, "size": len(data)}


def imageio_images(names, out, cache_dir):
    """The sample images of imageio that the examples use ("imageio:xxx").

    imageio downloads these on first use. The site has them instead, one file
    each, and the page puts those that an example names in imageio's user
    directory, so that the examples do not need the network.
    """
    os.makedirs(cache_dir, exist_ok=True)
    shutil.rmtree(os.path.join(out, "imageio"), ignore_errors=True)
    images = {}
    for name in names:
        path = os.path.join(cache_dir, name)
        if not os.path.isfile(path):
            print(f"Downloading imageio:{name}")
            try:
                urllib.request.urlretrieve(IMAGEIO_URL + name, path + ".part")
            except urllib.error.HTTPError:
                continue  # not a sample image of imageio after all
            os.replace(path + ".part", path)
        with open(path, "rb") as f:
            data = f.read()
        base, ext = os.path.splitext(name)
        images[name] = write_hashed(out, f"imageio/{base}.{{}}{ext}", data)
    return images


def git(cwd, *args):
    try:
        return subprocess.check_output(["git", "-C", cwd, *args], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pygfx", required=True, help="A checkout of pygfx")
    parser.add_argument("--wheels", required=True, help="Directory with the wheels")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument(
        "--cache",
        default=os.path.join(ROOT, "build", "website-cache"),
        help="Where downloads are kept between builds",
    )
    parser.add_argument(
        "--no-bytecode",
        action="store_true",
        help="Do not compile the packages (to measure what the bytecode saves)",
    )
    args = parser.parse_args()

    examples_dir = os.path.join(args.pygfx, "examples")
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)

    # Static files. The page is one document with two views; run.html is the
    # same document, so that the address of an example is run.html?ex=<id>.
    for name in STATIC:
        shutil.copy(os.path.join(HERE, name), os.path.join(out, name))
    shutil.copy(os.path.join(HERE, "index.html"), os.path.join(out, "run.html"))
    open(os.path.join(out, ".nojekyll"), "w").close()

    # The pictures of the gallery: taken by check.mjs on a machine with a GPU,
    # and kept in the repository, because CI has no GPU to take them with
    shots = os.path.join(HERE, "shots")
    if os.path.isdir(shots):
        shutil.copytree(shots, os.path.join(out, "shots"), dirs_exist_ok=True)
    # What earlier versions of the site had
    for name in ("examples.zip", "examples-data.zip", "imageio.zip"):
        if os.path.exists(os.path.join(out, name)):
            os.remove(os.path.join(out, name))
    for name in os.listdir(out):
        if re.fullmatch(r"(base|python_stdlib)\.[0-9a-f]+\.zip", name):
            os.remove(os.path.join(out, name))
    for name in ("wheels", "data"):
        shutil.rmtree(os.path.join(out, name), ignore_errors=True)
        os.makedirs(os.path.join(out, name))

    with open(os.path.join(HERE, "pyodide.json"), encoding="utf-8") as f:
        pyodide = json.load(f)
    lock_path = download(
        pyodide["url"] + "pyodide-lock.json",
        os.path.join(args.cache, "pyodide", pyodide["version"], "pyodide-lock.json"),
    )
    with open(lock_path, encoding="utf-8") as f:
        lock = json.load(f)
    lock_files = {normalize(k): v["file_name"] for k, v in lock["packages"].items()}

    # Wheels of this project: the newest of each
    wheels = {}
    for name in sorted(os.listdir(args.wheels)):
        if name.endswith(".whl"):
            wheels[name.split("-")[0]] = name
    for key in ("wgpudawn", "pygfx", "freetype_py"):
        if key not in wheels:
            raise SystemExit(f"No {key} wheel in {args.wheels}")

    # What every example needs, in one file: the packages (the wheels,
    # unpacked), the Python side of the page, and the examples themselves
    # (in one place, because examples import each other).
    base_packages = closure(lock, pyodide["packages"])
    base_wheels = [
        os.path.join(args.wheels, wheels[k])
        for k in ("wgpudawn", "freetype_py", "pygfx")
    ] + [pypi_wheel(spec, lock, args.cache) for spec in pyodide["pypi_always"]]
    # wgpu is wgpudawn here (install_as_wgpu)
    check_requires(base_wheels, [*base_packages, "wgpu"], "pypi_always or packages")
    bundle = Bundle()
    for wheel in base_wheels:
        bundle.add_wheel(wheel, "packages/")
    version = ".".join(lock["info"]["python"].split(".")[:2])
    python = None if args.no_bytecode else find_python(version)
    if python:
        for name, data in sorted(
            compile_wheels(base_wheels, python, "packages/").items()
        ):
            bundle.add(name, data)
    elif not args.no_bytecode:
        print(
            f"No Python {version} here (the Python of Pyodide {pyodide['version']}): "
            "Python and the packages go without bytecode, and the pages start slower. "
            f"Run this with Python {version}, or have python{version} on the PATH."
        )
    bundle.add_tree(os.path.join(HERE, "webhost.py"), "packages/webhost.py")
    bundle.add_tree(
        examples_dir,
        "examples",
        keep=lambda p: p.endswith(".py") and os.sep + "data" + os.sep not in p + os.sep,
    )
    base = write_hashed(out, "base.{}.zip", bundle.bytes())
    stdlib = None
    if python:
        stdlib_path = download(
            pyodide["url"] + "python_stdlib.zip",
            os.path.join(
                args.cache, "pyodide", pyodide["version"], "python_stdlib.zip"
            ),
        )
        stdlib = write_hashed(
            out, "python_stdlib.{}.zip", compile_stdlib(stdlib_path, python, version)
        )

    # Packages that only some examples import, each wheel as it is
    extras = {}
    for module in pyodide["pypi_by_import"]:
        specs, packages = extra_requires(pyodide, module)
        paths = [pypi_wheel(spec, lock, args.cache) for spec in specs]
        check_requires(
            paths,
            [
                *base_packages,
                *closure(lock, packages),
                *(os.path.basename(w).split("-")[0] for w in base_wheels),
            ],
            f'"requires" of {specs[0].split("==")[0]}',
        )
        for path in paths:
            shutil.copy(path, os.path.join(out, "wheels", os.path.basename(path)))
        extras[module] = {
            "wheels": [
                {
                    "url": "wheels/" + os.path.basename(path),
                    "size": os.path.getsize(path),
                }
                for path in paths
            ],
            # ... and what they need of the Pyodide distribution
            "packages": extra_requires(pyodide, module)[1],
        }

    examples = collect_examples(examples_dir, pyodide)

    # The data files (large), per file or directory of examples/data: an
    # example fetches what it names. With pygfx's reference screenshots.
    data = {}
    for entry in sorted({d for e in examples for d in e["data"]}):
        zf = Bundle()
        zf.add_tree(
            os.path.join(examples_dir, entry),
            entry,
            keep=lambda p: os.sep + "diffs" + os.sep not in p,
        )
        name = entry.replace("/", "-")
        data[entry] = write_hashed(out, f"data/{name}.{{}}.zip", zf.bytes())
    images = imageio_images(
        sorted({name for e in examples for name in e["imageio"]} - {"*"}),
        out,
        args.cache,
    )
    src_out = os.path.join(out, "src")
    for example in examples:
        dst = os.path.join(src_out, example["id"] + ".py")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(examples_dir, example["id"] + ".py"), dst)

    with open(os.path.join(ROOT, "upstream.json"), encoding="utf-8") as f:
        upstream = json.load(f)
    pygfx_commit = git(args.pygfx, "rev-parse", "HEAD")
    used = {p for e in examples for p in e["packages"]}
    manifest = {
        "pyodide": {
            "version": pyodide["version"],
            "url": pyodide["url"],
            # The core of Pyodide as the site serves it (see host_pyodide)
            "index": host_pyodide(out, pyodide, args.cache),
            # Loaded for every example, and the files of the distribution
            # behind each package that the site uses (to fetch them early)
            "packages": pyodide["packages"],
            # The standard library with bytecode (None: that of the distribution)
            "stdlib": stdlib,
            # Modules that libraries try to import and do without (trimesh
            # and imageio do): not worth a download in the middle of an example
            "not_on_import": pyodide.get("not_on_import", []),
            "files": {
                name: [lock_files[p] for p in closure(lock, [name])]
                for name in sorted(used | set(pyodide["packages"]))
            },
        },
        "base": base,
        "extras": extras,
        "data": data,
        "imageio": images,
        "versions": {
            "wgpudawn": wheels["wgpudawn"].split("-")[1],
            "wgpudawn_commit": git(ROOT, "rev-parse", "HEAD"),
            "pygfx": wheels["pygfx"].split("-")[1],
            "pygfx_commit": pygfx_commit,
            # Where that commit is: pygfx/pygfx, or a fork with fixes on top
            "pygfx_repository": upstream["pygfx"]["repository"],
            "pygfx_upstream": upstream["pygfx"].get("upstream", ""),
            "dawn": upstream["dawn"]["tag"],
            "wgpu_py": upstream["wgpu-py"]["version"],
        },
        "categories": [{"id": c, "title": CATEGORY_TITLES[c]} for c in CATEGORIES],
        "examples": examples,
    }
    with open(os.path.join(out, "examples.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, separators=(",", ":"))

    n_skip = sum(bool(e["skip"]) for e in examples)
    print(f"{len(examples)} examples ({n_skip} cannot run in a browser) -> {out}")


if __name__ == "__main__":
    main()
