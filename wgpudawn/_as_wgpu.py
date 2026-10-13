"""Let libraries that ``import wgpu`` run on wgpudawn, by explicit opt-in.

wgpudawn does not install a ``wgpu`` module (it is co-installable with
wgpu-py). Libraries such as pygfx and rendercanvas import ``wgpu`` by name
though. ``install_as_wgpu()`` makes that name resolve to wgpudawn, for the
current process only.
"""

import sys
import types
import importlib
import importlib.abc
import importlib.util

# Modules of wgpu-py that have a different name in wgpudawn
RENAMED = {
    "wgpudawn.backends.wgpu_native": "wgpudawn.backends.dawn",
}


class _AliasLoader(importlib.abc.Loader):
    def __init__(self, module):
        self._module = module

    def create_module(self, spec):
        return self._module

    def exec_module(self, module):
        pass  # already executed, as a wgpudawn module


class _AliasFinder(importlib.abc.MetaPathFinder):
    """Make ``wgpu.xxx`` the very same module object as ``wgpudawn.xxx``."""

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("wgpu."):
            return None
        name = "wgpudawn" + fullname[len("wgpu") :]
        name = RENAMED.get(name, name)
        try:
            module = importlib.import_module(name)
        except ModuleNotFoundError:
            return None
        return importlib.util.spec_from_loader(fullname, _AliasLoader(module))


class _WgpuProxy(types.ModuleType):
    """The wgpudawn module under the name ``wgpu``.

    Everything is forwarded to wgpudawn, except the version: that is the
    version of the wgpu-py that wgpudawn mirrors, because libraries check for
    a minimum version of wgpu-py.
    """

    def __getattr__(self, name):
        return getattr(sys.modules["wgpudawn"], name)

    def __setattr__(self, name, value):
        setattr(sys.modules["wgpudawn"], name, value)

    def __dir__(self):
        return dir(sys.modules["wgpudawn"])


def install_as_wgpu():
    """Make ``import wgpu`` give wgpudawn, in this process.

    Call this before anything imports ``wgpu``, e.g. at the top of a script::

        import wgpudawn

        wgpudawn.install_as_wgpu()

        import pygfx  # uses wgpudawn

    Afterwards ``wgpu`` and all its submodules are wgpudawn's, also when
    wgpu-py is installed. Raises ``RuntimeError`` if wgpu-py is already imported.
    """
    wgpudawn = sys.modules["wgpudawn"]

    current = sys.modules.get("wgpu")
    if isinstance(current, _WgpuProxy):
        return
    # A module that is still being imported (the test-only stand-in for wgpu-py
    # that calls this function) has no API yet; anything else is wgpu-py.
    if current is not None and hasattr(current, "GPUDevice"):
        raise RuntimeError(
            "wgpu-py is already imported; call wgpudawn.install_as_wgpu() "
            "before the first 'import wgpu'."
        )

    proxy = _WgpuProxy("wgpu", wgpudawn.__doc__)
    version = wgpudawn.wgpu_py_version
    types.ModuleType.__setattr__(proxy, "__version__", version)
    types.ModuleType.__setattr__(
        proxy, "version_info", tuple(int(i) for i in version.split("."))
    )
    sys.meta_path.insert(0, _AliasFinder())
    sys.modules["wgpu"] = proxy
