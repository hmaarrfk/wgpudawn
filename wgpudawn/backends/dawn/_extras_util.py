"""Helpers of Dawn's native extras (see extras.py)."""

from ._api import lib, libf


def _native(name):
    """A function of the native build, or a clear error on a build without it."""
    function = getattr(libf, name, None)
    if function is None:
        raise RuntimeError(
            f"{name} is not available in this build of wgpudawn "
            "(Dawn's native extras need a native build)"
        )
    return function


def _check_status(status, what):
    # Dawn reports the reason through the device's error callback, which libf
    # raises; this is for a failure that produced no error.
    if status != lib.WGPUStatus_Success:
        raise RuntimeError(f"{what} failed (status {status})")
