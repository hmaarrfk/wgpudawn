"""A minimal CUDA, through ctypes and the driver API (libcuda), for the tests
of Dawn's extras: imports memory and semaphores that Vulkan exported as opaque
fds, and copies to and from the memory. Linux only. The struct layouts are
those of cuda.h (checked with offsetof against CUDA 13).
"""

import ctypes

c_u32, c_u64, c_ptr = ctypes.c_uint32, ctypes.c_uint64, ctypes.c_void_p

CU_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD = 1
CU_EXTERNAL_SEMAPHORE_HANDLE_TYPE_OPAQUE_FD = 1
CUDA_EXTERNAL_MEMORY_DEDICATED = 1


class ExternalMemoryHandleDesc(ctypes.Structure):
    _fields_ = [
        ("type", c_u32),
        ("_pad", c_u32),
        ("fd", ctypes.c_int),  # the first member of the 16-byte handle union
        ("_handle", ctypes.c_byte * 12),
        ("size", c_u64),
        ("flags", c_u32),
        ("reserved", c_u32 * 16),
        ("_tail", c_u32),
    ]


class ExternalMemoryBufferDesc(ctypes.Structure):
    _fields_ = [
        ("offset", c_u64),
        ("size", c_u64),
        ("flags", c_u32),
        ("reserved", c_u32 * 16),
        ("_tail", c_u32),
    ]


class ExternalSemaphoreHandleDesc(ctypes.Structure):
    _fields_ = [
        ("type", c_u32),
        ("_pad", c_u32),
        ("fd", ctypes.c_int),
        ("_handle", ctypes.c_byte * 12),
        ("flags", c_u32),
        ("reserved", c_u32 * 16),
        ("_tail", c_u32),
    ]


class ExternalSemaphoreWaitParams(ctypes.Structure):
    _fields_ = [
        ("fence_value", c_u64),  # params.fence.value
        ("_params", ctypes.c_byte * 64),
        ("flags", c_u32),
        ("reserved", c_u32 * 16),
        ("_tail", c_u32),
    ]


assert ctypes.sizeof(ExternalMemoryHandleDesc) == 104
assert ctypes.sizeof(ExternalMemoryBufferDesc) == 88
assert ctypes.sizeof(ExternalSemaphoreHandleDesc) == 96
assert ctypes.sizeof(ExternalSemaphoreWaitParams) == 144


def load():
    """libcuda, initialized, or None when there is no CUDA driver."""
    try:
        cuda = ctypes.CDLL("libcuda.so.1")
    except OSError:
        return None
    if cuda.cuInit(0) != 0:
        return None
    return cuda


def _check(result, what):
    if result != 0:
        raise RuntimeError(f"{what} failed: CUresult {result}")


class CudaDevice:
    """A CUDA context on the GPU with this UUID (16 bytes, e.g. the Vulkan
    device UUID of Dawn's adapter: the same GPU)."""

    def __init__(self, cuda, uuid):
        self.cuda = cuda
        count = ctypes.c_int()
        _check(cuda.cuDeviceGetCount(ctypes.byref(count)), "cuDeviceGetCount")
        for index in range(count.value):
            device = ctypes.c_int()
            _check(cuda.cuDeviceGet(ctypes.byref(device), index), "cuDeviceGet")
            found = (ctypes.c_char * 16)()
            _check(cuda.cuDeviceGetUuid_v2(found, device), "cuDeviceGetUuid")
            if found.raw == bytes(uuid):
                break
        else:
            raise LookupError("No CUDA device with this UUID")
        self.device = device
        self.context = c_ptr()
        cuda.cuDevicePrimaryCtxRetain.argtypes = [ctypes.POINTER(c_ptr), ctypes.c_int]
        _check(
            cuda.cuDevicePrimaryCtxRetain(ctypes.byref(self.context), device),
            "cuDevicePrimaryCtxRetain",
        )
        cuda.cuCtxSetCurrent.argtypes = [c_ptr]
        _check(cuda.cuCtxSetCurrent(self.context), "cuCtxSetCurrent")
        cuda.cuMemcpyHtoD_v2.argtypes = [c_u64, c_ptr, ctypes.c_size_t]
        cuda.cuMemcpyDtoH_v2.argtypes = [c_ptr, c_u64, ctypes.c_size_t]
        cuda.cuMemFree_v2.argtypes = [c_u64]
        cuda.cuDestroyExternalMemory.argtypes = [c_ptr]
        cuda.cuDestroyExternalSemaphore.argtypes = [c_ptr]
        cuda.cuWaitExternalSemaphoresAsync.argtypes = [
            ctypes.POINTER(c_ptr),
            ctypes.POINTER(ExternalSemaphoreWaitParams),
            ctypes.c_uint,
            c_ptr,
        ]

    def import_memory(self, fd, size, dedicated=True):
        """Import Vulkan memory exported as an opaque fd (CUDA owns the fd
        after this) and map all of it: ``(external_memory, device_pointer)``."""
        desc = ExternalMemoryHandleDesc(
            type=CU_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD,
            fd=fd,
            size=size,
            flags=CUDA_EXTERNAL_MEMORY_DEDICATED if dedicated else 0,
        )
        memory = c_ptr()
        _check(
            self.cuda.cuImportExternalMemory(ctypes.byref(memory), ctypes.byref(desc)),
            "cuImportExternalMemory",
        )
        buffer = ExternalMemoryBufferDesc(offset=0, size=size)
        pointer = c_u64()
        _check(
            self.cuda.cuExternalMemoryGetMappedBuffer(
                ctypes.byref(pointer), memory, ctypes.byref(buffer)
            ),
            "cuExternalMemoryGetMappedBuffer",
        )
        return memory, pointer.value

    def import_semaphore(self, fd):
        """Import a Vulkan semaphore exported as an opaque fd (CUDA owns the
        fd after this)."""
        desc = ExternalSemaphoreHandleDesc(
            type=CU_EXTERNAL_SEMAPHORE_HANDLE_TYPE_OPAQUE_FD, fd=fd
        )
        semaphore = c_ptr()
        _check(
            self.cuda.cuImportExternalSemaphore(
                ctypes.byref(semaphore), ctypes.byref(desc)
            ),
            "cuImportExternalSemaphore",
        )
        return semaphore

    def wait(self, semaphore):
        """Make the default stream wait (on the GPU) for the semaphore."""
        params = ExternalSemaphoreWaitParams()
        _check(
            self.cuda.cuWaitExternalSemaphoresAsync(
                ctypes.byref(semaphore), ctypes.byref(params), 1, None
            ),
            "cuWaitExternalSemaphoresAsync",
        )

    def write(self, pointer, data):
        """Copy bytes (a contiguous numpy array) to device memory."""
        _check(
            self.cuda.cuMemcpyHtoD_v2(pointer, data.ctypes.data, data.nbytes),
            "cuMemcpyHtoD",
        )

    def read(self, pointer, out):
        """Copy device memory into a contiguous numpy array (on the default
        stream: after what it waits for)."""
        _check(
            self.cuda.cuMemcpyDtoH_v2(out.ctypes.data, pointer, out.nbytes),
            "cuMemcpyDtoH",
        )

    def synchronize(self):
        _check(self.cuda.cuCtxSynchronize(), "cuCtxSynchronize")

    def free(self, memory, pointer):
        self.cuda.cuMemFree_v2(pointer)
        self.cuda.cuDestroyExternalMemory(memory)

    def close(self):
        self.cuda.cuDevicePrimaryCtxRelease_v2(self.device)
