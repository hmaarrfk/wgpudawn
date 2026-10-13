"""Build the website: the examples of pygfx, running in the browser on wgpudawn.

    python website/build.py --pygfx ../pygfx-src --wheels <dir> --out site

``--wheels`` is a directory with the wheels that the pages install: wgpudawn
for Pyodide, pygfx (pure Python) and freetype-py (``build_freetype.sh``).
Everything else comes from the Pyodide distribution or from PyPI at runtime.

The site is static. It has the gallery (``index.html``), the page that runs
one example (``run.html``), the examples themselves, and ``examples.json``:
the list of examples with what the pages need to know about each. Whether an
example actually works in the browser is not decided here: ``check.mjs`` runs
them all in headless Chrome, and writes ``results.json`` and the screenshots
that the gallery shows.
"""

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

IMAGEIO_URL = "https://github.com/imageio/imageio-binaries/raw/master/images/"

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

    return {
        "title": title,
        "size": [width, height],
        # Asked for explicitly: the example may lay out for exactly this size
        "fixed_size": bool(size),
        "description": description,
        "lines": source.count("\n") + 1,
        "modules": top,
        # In pygfx's own gallery: 'screenshot', 'animate 4s', 'code', 'hidden'
        "docs": setting("docs"),
        "needs_data": bool(
            re.search(
                r"""["']data["']|data_dir|model_dir|["']screenshots["']""", source
            )
        ),
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


def collect_examples(examples_dir, pypi_by_import):
    with open(os.path.join(HERE, "notes.json"), encoding="utf-8") as f:
        notes = json.load(f)
    examples = []
    for category in CATEGORIES:
        names = sorted(os.listdir(os.path.join(examples_dir, category)))
        local_modules = {n[:-3] for n in names if n.endswith(".py")}
        for name in names:
            if not name.endswith(".py"):
                continue
            info = parse_example(os.path.join(examples_dir, category, name))
            modules = info.pop("modules")
            skip = sorted({UNAVAILABLE[m] for m in modules if m in UNAVAILABLE})
            examples.append(
                {
                    "id": f"{category}/{name[:-3]}",
                    "category": category,
                    "name": name[:-3],
                    **info,
                    "animated": info["docs"].startswith("animate"),
                    "packages": sorted(
                        {PYODIDE_PACKAGES[m] for m in modules if m in PYODIDE_PACKAGES}
                    ),
                    "pypi": sorted(
                        {pypi_by_import[m] for m in modules if m in pypi_by_import}
                    ),
                    "imports_examples": sorted(modules & (local_modules - {name[:-3]})),
                    "skip": SKIP_REASONS.get(f"{category}/{name[:-3]}", " ".join(skip)),
                    # Why it does not work (yet), for the examples that are run
                    "note": notes.get(f"{category}/{name[:-3]}", ""),
                }
            )
    return examples


def zip_dir(src, dst, arc_prefix, keep=lambda path: True):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, dirs, files in os.walk(src):
            dirs[:] = sorted(d for d in dirs if d != "__pycache__")
            for name in sorted(files):
                path = os.path.join(base, name)
                if keep(path):
                    arc = os.path.join(arc_prefix, os.path.relpath(path, src))
                    zf.write(path, arc)


def zip_imageio(names, dst, cache_dir):
    """The sample images of imageio that the examples use ("imageio:xxx").

    imageio downloads these on first use. The site has them instead, laid out
    as imageio's user directory, so that the examples do not need the network.
    """
    os.makedirs(cache_dir, exist_ok=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as zf:
        for name in names:
            path = os.path.join(cache_dir, name)
            if not os.path.isfile(path):
                print(f"Downloading imageio:{name}")
                try:
                    urllib.request.urlretrieve(IMAGEIO_URL + name, path + ".part")
                except urllib.error.HTTPError:
                    continue  # not a sample image of imageio after all
                os.replace(path + ".part", path)
            zf.write(path, f"imageio/.imageio/images/{name}")


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
    args = parser.parse_args()

    examples_dir = os.path.join(args.pygfx, "examples")
    out = os.path.abspath(args.out)
    os.makedirs(os.path.join(out, "wheels"), exist_ok=True)

    # Static files
    for name in (
        "index.html",
        "run.html",
        "site.css",
        "runner.js",
        "logo.svg",
        "diagnose.html",
    ):
        shutil.copy(os.path.join(HERE, name), os.path.join(out, name))
    open(os.path.join(out, ".nojekyll"), "w").close()

    # Wheels: the newest of each
    wheels = {}
    for name in sorted(os.listdir(args.wheels)):
        if name.endswith(".whl"):
            wheels[name.split("-")[0]] = name
    for key in ("wgpudawn", "pygfx", "freetype_py"):
        if key not in wheels:
            raise SystemExit(f"No {key} wheel in {args.wheels}")
    for name in wheels.values():
        shutil.copy(os.path.join(args.wheels, name), os.path.join(out, "wheels", name))

    # The examples: sources in one small zip (examples import each other), the
    # data files (large) in another, which is only fetched when needed
    with open(os.path.join(HERE, "pyodide.json"), encoding="utf-8") as f:
        pyodide = json.load(f)
    examples = collect_examples(examples_dir, pyodide["pypi_by_import"])
    zip_dir(
        examples_dir,
        os.path.join(out, "examples.zip"),
        "examples",
        keep=lambda p: p.endswith(".py") and os.sep + "data" + os.sep not in p + os.sep,
    )
    # ... together with pygfx's reference screenshots, which an example compares
    zip_dir(
        examples_dir,
        os.path.join(out, "examples-data.zip"),
        "examples",
        keep=lambda p: (
            os.sep + "data" + os.sep in p or os.sep + "screenshots" + os.sep in p
        ),
    )
    zip_imageio(
        sorted({name for e in examples for name in e["imageio"]} - {"*"}),
        os.path.join(out, "imageio.zip"),
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
    manifest = {
        "pyodide": pyodide,
        "wheels": [wheels[k] for k in ("wgpudawn", "freetype_py", "pygfx")],
        "versions": {
            "wgpudawn": wheels["wgpudawn"].split("-")[1],
            "wgpudawn_commit": git(ROOT, "rev-parse", "HEAD"),
            "pygfx": wheels["pygfx"].split("-")[1],
            "pygfx_commit": pygfx_commit,
            "dawn": upstream["dawn"]["tag"],
            "wgpu_py": upstream["wgpu-py"]["version"],
        },
        "categories": [{"id": c, "title": CATEGORY_TITLES[c]} for c in CATEGORIES],
        "examples": examples,
    }
    with open(os.path.join(out, "examples.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)

    n_skip = sum(bool(e["skip"]) for e in examples)
    print(f"{len(examples)} examples ({n_skip} cannot run in a browser) -> {out}")


if __name__ == "__main__":
    main()
