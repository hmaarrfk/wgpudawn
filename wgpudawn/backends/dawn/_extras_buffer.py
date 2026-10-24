"""Dawn's native extras for buffers in memory that another API or process
owns (Windows: a D3D12 resource, a shared memory handle, host memory). See
extras.py.
"""

from dataclasses import dataclass, field

from ... import enums, flags
from ..._coreutils import str_flag_to_int
from ._api import (
    GPUBuffer,
    GPUDevice,
    GPUObjectBase,
    ffi,
    lib,
    libf,
    new_struct_p,
    to_c_string_view,
)
from ._ffi import CALLBACK_MODE, callbacks
from ._helpers import get_memoryview_and_address
from ._extras_util import _native, _check_status


# Dawn calls this (a WGPUDisposeCallback) when it no longer uses host memory
# that was imported as shared buffer memory.
@ffi.def_extern(name="_wgpu_dawn_native_WGPUDisposeCallback")
def _dispose(status, userdata1, userdata2):
    callbacks.call(userdata1, status)


@dataclass
class SharedBufferMemoryEndAccessState:
    """What :meth:`GPUSharedBufferMemory.end_access` returns: the GPU work on
    the buffer is done when each fence has reached its value."""

    initialized: bool
    fences: list = field(default_factory=list)
    signaled_values: list = field(default_factory=list)


class GPUSharedBufferMemory(GPUObjectBase):
    """Memory that another API or process owns, that buffers can be made on.

    Made by :func:`import_shared_buffer_memory`. A buffer made from it may only
    be used on the queue between :meth:`begin_access` and :meth:`end_access`.
    """

    _release_function = None  # set on first use: the native build has it

    def __init__(self, label, internal, device):
        super().__init__(label, internal, device)
        struct = new_struct_p("WGPUSharedBufferMemoryProperties *")
        status = _native("wgpuSharedBufferMemoryGetProperties")(internal, struct)
        _check_status(status, "wgpuSharedBufferMemoryGetProperties")
        self._properties = {"usage": int(struct.usage), "size": int(struct.size)}

    @property
    def properties(self):
        """``{"usage", "size"}``: the usage a buffer may have (an int of
        :class:`wgpudawn.BufferUsage` flags) and the size in bytes."""
        return self._properties

    def is_device_lost(self):
        """Whether the device that imported the memory has been lost."""
        return bool(_native("wgpuSharedBufferMemoryIsDeviceLost")(self._internal))

    def create_buffer(self, *, label="", usage=None) -> GPUBuffer:
        """Create a buffer on the memory, of its whole size.

        Arguments:
            label (str): A human-readable label. Optional.
            usage (BufferUsageFlags): A subset of ``properties["usage"]``; that
                whole usage by default.
        """
        if usage is None:
            usage = self._properties["usage"]
        elif isinstance(usage, str):
            usage = str_flag_to_int(flags.BufferUsage, usage)
        size = self._properties["size"]
        struct = new_struct_p(
            "WGPUBufferDescriptor *",
            label=to_c_string_view(label),
            usage=int(usage),
            size=size,
            mappedAtCreation=False,
        )
        id = _native("wgpuSharedBufferMemoryCreateBuffer")(self._internal, struct)
        return GPUBuffer(
            label, id, self._device, size, int(usage), enums.BufferMapState.unmapped
        )

    def begin_access(self, buffer, *, initialized=True, fences=(), signaled_values=()):
        """Start using ``buffer`` (made by :meth:`create_buffer`) on the queue,
        after the GPU has waited for the ``fences`` to reach their
        ``signaled_values`` (see :func:`import_shared_fence`)."""
        if len(fences) != len(signaled_values):
            raise ValueError("fences and signaled_values must have the same length")
        c_fences = ffi.new(
            "WGPUSharedFence[]", [f._internal for f in fences] or [ffi.NULL]
        )
        c_values = ffi.new("uint64_t[]", list(signaled_values) or [0])
        struct = new_struct_p(
            "WGPUSharedBufferMemoryBeginAccessDescriptor *",
            initialized=bool(initialized),
            fenceCount=len(fences),
            fences=c_fences,
            signaledValueCount=len(signaled_values),
            signaledValues=c_values,
        )
        status = _native("wgpuSharedBufferMemoryBeginAccess")(
            self._internal, buffer._internal, struct
        )
        _check_status(status, "wgpuSharedBufferMemoryBeginAccess")

    def end_access(self, buffer):
        """Stop using ``buffer`` on the queue. Returns a
        :class:`SharedBufferMemoryEndAccessState` with the fences that the
        other side waits for."""
        from .extras import GPUSharedFence

        state = new_struct_p("WGPUSharedBufferMemoryEndAccessState *")
        status = _native("wgpuSharedBufferMemoryEndAccess")(
            self._internal, buffer._internal, state
        )
        _check_status(status, "wgpuSharedBufferMemoryEndAccess")
        fences = []
        for i in range(state.fenceCount):
            # The state owns its fences, and FreeMembers releases them
            _native("wgpuSharedFenceAddRef")(state.fences[i])
            fences.append(GPUSharedFence("", state.fences[i], self._device))
        values = [int(state.signaledValues[i]) for i in range(state.signaledValueCount)]
        result = SharedBufferMemoryEndAccessState(
            bool(state.initialized), fences, values
        )
        _native("wgpuSharedBufferMemoryEndAccessStateFreeMembers")(state[0])
        return result

    def _release(self):
        if self._internal is not None and libf is not None:
            type(self)._release_function = _native("wgpuSharedBufferMemoryRelease")
            super()._release()


def import_shared_buffer_memory(
    device: GPUDevice,
    *,
    label: str = "",
    d3d12_resource=None,
    windows_handle=None,
    size=None,
    host_memory=None,
) -> GPUSharedBufferMemory:
    """Import memory that another API or process owns as a
    :class:`GPUSharedBufferMemory` (Windows, D3D12).

    Arguments:
        device (GPUDevice): The device, created with the feature for this kind.
        label (str): A human-readable label. Optional.
        d3d12_resource (int): An ``ID3D12Resource *`` buffer, made on the
            device's own ``ID3D12Device`` (:func:`get_d3d12_device`). Feature
            ``shared-buffer-memory-d-3d12-resource``.
        windows_handle (int): The ``HANDLE`` of shared memory (a file mapping),
            with its ``size``. Feature
            ``shared-buffer-memory-from-windows-handle`` (integrated GPUs).
        host_memory: Writable memory (buffer protocol) of this process, e.g. of
            :func:`allocate_host_memory`; it is kept alive until Dawn has
            let go of it. Feature ``shared-buffer-memory-host-pointer``
            (integrated GPUs).

    Exactly one source must be given.
    """
    if sum(x is not None for x in (d3d12_resource, windows_handle, host_memory)) != 1:
        raise TypeError(
            "Give exactly one of d3d12_resource, windows_handle and host_memory"
        )
    if d3d12_resource is not None:
        id = _native("wgpu_dawn_import_d3d12_buffer")(
            device._internal,
            ffi.cast("void *", int(d3d12_resource)),
            ffi.new("char[]", label.encode()),
        )
        if id == ffi.NULL:
            raise RuntimeError("Importing the D3D12 resource failed (not on Windows?)")
        return GPUSharedBufferMemory(label, id, device)
    if windows_handle is not None:
        if size is None:
            raise TypeError("windows_handle needs a size")
        chained = new_struct_p(
            "WGPUSharedBufferMemoryFromWindowsHandleDescriptor *",
            handle=ffi.cast("void *", int(windows_handle)),
            size=int(size),
        )
        chained.chain.sType = (
            lib.WGPUSType_SharedBufferMemoryFromWindowsHandleDescriptor
        )
    else:
        m, address = get_memoryview_and_address(host_memory)
        if m.readonly:
            raise ValueError("The memory must be writable")
        # The callback holds the memory until Dawn calls it
        userdata = callbacks.register(lambda status, _keep=(host_memory, m): None)
        chained = new_struct_p(
            "WGPUSharedBufferMemoryHostPointerDescriptor *",
            pointer=ffi.cast("void *", address),
            size=m.nbytes,
            disposeCallbackInfo=new_struct_p(
                "WGPUDisposeCallbackInfo *",
                mode=CALLBACK_MODE,
                callback=lib._wgpu_dawn_native_WGPUDisposeCallback,
                userdata1=userdata,
            )[0],
        )
        chained.chain.sType = lib.WGPUSType_SharedBufferMemoryHostPointerDescriptor
    struct = new_struct_p(
        "WGPUSharedBufferMemoryDescriptor *",
        nextInChain=ffi.cast("WGPUChainedStruct *", chained),
        label=to_c_string_view(label),
    )
    id = _native("wgpuDeviceImportSharedBufferMemory")(device._internal, struct)
    if id == ffi.NULL:
        raise RuntimeError("wgpuDeviceImportSharedBufferMemory returned NULL")
    return GPUSharedBufferMemory(label, id, device)
