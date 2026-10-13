"""
WebGPU for Python, on Dawn.

The API of wgpu-py, with Dawn as the (only) backend.
"""

# ruff: noqa: F401, F403

from ._coreutils import logger
from ._version import __version__
from ._diagnostics import diagnostics, DiagnosticsBase
from .flags import *
from .enums import *
from .structs import *
from .classes import *
from .utils.device import *
from . import utils
from . import backends
from . import resources
from ._as_wgpu import install_as_wgpu


# The version of wgpu-py that this version of wgpudawn mirrors: same API, and
# the same behavior as far as the backends allow. See upstream.json in the repo.
wgpu_py_version = "0.32.0"

version_info = tuple(
    int(i) if i.isdecimal() else i for i in __version__.split("+")[0].split(".")
)

# The API entrypoint, from wgpudawn.classes - gets replaced when a backend loads.
gpu = GPU()  # noqa: F405


def rendercanvas_context_hook(canvas, _):
    raise RuntimeError(
        "The rendercanvas_context_hook is deprecated. If you're using rendercanvas, please update to the latest version. Otherwise, use wgpudawn.gpu.get_canvas_context()"
    )
