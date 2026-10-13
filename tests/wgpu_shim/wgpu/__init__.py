"""A stand-in for wgpu-py, for testing only: ``import wgpu`` gives wgpudawn.

``wgpu`` becomes a thin proxy for the ``wgpudawn`` module, and every
``wgpu.xxx`` submodule is the very same module object as ``wgpudawn.xxx`` (not
a copy), so that libraries that ``import wgpu`` (pygfx, rendercanvas, ...) run
on wgpudawn unmodified. The only difference with ``wgpudawn`` itself is the
version: ``wgpu.__version__`` is the wgpu-py version that wgpudawn mirrors,
because libraries check for a minimum version of wgpu-py.

It is not shipped with wgpudawn: wgpudawn and wgpu-py are co-installable, and
this package takes the place of wgpu-py.
"""

import sys
import types
import importlib
import importlib.abc
import importlib.util

import wgpudawn

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


class _Proxy(types.ModuleType):
    """The wgpudawn module, with the version of the wgpu-py that it mirrors."""

    __version__ = wgpudawn.wgpu_py_version
    version_info = tuple(int(i) for i in wgpudawn.wgpu_py_version.split("."))

    def __getattr__(self, name):
        return getattr(wgpudawn, name)

    def __setattr__(self, name, value):
        setattr(wgpudawn, name, value)

    def __dir__(self):
        return dir(wgpudawn)


sys.meta_path.insert(0, _AliasFinder())
sys.modules[__name__] = _Proxy(__name__, wgpudawn.__doc__)
