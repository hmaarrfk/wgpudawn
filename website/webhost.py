"""The Python side of the website: runs the examples, one after another.

``runner.js`` puts this module in the interpreter (it is in the base bundle
that ``build.py`` makes) and calls ``setup()`` once, then for every example
``run()`` and, before the next one, ``teardown()``.

One interpreter serves a whole visit, so an example starts in a fraction of
the time that starting Python takes. What makes that honest is here: an
example gets a fresh ``__main__``, its own working directory and arguments,
and only the data files that it names; and what the previous example left
running (canvases, draw callbacks, tasks, modules of its own directory) is
gone before the next one starts. What cannot be undone (the configuration of
the GPU device) is not attempted: ``runner.js`` gives such examples an
interpreter of their own.
"""

import gc
import importlib
import importlib.abc
import importlib.util
import linecache
import logging
import os
import runpy
import sys

ROOT = "/site"
EXAMPLES = ROOT + "/examples"
# Data entries wait in the store, and are in the examples directory only
# while an example that names them runs
STORE = ROOT + "/store"
IMAGE_STORE = ROOT + "/images"
IMAGES = "/imageio/.imageio/images"  # imageio's user directory

_placed = set()  # data entries that are in EXAMPLES now
_images = set()  # sample images that are in IMAGES now
_before = None  # the state of the interpreter that run() changed


class LazyPackages(importlib.abc.MetaPathFinder):
    """Load a package when it is imported, if Pyodide or the site knows it.

    The packages that an example imports itself are loaded up front. This is
    for the rest: imports inside functions, and of dependencies.
    """

    def __init__(self, knows, load):
        self._knows = knows
        self._load = load
        self._busy = set()

    def find_spec(self, fullname, path=None, target=None):
        if "." in fullname or fullname in self._busy or not self._knows(fullname):
            return None
        from pyodide.ffi import run_sync

        self._busy.add(fullname)
        try:
            run_sync(self._load(fullname))
            importlib.invalidate_caches()
            return importlib.util.find_spec(fullname)
        except Exception as err:
            print(f"Could not load {fullname}: {err}", file=sys.stderr)
            return None
        finally:
            self._busy.discard(fullname)


class ReportErrors(logging.Handler):
    """Errors that are logged, as "ERROR:" lines on stderr.

    In a browser, validation errors of the GPU arrive after the call that
    caused them, so they are logged instead of raised. The page counts these
    lines to know that an example does not really work.
    """

    def emit(self, record):
        print(f"ERROR: {record.name}: {record.getMessage()}", file=sys.stderr)


def setup(knows, load):
    """Once per interpreter. ``knows(name)`` and ``load(name)`` are of the page."""
    for path in (STORE, IMAGE_STORE, IMAGES, EXAMPLES + "/data", "/tmp/pygfx"):
        os.makedirs(path, exist_ok=True)
    os.environ["PYGFX_DATA_DIR"] = "/tmp/pygfx"  # pygfx does not know this platform
    os.environ["IMAGEIO_USERDIR"] = "/imageio"  # where the page puts the sample images
    sys.meta_path.append(LazyPackages(knows, load))
    logging.getLogger().addHandler(ReportErrors(level=logging.ERROR))

    import wgpudawn

    wgpudawn.install_as_wgpu()  # pygfx and rendercanvas import wgpu by name
    _size_at_once()


def _size_at_once():
    """A canvas knows its size when it is created, as a window on a desktop does.

    In a browser, rendercanvas learns the size of its element from a
    ResizeObserver, i.e. after the code that created the canvas has returned
    to the browser. An example that asks for the size right away (to place a
    camera, to lay out) only gets it if something happened to wait in
    between, such as the first request for a GPU device. In an interpreter
    that has the device already, nothing waits. So the size is read here.
    """
    from js import window
    from rendercanvas import pyodide as backend

    original = backend.PyodideRenderCanvas._final_canvas_init

    def _final_canvas_init(self):
        try:
            element = self._canvas_element
            ratio = window.devicePixelRatio
            # The size of the layout, which a transform (the page scales a
            # canvas of a fixed size) does not change
            width = int(element.clientWidth * ratio)
            height = int(element.clientHeight * ratio)
            if width > 0 and height > 0:
                element.width = width
                element.height = height
                self._on_resize(width, height, ratio)
        except Exception as err:  # the observer will tell
            print(f"Could not read the size of the canvas: {err}", file=sys.stderr)
        original(self)

    backend.PyodideRenderCanvas._final_canvas_init = _final_canvas_init


def _place(wanted, placed, store, target):
    """Make exactly the wanted entries of the store present in the target."""
    wanted = set(wanted)
    for entry in placed - wanted:
        if os.path.lexists(f"{target}/{entry}"):
            os.rename(f"{target}/{entry}", f"{store}/{entry}")
    for entry in wanted - placed:
        os.makedirs(os.path.dirname(f"{target}/{entry}"), exist_ok=True)
        os.rename(f"{store}/{entry}", f"{target}/{entry}")
    placed.clear()
    placed.update(wanted)


def run(example_id, data, images):
    """Run an example as ``__main__``, with the data and sample images it names."""
    global _before
    _place(data, _placed, STORE, EXAMPLES)
    _place(images, _images, IMAGE_STORE, IMAGES)
    importlib.invalidate_caches()
    path = f"{EXAMPLES}/{example_id}.py"
    _before = (os.getcwd(), list(sys.path), list(sys.argv))
    os.chdir(os.path.dirname(path))
    sys.path.insert(0, os.path.dirname(path))
    sys.argv = [path]
    runpy.run_path(path, run_name="__main__")


def device_lost():
    """Whether the GPU device of pygfx is gone (the browser can take it away).

    A lost device accepts every call and reports no error, and draws nothing:
    what runs on it looks like it works. The page then starts a new
    interpreter, which asks for a new device.
    """
    try:
        from pygfx.renderers.wgpu.engine.shared import Shared

        shared = Shared.get_instance()
        return shared is not None and shared.device._lost_promise._state != "pending"
    except Exception:
        return False


def _loops():
    """The event loops of rendercanvas that exist (one per backend in use)."""
    loops = {}
    for name, module in list(sys.modules.items()):
        if name == "rendercanvas" or name.startswith("rendercanvas."):
            loop = getattr(module, "loop", None)
            if loop is not None and hasattr(loop, "get_canvases"):
                loops[id(loop)] = loop
    return list(loops.values())


async def teardown():
    """End what the last example left running. Returns the number of canvases closed."""
    global _before
    import asyncio

    closed = 0
    # Let what was scheduled start, so that it can be cancelled properly
    await asyncio.sleep(0)
    for loop in _loops():
        canvases = loop.get_canvases()
        closed += len(canvases)
        # Closes the canvases (which removes their elements from the page and
        # drops the draw functions and event handlers), and cancels the tasks
        # of the loop: the schedulers of the canvases and what the example added
        loop.stop(force=True)
        for canvas in canvases:
            if not canvas.get_closed():
                canvas.close()
        del canvases
    # Cancelled tasks end when the event loop gets to them
    for _ in range(3):
        await asyncio.sleep(0)

    if _before is not None:
        cwd, path, argv = _before
        _before = None
        os.chdir(cwd)
        sys.path[:] = path
        sys.argv[:] = argv
    # Modules of the examples directory: the next example imports its own
    for name, module in list(sys.modules.items()):
        if str(getattr(module, "__file__", "") or "").startswith(EXAMPLES + "/"):
            del sys.modules[name]
    linecache.clearcache()
    importlib.invalidate_caches()
    # The scene of the example, and with it its buffers and textures on the GPU
    gc.collect()
    return closed
