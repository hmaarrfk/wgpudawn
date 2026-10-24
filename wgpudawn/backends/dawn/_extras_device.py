"""Dawn's native extras for the instance, adapters and devices: backends,
validation, toggles, feature information, memory statistics, and the native
objects of the backend. See extras.py.
"""

import os
from typing import Sequence, Union

from ... import enums, structs
from ._api import GPUAdapter, GPUDevice, enum_str2int, ffi, logger
from . import _helpers
from ._helpers import dawn_instance_extras, get_wgpu_instance, new_toggles_struct
from ._extras_util import _native


# wgpu-native's backend names (wgpu-py's set_instance_extras) and Dawn's
_backend_names = {
    "All": ("Vulkan", "Metal", "D3D12", "D3D11"),
    "Primary": ("Vulkan", "Metal", "D3D12"),
    "Secondary": ("D3D11",),
    "Vulkan": ("Vulkan",),
    "Metal": ("Metal",),
    "DX12": ("D3D12",),
    "D3D12": ("D3D12",),
    "D3D11": ("D3D11",),
    "GL": (),  # wgpudawn is built without the OpenGL backends
    "BrowserWebGPU": (),
}

# wgpu-native's instance flags that Dawn has: its backend validation level
_validation_flags = {"Debug": 1, "Validation": 1, "GpuBasedValidation": 0}
_validation_levels = {"full": 0, "partial": 1, "disabled": 2}

_toggle_stages = ("instance", "adapter", "device")


def set_instance_extras(
    backends: Sequence[str] = ("All",),
    flags: Sequence[str] = ("Default",),
    dx12_compiler="fxc",
    gles3_minor_version="Atomic",
    fence_behavior="Normal",
    dxc_path: Union[os.PathLike, None] = None,
    dxc_max_shader_model: float = 6.5,
    budget_for_device_creation: Union[int, None] = None,
    budget_for_device_loss: Union[int, None] = None,
    *,
    enable_toggles: Sequence[str] = (),
    disable_toggles: Sequence[str] = (),
):
    """Set up the global instance. Must be called before it is created (by the
    first ``request_adapter`` or ``enumerate_adapters``).

    The signature is that of wgpu-py's ``wgpu.backends.wgpu_native.extras``;
    what Dawn has of it is used, and asking for the rest is an error:

    Arguments:
        backends (list of str): the backends that adapters may be of:
            ``"Vulkan"``, ``"Metal"``, ``"DX12"`` (or ``"D3D12"``), ``"D3D11"``,
            ``"Primary"`` (Vulkan, Metal, D3D12), ``"Secondary"`` (D3D11), or
            ``"All"``. Requesting an adapter takes the first of these that the
            system has, in that order.
        flags (list of str): ``"Debug"`` and ``"Validation"`` turn on the
            validation layers of the backend (Vulkan's, D3D12's debug layer,
            Metal's validation), ``"GpuBasedValidation"`` also their GPU-based
            validation. They must be installed; they make everything slower.
        dx12_compiler (str): ``"dxc"`` compiles shaders with DXC instead of FXC
            on D3D12 (Dawn's ``use_dxc`` toggle; DXC must be available).
        enable_toggles (list of str): Dawn toggles to enable, e.g.
            ``"allow_unsafe_apis"`` (needed for Dawn's experimental features,
            such as ``multi-draw-indirect``), ``"dump_shaders"``,
            ``"skip_validation"``. :func:`all_toggles` lists them; each goes to
            the instance, every adapter or every device, by its stage.
        disable_toggles (list of str): Dawn toggles to disable (e.g.
            ``"lazy_clear_resource_on_first_use"``).

    The other arguments are for wgpu-native's OpenGL and DXC options and must
    keep their defaults.
    """
    unsupported = {
        "gles3_minor_version": (gles3_minor_version, "Atomic"),
        "fence_behavior": (fence_behavior, "Normal"),
        "dxc_path": (dxc_path, None),
        "dxc_max_shader_model": (dxc_max_shader_model, 6.5),
        "budget_for_device_creation": (budget_for_device_creation, None),
        "budget_for_device_loss": (budget_for_device_loss, None),
    }
    for name, (value, default) in unsupported.items():
        if value != default:
            raise ValueError(f"set_instance_extras: Dawn has no {name}")

    allowed = set()
    for name in backends:
        if name not in _backend_names:
            raise ValueError(f"Unknown backend {name!r}: {sorted(_backend_names)}")
        allowed.update(_backend_names[name])

    validation = None
    for flag in flags:
        if flag in _validation_flags:
            level = _validation_flags[flag]
            validation = level if validation is None else min(validation, level)
        elif flag != "Default":
            raise ValueError(f"set_instance_extras: Dawn has no instance flag {flag!r}")

    enabled = {stage: [] for stage in _toggle_stages}
    disabled = {stage: [] for stage in _toggle_stages}
    if dx12_compiler.lower() == "dxc":
        enabled["adapter"].append("use_dxc")
    elif dx12_compiler.lower() not in ("fxc", "undefined"):
        raise ValueError(f"Unknown dx12_compiler {dx12_compiler!r}")
    toggles = all_toggles()
    for names, by_stage in ((enable_toggles, enabled), (disable_toggles, disabled)):
        for name in names:
            if name not in toggles:
                raise ValueError(f"Unknown Dawn toggle {name!r}: see all_toggles()")
            by_stage[toggles[name]["stage"]].append(name)

    if _helpers._the_instance is not None:
        raise RuntimeError(
            "Instance already exists. Please call `set_instance_extras` before "
            "the instance is created (calls to `request_adapter` or "
            "`enumerate_adapters`)"
        )
    keepalive = []
    c_toggles = new_toggles_struct(enabled["instance"], disabled["instance"], keepalive)
    instance = get_wgpu_instance(extras=c_toggles if c_toggles else None)
    if validation is not None:
        _native("wgpu_dawn_set_backend_validation_level")(instance, validation)
    # Adapters and devices get the toggles of their stage (Dawn validates
    # them per stage), and adapters only the backends asked for.
    dawn_instance_extras["backends"] = (
        None if allowed >= set(_backend_names["All"]) else allowed
    )
    dawn_instance_extras["adapter_toggles"] = (
        tuple(enabled["adapter"]),
        tuple(disabled["adapter"]),
    )
    dawn_instance_extras["device_toggles"] = (
        tuple(enabled["device"]),
        tuple(disabled["device"]),
    )


def request_device_sync(
    adapter: GPUAdapter,
    trace_path: Union[str, None] = None,
    *,
    label: str = "",
    required_features: Sequence[enums.FeatureName] = (),
    required_limits: Union[dict[str, int], None] = None,
    default_queue: Union[structs.QueueDescriptorStruct, None] = None,
    enable_toggles: Sequence[str] = (),
    disable_toggles: Sequence[str] = (),
) -> GPUDevice:
    """Request a device with Dawn's device toggles.

    The signature is that of wgpu-py's ``wgpu.backends.wgpu_native.extras``,
    plus ``enable_toggles`` and ``disable_toggles`` (device toggles, see
    :func:`all_toggles`), which come on top of those of
    :func:`set_instance_extras`. Dawn cannot write a trace of the API calls,
    so ``trace_path`` must be None.
    """
    if trace_path is not None:
        raise NotImplementedError("Dawn cannot write a trace (trace_path)")
    toggles = all_toggles()
    for name in (*enable_toggles, *disable_toggles):
        if name not in toggles:
            raise ValueError(f"Unknown Dawn toggle {name!r}: see all_toggles()")
        if toggles[name]["stage"] != "device":
            raise ValueError(
                f"Dawn toggle {name!r} is a toggle of the {toggles[name]['stage']}: "
                "give it to set_instance_extras()"
            )
    enabled, disabled = dawn_instance_extras["device_toggles"]
    enabled = [t for t in enabled if t not in disable_toggles] + list(enable_toggles)
    disabled = [t for t in disabled if t not in enable_toggles] + list(disable_toggles)
    promise = adapter._request_device_async(
        label,
        required_features,
        {} if required_limits is None else required_limits,
        {} if default_queue is None else default_queue,
        "",
        toggles=(tuple(enabled), tuple(disabled)),
    )
    return promise.sync_wait()


def request_device(*args, **kwargs):
    """Deprecated: use :func:`request_device_sync` (as in wgpu-py)."""
    logger.warning(
        "WGPU: request_device() is deprecated, use request_device_sync() instead."
    )
    return request_device_sync(*args, **kwargs)


def all_toggles():
    """All of Dawn's toggles: ``{name: {"description": str, "stage": str}}``,
    where the stage (``"instance"``, ``"adapter"`` or ``"device"``) is where the
    toggle is given (see :func:`set_instance_extras`, :func:`request_device_sync`)."""
    function = _native("wgpu_dawn_all_toggles")
    count = function(ffi.NULL, ffi.NULL, ffi.NULL, 0)
    names = ffi.new("const char *[]", count)
    descriptions = ffi.new("const char *[]", count)
    stages = ffi.new("int[]", count)
    count = min(count, function(names, descriptions, stages, count))
    return {
        ffi.string(names[i]).decode(): {
            "description": ffi.string(descriptions[i]).decode(),
            "stage": _toggle_stages[stages[i]],
        }
        for i in range(count)
    }


def get_toggles(adapter_or_device):
    """The names of the Dawn toggles that are enabled on an adapter or device:
    those asked for, and those that Dawn enables itself (workarounds for the
    driver, defaults of the backend)."""
    if isinstance(adapter_or_device, GPUDevice):
        function = _native("wgpu_dawn_device_toggles")
    elif isinstance(adapter_or_device, GPUAdapter):
        function = _native("wgpu_dawn_adapter_toggles")
    else:
        raise TypeError("get_toggles() takes a GPUAdapter or a GPUDevice")
    handle = adapter_or_device._internal
    count = function(handle, ffi.NULL, 0)
    names = ffi.new("const char *[]", count)
    count = min(count, function(handle, names, count))
    return [ffi.string(names[i]).decode() for i in range(count)]


def feature_info(feature):
    """What Dawn says about a feature (a name from ``adapter.features``):
    ``{"name": Dawn's name, "description": str, "experimental": bool}``. An
    experimental feature is only offered with the ``allow_unsafe_apis``
    toggle (see :func:`set_instance_extras`)."""
    from ._mappings import enummap

    value = enummap.get(f"FeatureName.{feature}")
    if value is None:
        value = enum_str2int["FeatureName"].get(feature)
    if value is None:
        raise KeyError(f"Unknown feature: {feature!r}")
    name = ffi.new("const char **")
    description = ffi.new("const char **")
    experimental = ffi.new("int *")
    if not _native("wgpu_dawn_feature_info")(value, name, description, experimental):
        raise KeyError(f"Dawn has no information about {feature!r}")
    return {
        "name": ffi.string(name[0]).decode(),
        "description": ffi.string(description[0]).decode(),
        "experimental": bool(experimental[0]),
    }


def get_memory_usage(device: GPUDevice):
    """Dawn's estimate of the GPU memory that a device uses, in bytes:
    ``{"total", "textures", "buffers", "depth_stencil_textures",
    "msaa_textures", "msaa_texture_count", "largest_msaa_texture"}``, and what
    its allocator holds: ``"allocator_used"``, ``"allocator_allocated"`` (and
    the ``"allocator_lazy_*"`` of memory that is allocated on first use)."""
    usage = ffi.new("uint64_t[7]")
    _native("wgpu_dawn_memory_usage")(device._internal, usage)
    allocator = ffi.new("uint64_t[4]")
    _native("wgpu_dawn_allocator_memory")(device._internal, allocator)
    return {
        "total": usage[0],
        "depth_stencil_textures": usage[1],
        "msaa_textures": usage[2],
        "msaa_texture_count": usage[3],
        "largest_msaa_texture": usage[4],
        "textures": usage[5],
        "buffers": usage[6],
        "allocator_used": allocator[0],
        "allocator_allocated": allocator[1],
        "allocator_lazy_allocated": allocator[2],
        "allocator_lazy_used": allocator[3],
    }


def reduce_memory_usage(device: GPUDevice):
    """Ask Dawn to free memory that it keeps for reuse (e.g. when the
    application goes to the background). Returns whether there is still
    work to wait for before more can be freed."""
    return bool(_native("wgpu_dawn_reduce_memory_usage")(device._internal))


def perform_idle_tasks(device: GPUDevice):
    """Let Dawn do deferred work now (e.g. when the application is idle)."""
    _native("wgpu_dawn_perform_idle_tasks")(device._internal)


def _check_backend(device, backend):
    if device.adapter.info["backend_type"] != backend:
        raise RuntimeError(
            f"The device is not a {backend} device "
            f"({device.adapter.info['backend_type']})"
        )


def get_vk_instance(device: GPUDevice):
    """The ``VkInstance`` of a Vulkan device, as an int. It is owned by Dawn."""
    _check_backend(device, "Vulkan")
    ptr = _native("wgpu_dawn_vk_instance")(device._internal)
    return int(ffi.cast("uintptr_t", ptr))


def get_vk_instance_proc_addr(device: GPUDevice, name: str):
    """Vulkan's ``vkGetInstanceProcAddr(instance, name)`` for the instance of a
    Vulkan device: the address of a Vulkan function as an int (0 when the
    instance does not have it). With :func:`get_vk_instance`, this is what
    another library needs to make Vulkan calls on Dawn's instance."""
    _check_backend(device, "Vulkan")
    ptr = _native("wgpu_dawn_vk_get_instance_proc_addr")(
        device._internal, ffi.new("char[]", name.encode())
    )
    return int(ffi.cast("uintptr_t", ptr))
