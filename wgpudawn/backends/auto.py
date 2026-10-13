"""Load the backend. In wgpudawn there is only one: Dawn."""

import os
import sys


def _load_backend(backend_name):
    """Load a backend by name."""

    if backend_name == "dawn":
        from . import dawn as module
    else:  # no-cover
        raise ImportError(
            f"Unknown wgpudawn backend: '{backend_name}' (only 'dawn' is available)"
        )

    return module.gpu


def _auto_load_backend():
    """Decide on the backend automatically."""

    # If the backend has already been loaded (e.g. by importing wgpudawn.backends.dawn), use that
    current_gpu = sys.modules["wgpudawn"].gpu
    if type(current_gpu).__module__ != "wgpudawn._classes":
        return current_gpu

    # WGPUPY_BACKEND is the env var that wgpu-py uses to select a backend. We
    # only have Dawn, so any other value is an error rather than silently ignored.
    backend_name = os.getenv("WGPUPY_BACKEND", "").strip().lower().replace("-", "_")
    return _load_backend(backend_name or "dawn")


gpu = _auto_load_backend()
