"""Dawn's native extras for memory that the host owns: buffers on host memory
(feature ``host-mapped-pointer``). See extras.py.
"""

from ... import enums, flags
from ..._coreutils import str_flag_to_int
from . import _api
from ._api import GPUBuffer, GPUDevice, ffi, lib, libf, new_struct_p, to_c_string_view
from ._ffi import callbacks
from ._helpers import get_memoryview_and_address


# Dawn calls this (a WGPUCallback, one userdata) when it no longer uses the
# memory of a buffer made by create_buffer_from_host_memory().
@ffi.def_extern(name="_wgpu_dawn_native_WGPUCallback")
def _dispose(userdata):
    callbacks.call(userdata)


def process_events():
    """Let Dawn run the callbacks of finished work and tick every device
    (``wgpuInstanceProcessEvents``): e.g. to release host memory of destroyed
    buffers (:func:`create_buffer_from_host_memory`) in a program that only
    uses the synchronous API, which waits on single operations."""
    _api.process_events()


def get_host_memory_alignment(device: GPUDevice):
    """The alignment, in bytes, of the address and size of host memory for
    :func:`create_buffer_from_host_memory` (e.g. 4096, a page)."""
    limits_ext = new_struct_p("WGPUDawnHostMappedPointerLimits *")
    limits_ext.chain.sType = lib.WGPUSType_DawnHostMappedPointerLimits
    limits = new_struct_p(
        "WGPULimits *", nextInChain=ffi.cast("WGPUChainedStruct *", limits_ext)
    )
    status = lib.wgpuDeviceGetLimits(device._internal, limits)
    if status != lib.WGPUStatus_Success:
        raise RuntimeError("wgpuDeviceGetLimits failed")
    return int(limits_ext.hostMappedPointerAlignment)


def allocate_host_memory(device: GPUDevice, size: int):
    """A writable ``memoryview`` of ``size`` bytes (rounded up to the
    alignment) that :func:`create_buffer_from_host_memory` can use. For a
    numpy array: ``np.frombuffer(memory, dtype)``."""
    alignment = get_host_memory_alignment(device)
    size = -(-int(size) // alignment) * alignment
    raw = bytearray(size + alignment)
    address = int(ffi.cast("uintptr_t", ffi.from_buffer(raw)))
    offset = -address % alignment
    return memoryview(raw)[offset : offset + size]


def create_buffer_from_host_memory(
    device: GPUDevice, data, *, usage, label: str = ""
) -> GPUBuffer:
    """Create a buffer whose memory is ``data``: no copy, the GPU reads and
    writes that memory itself, and the CPU sees what the GPU wrote once the
    work is done (e.g. after ``device.queue.on_submitted_work_done_sync()``).

    Arguments:
        device (GPUDevice): A device with the ``host-mapped-pointer`` feature
            (experimental in Dawn: it needs ``allow_unsafe_apis``, see
            :func:`set_instance_extras`). Vulkan (not on AMD), Metal and D3D12.
        data: Writable, contiguous memory that supports the buffer protocol (a
            numpy array, a ``bytearray``, a ``memoryview``), whose address and
            size are multiples of :func:`get_host_memory_alignment`;
            :func:`allocate_host_memory` makes such memory.
        usage (BufferUsageFlags): The usage of the buffer.
        label (str): A human-readable label. Optional.

    The buffer keeps ``data`` alive until Dawn has released the memory: after
    the buffer is destroyed (or collected), the GPU work submitted until then
    is done, and Dawn processed its events (which happens while promises are
    awaited, or with :func:`process_events`). Do not resize or reallocate the
    memory meanwhile.
    """
    m, address = get_memoryview_and_address(data)
    if m.readonly:
        raise ValueError("The memory must be writable")
    alignment = get_host_memory_alignment(device)
    if address % alignment or m.nbytes % alignment:
        raise ValueError(
            f"The address and size of the memory must be multiples of {alignment} "
            "(see allocate_host_memory())"
        )
    if isinstance(usage, str):
        usage = str_flag_to_int(flags.BufferUsage, usage)
    usage = int(usage)

    # The callback holds the memory until Dawn calls it (once, at disposal)
    userdata = callbacks.register(lambda _keep=(data, m): None)
    chained = new_struct_p(
        "WGPUBufferHostMappedPointer *",
        pointer=ffi.cast("void *", address),
        disposeCallback=lib._wgpu_dawn_native_WGPUCallback,
        userdata=userdata,
    )
    chained.chain.sType = lib.WGPUSType_BufferHostMappedPointer
    struct = new_struct_p(
        "WGPUBufferDescriptor *",
        nextInChain=ffi.cast("WGPUChainedStruct *", chained),
        label=to_c_string_view(label),
        usage=usage,
        size=m.nbytes,
        mappedAtCreation=False,
    )
    id = libf.wgpuDeviceCreateBuffer(device._internal, struct)
    return GPUBuffer(label, id, device, m.nbytes, usage, enums.BufferMapState.unmapped)
