"""Tests for Dawn's native extras (``wgpudawn.backends.dawn.extras``):
shared texture memory and shared fences.

The round trips need memory that another API allocates: an IOSurface on
macOS, a dmabuf from GBM on Linux. Both are made here with ctypes, and the
tests skip where the platform, the adapter or the libraries lack them.
"""

import os
import sys
import ctypes
import ctypes.util

import numpy as np
import pytest

import wgpudawn as wgpu
from wgpudawn.backends.dawn import extras
from wgpudawn.backends.dawn._mappings import enum_str2int

from testutils import can_use_wgpu_lib

IO_SURFACE = "shared-texture-memory-i-o-surface"
DMA_BUF = "shared-texture-memory-dma-buf"
MTL_SHARED_EVENT = "shared-fence-m-t-l-shared-event"
SYNC_FD = "shared-fence-sync-f-d"
OPAQUE_FD = "shared-fence-vk-semaphore-opaque-f-d"

WIDTH, HEIGHT = 64, 32
CLEAR = (0.0, 0.0, 1.0, 1.0)  # blue: B=255, G=0, R=0, A=255 in BGRA memory


def test_feature_names_are_known():
    names = enum_str2int["FeatureName"]
    for name in (IO_SURFACE, DMA_BUF, MTL_SHARED_EVENT, SYNC_FD, OPAQUE_FD):
        assert name in names
        assert names[name] >= 0x00050000  # Dawn's range, not WebGPU's


def test_arguments_are_checked():
    with pytest.raises(TypeError):
        extras.import_shared_texture_memory(None)
    with pytest.raises(TypeError):
        extras.import_shared_texture_memory(None, io_surface=1, dma_buf={})
    with pytest.raises(TypeError):
        extras.import_shared_fence(None)
    with pytest.raises(TypeError):
        extras.import_shared_fence(None, sync_fd=1, mtl_shared_event=2)


def _device_with(*features):
    """A device with these features, or skip when the adapter lacks them."""
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    missing = [f for f in features if f not in adapter.features]
    if missing:
        pytest.skip(f"Adapter lacks {missing}")
    return adapter.request_device_sync(required_features=list(features))


def _clear_to(device, texture, color):
    encoder = device.create_command_encoder()
    rpass = encoder.begin_render_pass(
        color_attachments=[
            {
                "view": texture.create_view(),
                "load_op": "clear",
                "store_op": "store",
                "clear_value": color,
            }
        ]
    )
    rpass.end()
    device.queue.submit([encoder.finish()])


# --- macOS: IOSurface and MTLSharedEvent ------------------------------------


class _IOSurface:
    """An IOSurface made with ctypes (BGRA), readable from the CPU."""

    def __init__(self, width, height):
        self.cf = cf = ctypes.CDLL(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )
        self.ios = ios = ctypes.CDLL(
            "/System/Library/Frameworks/IOSurface.framework/IOSurface"
        )
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_uint32,
        ]
        cf.CFNumberCreate.restype = ctypes.c_void_p
        cf.CFNumberCreate.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        cf.CFDictionaryCreate.restype = ctypes.c_void_p
        cf.CFDictionaryCreate.argtypes = [ctypes.c_void_p] * 3 + [
            ctypes.c_long,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        ios.IOSurfaceCreate.restype = ctypes.c_void_p
        ios.IOSurfaceCreate.argtypes = [ctypes.c_void_p]
        for name in ("IOSurfaceGetBaseAddress",):
            getattr(ios, name).restype = ctypes.c_void_p
            getattr(ios, name).argtypes = [ctypes.c_void_p]
        for name in ("IOSurfaceGetBytesPerRow", "IOSurfaceGetAllocSize"):
            getattr(ios, name).restype = ctypes.c_size_t
            getattr(ios, name).argtypes = [ctypes.c_void_p]
        for name in ("IOSurfaceLock", "IOSurfaceUnlock"):
            getattr(ios, name).restype = ctypes.c_int
            getattr(ios, name).argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                ctypes.c_void_p,
            ]
        utf8 = 0x08000100
        sint32 = 3
        key_callbacks = ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryKeyCallBacks")
        value_callbacks = ctypes.c_void_p.in_dll(cf, "kCFTypeDictionaryValueCallBacks")
        bgra = (ord("B") << 24) | (ord("G") << 16) | (ord("R") << 8) | ord("A")
        items = {
            b"IOSurfaceWidth": width,
            b"IOSurfaceHeight": height,
            b"IOSurfaceBytesPerElement": 4,
            b"IOSurfacePixelFormat": bgra,
        }
        keys = (ctypes.c_void_p * len(items))()
        values = (ctypes.c_void_p * len(items))()
        self._numbers = []
        for i, (key, value) in enumerate(items.items()):
            keys[i] = cf.CFStringCreateWithCString(None, key, utf8)
            number = ctypes.c_int32(value)
            self._numbers.append(number)
            values[i] = cf.CFNumberCreate(None, sint32, ctypes.byref(number))
        props = cf.CFDictionaryCreate(
            None,
            keys,
            values,
            len(items),
            ctypes.addressof(key_callbacks),
            ctypes.addressof(value_callbacks),
        )
        self.ref = ios.IOSurfaceCreate(props)
        assert self.ref, "IOSurfaceCreate failed"
        self.width, self.height = width, height

    def pixels(self):
        ios = self.ios
        ios.IOSurfaceLock(self.ref, 1, None)  # read only
        try:
            stride = ios.IOSurfaceGetBytesPerRow(self.ref)
            buf = (ctypes.c_uint8 * ios.IOSurfaceGetAllocSize(self.ref)).from_address(
                ios.IOSurfaceGetBaseAddress(self.ref)
            )
            data = np.frombuffer(buf, np.uint8)[: stride * self.height].reshape(
                self.height, stride
            )
            return data[:, : self.width * 4].reshape(self.height, self.width, 4).copy()
        finally:
            ios.IOSurfaceUnlock(self.ref, 1, None)


def _mtl_shared_event_value(pointer):
    objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    send = objc.objc_msgSend
    send.restype = ctypes.c_uint64
    send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    return send(pointer, objc.sel_registerName(b"signaledValue"))


@pytest.mark.skipif(sys.platform != "darwin", reason="IOSurface is macOS")
def test_io_surface_round_trip():
    device = _device_with(IO_SURFACE, MTL_SHARED_EVENT)
    surface = _IOSurface(WIDTH, HEIGHT)

    memory = extras.import_shared_texture_memory(
        device, io_surface=surface.ref, label="ios"
    )
    props = memory.properties
    assert props["size"] == (WIDTH, HEIGHT, 1)
    assert props["format"] == "bgra8unorm"
    assert props["usage"] & wgpu.TextureUsage.RENDER_ATTACHMENT
    assert not memory.is_device_lost()

    texture = memory.create_texture(view_formats=["bgra8unorm-srgb"])
    assert texture.size == (WIDTH, HEIGHT, 1)
    assert texture.format == "bgra8unorm"
    # The listed view format is allowed, so an sRGB view can be made
    texture.create_view(format="bgra8unorm-srgb")

    memory.begin_access(texture, initialized=False)
    _clear_to(device, texture, CLEAR)
    state = memory.end_access(texture)
    assert state.initialized
    # One fence per submission; clearing uninitialized memory may be its own
    assert len(state.fences) == len(state.signaled_values) >= 1
    # Metal tells when it has scheduled the work (before the fences signal)
    assert state._commands_scheduled
    assert state.wait_for_commands_scheduled(timeout=10)

    # Wait for the GPU through the events, then the pixels are there
    for fence, value in zip(state.fences, state.signaled_values, strict=True):
        assert fence.type == "mtl-shared-event"
        info = fence.export()
        assert info["type"] == "mtl-shared-event"
        assert info["shared_event"]
        for _ in range(10_000):
            if _mtl_shared_event_value(info["shared_event"]) >= value:
                break
        assert _mtl_shared_event_value(info["shared_event"]) >= value
    pixels = surface.pixels()
    assert pixels[0, 0].tolist() == [255, 0, 0, 255]  # B, G, R, A
    assert pixels[-1, -1].tolist() == [255, 0, 0, 255]

    # The exported event can come back as a fence to wait for
    imported = extras.import_shared_fence(device, mtl_shared_event=info["shared_event"])
    assert imported.type == "mtl-shared-event"
    memory.begin_access(
        texture, initialized=True, fences=[imported], signaled_values=[value]
    )
    _clear_to(device, texture, (0.0, 1.0, 0.0, 1.0))
    state2 = memory.end_access(texture)
    assert state2.signaled_values[-1] > value
    device.queue.on_submitted_work_done_sync()
    assert surface.pixels()[0, 0].tolist() == [0, 255, 0, 255]


# --- Linux: dmabuf from GBM, sync fd ----------------------------------------


def _fourcc(code):
    return sum(ord(c) << (8 * i) for i, c in enumerate(code))


class _GbmBuffer:
    """A linear dmabuf from GBM on the render node of the adapter (a machine
    with several GPUs has several), ARGB8888 by default."""

    def __init__(self, adapter, width, height, drm_format="AR24", bpp=4):
        drm = extras.get_adapter_properties(adapter).get("drm") or {}
        node = drm.get("render_node")
        if not node:
            pytest.skip("The adapter has no render node")
        for name in (
            "/usr/lib/x86_64-linux-gnu/libgbm.so.1",
            "/usr/lib64/libgbm.so.1",
            ctypes.util.find_library("gbm"),
        ):
            if name and os.path.exists(name):
                self.gbm = gbm = ctypes.CDLL(name)
                break
        else:
            pytest.skip("No libgbm")
        gbm.gbm_create_device.restype = ctypes.c_void_p
        gbm.gbm_create_device.argtypes = [ctypes.c_int]
        gbm.gbm_bo_create.restype = ctypes.c_void_p
        gbm.gbm_bo_create.argtypes = [ctypes.c_void_p] + [ctypes.c_uint32] * 4
        gbm.gbm_bo_get_fd.restype = ctypes.c_int
        gbm.gbm_bo_get_fd.argtypes = [ctypes.c_void_p]
        gbm.gbm_bo_get_stride.restype = ctypes.c_uint32
        gbm.gbm_bo_get_stride.argtypes = [ctypes.c_void_p]
        gbm.gbm_bo_get_modifier.restype = ctypes.c_uint64
        gbm.gbm_bo_get_modifier.argtypes = [ctypes.c_void_p]
        gbm.gbm_bo_map.restype = ctypes.c_void_p
        gbm.gbm_bo_map.argtypes = (
            [ctypes.c_void_p]
            + [ctypes.c_uint32] * 5
            + [ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p)]
        )
        gbm.gbm_bo_unmap.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.fd = os.open(node, os.O_RDWR | os.O_CLOEXEC)
        self.dev = gbm.gbm_create_device(self.fd)
        if not self.dev:
            pytest.skip("gbm_create_device failed")
        self.drm_format = _fourcc(drm_format)
        self.bpp = bpp
        self.bo = gbm.gbm_bo_create(
            self.dev, width, height, self.drm_format, (1 << 2) | (1 << 4)
        )  # rendering, linear
        if not self.bo:  # e.g. R8 is not renderable everywhere
            self.bo = gbm.gbm_bo_create(
                self.dev, width, height, self.drm_format, 1 << 4
            )
        if not self.bo:
            pytest.skip("gbm_bo_create failed")
        self.buffer_fd = gbm.gbm_bo_get_fd(self.bo)
        self.stride = gbm.gbm_bo_get_stride(self.bo)
        self.modifier = gbm.gbm_bo_get_modifier(self.bo)
        self.width, self.height = width, height

    def _map(self, flags):
        stride = ctypes.c_uint32(0)
        data = ctypes.c_void_p(None)
        p = self.gbm.gbm_bo_map(
            self.bo,
            0,
            0,
            self.width,
            self.height,
            flags,
            ctypes.byref(stride),
            ctypes.byref(data),
        )
        assert p, "gbm_bo_map failed"
        buf = (ctypes.c_uint8 * (stride.value * self.height)).from_address(p)
        rows = np.frombuffer(buf, np.uint8).reshape(self.height, stride.value)
        return rows[:, : self.width * self.bpp], data

    def write(self, data):
        """Write rows of bytes (height, width * bpp) through the CPU. (A plain
        mmap of the dmabuf is not coherent with the GPU everywhere.)"""
        rows, handle = self._map(2)  # GBM_BO_TRANSFER_WRITE
        try:
            rows[:] = data
        finally:
            self.gbm.gbm_bo_unmap(self.bo, handle)

    def pixels(self):
        stride = ctypes.c_uint32(0)
        data = ctypes.c_void_p(None)
        p = self.gbm.gbm_bo_map(
            self.bo,
            0,
            0,
            self.width,
            self.height,
            1,
            ctypes.byref(stride),
            ctypes.byref(data),
        )
        assert p, "gbm_bo_map failed"
        try:
            buf = (ctypes.c_uint8 * (stride.value * self.height)).from_address(p)
            arr = np.frombuffer(buf, np.uint8).reshape(self.height, stride.value)
            return arr[:, : self.width * 4].reshape(self.height, self.width, 4).copy()
        finally:
            self.gbm.gbm_bo_unmap(self.bo, data)

    def close(self):
        self.gbm.gbm_bo_destroy.argtypes = [ctypes.c_void_p]
        self.gbm.gbm_device_destroy.argtypes = [ctypes.c_void_p]
        self.gbm.gbm_bo_destroy(self.bo)
        self.gbm.gbm_device_destroy(self.dev)
        os.close(self.buffer_fd)
        os.close(self.fd)


def _dma_buf_adapter(needed, drm_format="AR24", bpp=4):
    """The first adapter (in Dawn's order) with these features on whose
    render node GBM can make a buffer of this format: not every GPU has a
    GBM backend (NVIDIA's is a separate package)."""
    for adapter in wgpu.gpu.enumerate_adapters_sync():
        if not all(f in adapter.features for f in needed):
            continue
        try:
            _GbmBuffer(adapter, 16, 16, drm_format, bpp).close()
        except pytest.skip.Exception:
            continue
        return adapter
    pytest.skip(f"No adapter with {needed} and a working GBM")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="dmabuf is Linux")
def test_dma_buf_round_trip():
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    adapter = _dma_buf_adapter([DMA_BUF])
    # Dawn's Vulkan device takes at most one kind of fence
    fence_feature = next(
        (f for f in (SYNC_FD, OPAQUE_FD) if f in adapter.features), None
    )
    device = adapter.request_device_sync(
        required_features=[DMA_BUF] + ([fence_feature] if fence_feature else [])
    )
    buffer = _GbmBuffer(adapter, WIDTH, HEIGHT)

    memory = extras.import_shared_texture_memory(
        device,
        dma_buf={
            "size": (WIDTH, HEIGHT),
            "drm_format": buffer.drm_format,
            "drm_modifier": buffer.modifier,
            "planes": [{"fd": buffer.buffer_fd, "offset": 0, "stride": buffer.stride}],
        },
    )
    props = memory.properties
    assert props["size"] == (WIDTH, HEIGHT, 1)
    assert props["format"] == "bgra8unorm"

    # Storage binding, which the Vulkan import may report, has no sRGB view
    usage = props["usage"] & ~wgpu.TextureUsage.STORAGE_BINDING
    texture = memory.create_texture(usage=usage, view_formats=["bgra8unorm-srgb"])
    texture.create_view(format="bgra8unorm-srgb")

    memory.begin_access(texture, initialized=False)
    _clear_to(device, texture, CLEAR)
    state = memory.end_access(texture)
    assert state.initialized
    assert len(state.vk_image_layout) == 2  # what Dawn left the image in
    assert state.wait_for_commands_scheduled(timeout=0)  # nothing to wait for
    # The D3D options are refused before Dawn sees them: a rejected access
    # would still hold the memory
    for option in ({"requires_end_access_fence": False}, {"is_swapchain": True}):
        with pytest.raises(ValueError):
            memory.begin_access(texture, **option)

    if fence_feature:
        # One fence per submission; clearing uninitialized memory may be its own
        assert len(state.fences) == len(state.signaled_values) >= 1
        for fence in state.fences:
            info = fence.export()
            assert info["type"] == fence.type
            assert info["fd"] >= 0
            if info["type"] == "sync-fd":
                import select

                poller = select.poll()
                poller.register(info["fd"], select.POLLIN)
                ready = poller.poll(5000)  # [(fd, revents)]; a closed fd is POLLNVAL
                assert ready and ready[0][1] & select.POLLIN, (
                    f"sync fd not signalled: {ready}"
                )
            else:
                device.queue.on_submitted_work_done_sync()
    else:
        device.queue.on_submitted_work_done_sync()
    pixels = buffer.pixels()
    assert pixels[0, 0].tolist() == [255, 0, 0, 255]  # B, G, R, A
    assert pixels[-1, -1].tolist() == [255, 0, 0, 255]

    # A second access continues from the layout the first one left, by default
    memory.begin_access(texture, initialized=True)
    _clear_to(device, texture, (0.0, 1.0, 0.0, 1.0))
    memory.end_access(texture)
    device.queue.on_submitted_work_done_sync()
    assert buffer.pixels()[0, 0].tolist() == [0, 255, 0, 255]


if __name__ == "__main__":
    from testutils import run_tests

    run_tests(globals())


# --- Linux: Vulkan memory exported as an opaque fd ---------------------------

OPAQUE_FD_MEMORY = "shared-texture-memory-opaque-f-d"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="opaque fds are Linux")
def test_opaque_fd_round_trip():
    # Another Vulkan device (on the same GPU) makes an image on exportable
    # memory; Dawn imports it, renders into it, and Vulkan reads the pixels;
    # then Vulkan writes, and Dawn reads.
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    if OPAQUE_FD_MEMORY not in adapter.features:
        pytest.skip(f"Adapter lacks {OPAQUE_FD_MEMORY}")
    # Ending an access exports a fence: one kind is needed (at most one on Vulkan)
    fence_feature = next(
        (f for f in (OPAQUE_FD, SYNC_FD) if f in adapter.features), None
    )
    if fence_feature is None:
        pytest.skip("Adapter lacks a fence kind")
    device = adapter.request_device_sync(
        required_features=[OPAQUE_FD_MEMORY, fence_feature]
    )
    import vkutils

    vk = vkutils.VulkanDevice(device, adapter)
    try:
        image = vk.create_exported_image(WIDTH, HEIGHT)
    except RuntimeError as err:
        vk.close()
        pytest.skip(str(err))
    try:
        memory = extras.import_shared_texture_memory(
            device,
            opaque_fd={
                "fd": image["fd"],
                "vk_image_create_info": ctypes.addressof(image["_create_info"]),
                "memory_type_index": image["memory_type_index"],
                "allocation_size": image["size"],
                "dedicated_allocation": True,
            },
        )
        props = memory.properties
        assert props["format"] == "rgba8unorm"
        assert props["size"] == (WIDTH, HEIGHT, 1)
        texture = memory.create_texture()

        # Dawn writes, Vulkan reads
        memory.begin_access(texture, initialized=False)
        _clear_to(device, texture, (1.0, 0.0, 0.0, 1.0))
        state = memory.end_access(texture)
        assert state.initialized
        assert state.vk_image_layout is not None
        device.queue.on_submitted_work_done_sync()
        assert (vk.pixels(image) == [255, 0, 0, 255]).all()

        # Vulkan writes, Dawn reads
        vk.fill(image, [0, 255, 0, 255])
        memory.begin_access(texture, initialized=True)
        data = device.queue.read_texture(
            {"texture": texture}, {"bytes_per_row": WIDTH * 4}, (WIDTH, HEIGHT, 1)
        )
        memory.end_access(texture)
        pixels = np.frombuffer(data, np.uint8).reshape(HEIGHT, WIDTH, 4)
        assert (pixels == [0, 255, 0, 255]).all()
        del texture, memory
    finally:
        device.queue.on_submitted_work_done_sync()
        vk.release(image)
        vk.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="opaque fds are Linux")
def test_opaque_fd_with_cuda():
    # CUDA and Dawn on the same GPU share one Vulkan image in device memory
    # (linear: CUDA sees it as rows of pitch bytes). CUDA writes, Dawn reads;
    # Dawn writes, and CUDA reads after waiting for Dawn's semaphore on the GPU.
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    import cudautils

    cuda = cudautils.load()
    if cuda is None:
        pytest.skip("No CUDA driver")
    needed = [OPAQUE_FD_MEMORY, OPAQUE_FD]
    for adapter in wgpu.gpu.enumerate_adapters_sync():
        uuids = extras.get_adapter_properties(adapter).get("vulkan_uuids")
        if not uuids or not all(f in adapter.features for f in needed):
            continue
        try:
            cu = cudautils.CudaDevice(cuda, uuids["device_uuid"])
        except LookupError:
            continue
        break
    else:
        pytest.skip("No adapter with opaque fds that is also a CUDA device")
    device = adapter.request_device_sync(required_features=needed)
    import vkutils

    vk = vkutils.VulkanDevice(device, adapter)
    image = vk.create_exported_image(WIDTH, HEIGHT, host_visible=False)
    pitch, offset = image["row_pitch"], image["offset"]
    cu_memory, pointer = cu.import_memory(vk.export_fd(image), image["size"])
    semaphore = None
    try:
        # CUDA writes, then waits on the CPU (no semaphore that way)
        pixels = np.random.default_rng(0).integers(0, 256, (HEIGHT, WIDTH, 4), np.uint8)
        rows = np.zeros((HEIGHT, pitch), np.uint8)
        rows[:, : WIDTH * 4] = pixels.reshape(HEIGHT, -1)
        cu.write(pointer + offset, rows)
        cu.synchronize()

        memory = extras.import_shared_texture_memory(
            device,
            opaque_fd={
                "fd": image["fd"],
                "vk_image_create_info": ctypes.addressof(image["_create_info"]),
                "memory_type_index": image["memory_type_index"],
                "allocation_size": image["size"],
                "dedicated_allocation": True,
            },
        )
        image["fd"] = -1  # Dawn owns it now
        texture = memory.create_texture()
        # The image holds data in no layout that Vulkan tracked: GENERAL
        layout = (vkutils.VK_IMAGE_LAYOUT_GENERAL,) * 2
        memory.begin_access(texture, initialized=True, vk_image_layout=layout)
        data = device.queue.read_texture(
            {"texture": texture}, {"bytes_per_row": WIDTH * 4}, (WIDTH, HEIGHT, 1)
        )
        assert (np.frombuffer(data, np.uint8).reshape(HEIGHT, WIDTH, 4) == pixels).all()

        # Dawn writes; CUDA's stream waits on the GPU for Dawn's semaphore
        _clear_to(device, texture, (1.0, 0.0, 0.0, 1.0))
        state = memory.end_access(texture)
        assert [f.type for f in state.fences] == ["vk-semaphore-opaque-fd"]
        semaphore = cu.import_semaphore(os.dup(state.fences[0].export()["fd"]))
        cu.wait(semaphore)
        cu.read(pointer + offset, rows)
        cu.synchronize()
        assert (
            rows[:, : WIDTH * 4].reshape(HEIGHT, WIDTH, 4) == [255, 0, 0, 255]
        ).all()
        del texture, memory
    finally:
        device.queue.on_submitted_work_done_sync()
        if semaphore is not None:
            cu.cuda.cuDestroyExternalSemaphore(semaphore)
        cu.free(cu_memory, pointer)
        vk.release(image)
        vk.close()
        cu.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="dmabuf is Linux")
def test_dma_buf_nv12_to_rgb():
    # A video frame as a camera or decoder would give it: NV12 in a dmabuf
    # that another API wrote (here GBM: an R8 buffer of 1.5 times the height,
    # described as the two planes). Dawn imports it, and an external texture
    # converts it to RGB.
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    needed = [DMA_BUF, "dawn-multi-planar-formats"]
    adapter = _dma_buf_adapter(needed, drm_format="R8  ", bpp=1)
    fence_feature = next(
        (f for f in (SYNC_FD, OPAQUE_FD) if f in adapter.features), None
    )
    device = adapter.request_device_sync(
        required_features=needed + ([fence_feature] if fence_feature else [])
    )
    w, h = WIDTH, HEIGHT
    buffer = _GbmBuffer(adapter, w, h * 3 // 2, drm_format="R8  ", bpp=1)
    rng = np.random.default_rng(0)
    y = rng.integers(16, 236, (h, w), np.uint8)
    uv = rng.integers(16, 241, (h // 2, w // 2, 2), np.uint8)
    buffer.write(np.concatenate([y, uv.reshape(h // 2, w)]))

    memory = extras.import_shared_texture_memory(
        device,
        dma_buf={
            "size": (w, h),
            "drm_format": _fourcc("NV12"),
            "drm_modifier": buffer.modifier,
            "planes": [
                {"fd": buffer.buffer_fd, "offset": 0, "stride": buffer.stride},
                {
                    "fd": buffer.buffer_fd,
                    "offset": buffer.stride * h,
                    "stride": buffer.stride,
                },
            ],
        },
    )
    assert memory.properties["format"] == "r8bg8-biplanar-420-unorm"
    texture = memory.create_texture()
    memory.begin_access(texture, initialized=True)
    external = extras.create_external_texture(
        device,
        texture.create_view(aspect="plane0-only"),
        texture.create_view(aspect="plane1-only"),
        color_space="bt709",
    )
    shader = device.create_shader_module(
        code="""
        @group(0) @binding(0) var t: texture_external;
        @group(0) @binding(1) var<storage, read_write> out: array<vec4f>;
        @compute @workgroup_size(1) fn main(@builtin(global_invocation_id) i: vec3u) {
            out[i.y * textureDimensions(t).x + i.x] = textureLoad(t, i.xy);
        }
        """
    )
    layout = device.create_bind_group_layout(
        entries=[
            {"binding": 0, "visibility": "COMPUTE", "external_texture": {}},
            {"binding": 1, "visibility": "COMPUTE", "buffer": {"type": "storage"}},
        ]
    )
    pipeline = device.create_compute_pipeline(
        layout=device.create_pipeline_layout(bind_group_layouts=[layout]),
        compute={"module": shader, "entry_point": "main"},
    )
    out = device.create_buffer(size=w * h * 16, usage="STORAGE|COPY_SRC")
    bind_group = device.create_bind_group(
        layout=layout,
        entries=[
            {"binding": 0, "resource": external},
            {"binding": 1, "resource": {"buffer": out}},
        ],
    )
    encoder = device.create_command_encoder()
    cpass = encoder.begin_compute_pass()
    cpass.set_pipeline(pipeline)
    cpass.set_bind_group(0, bind_group)
    cpass.dispatch_workgroups(w, h)
    cpass.end()
    device.queue.submit([encoder.finish()])
    memory.end_access(texture)
    rgb = np.frombuffer(device.queue.read_buffer(out), np.float32)
    rgb = rgb.reshape(h, w, 4)[..., :3]

    m = np.array(extras.get_yuv_to_rgb_matrix("bt709")).reshape(3, 4)
    full_uv = np.repeat(np.repeat(uv / 255, 2, 0), 2, 1)
    yuv = np.concatenate([y[..., None] / 255, full_uv, np.ones((h, w, 1))], -1)
    assert np.abs(rgb - yuv @ m.T).max() < 1e-3


# --- Windows: D3D11 textures shared as NT handles ----------------------------

DXGI_MEMORY = "shared-texture-memory-d-x-g-i-shared-handle"
DXGI_FENCE = "shared-fence-d-x-g-i-shared-handle"


@pytest.mark.skipif(sys.platform != "win32", reason="DXGI is Windows")
def test_dxgi_shared_handle_round_trip():
    # D3D11, on Dawn's own DXGI adapter, makes a green texture and shares it
    # as an NT handle; Dawn reads green, clears it red, and D3D11 reads red.
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    if adapter.info["backend_type"] not in ("D3D12", "D3D11"):
        pytest.skip("Not a D3D adapter")
    features = [f for f in (DXGI_MEMORY, DXGI_FENCE) if f in adapter.features]
    if DXGI_MEMORY not in features:
        pytest.skip(f"Adapter lacks {DXGI_MEMORY}")
    dxgi_adapter = extras.get_dxgi_adapter(adapter)
    assert dxgi_adapter
    device = adapter.request_device_sync(required_features=features)
    if adapter.info["backend_type"] == "D3D12":
        assert extras.get_d3d12_device(device)
        assert extras.get_d3d12_command_queue(device)
    else:
        assert extras.get_d3d11_device(device)
    import d3dutils

    d3d = d3dutils.D3D11Device(dxgi_adapter)
    green = np.zeros((HEIGHT, WIDTH, 4), np.uint8)
    green[...] = [0, 255, 0, 255]
    texture11, handle = d3d.create_shared_texture(green)
    try:
        memory = extras.import_shared_texture_memory(device, dxgi_shared_handle=handle)
        assert memory.properties["format"] == "rgba8unorm"
        assert memory.properties["size"] == (WIDTH, HEIGHT, 1)
        texture = memory.create_texture()

        memory.begin_access(texture, initialized=True)
        data = device.queue.read_texture(
            {"texture": texture}, {"bytes_per_row": WIDTH * 4}, (WIDTH, HEIGHT, 1)
        )
        assert (np.frombuffer(data, np.uint8).reshape(HEIGHT, WIDTH, 4) == green).all()
        _clear_to(device, texture, (1.0, 0.0, 0.0, 1.0))
        state = memory.end_access(texture)
        for fence in state.fences:
            info = fence.export()
            assert info["type"] == "dxgi-shared-handle" and info["handle"]
        device.queue.on_submitted_work_done_sync()
        assert (d3d.pixels(texture11, WIDTH, HEIGHT) == [255, 0, 0, 255]).all()

        if state.fences:
            # The exported fence goes back in as a fence of "another API"
            info = state.fences[0].export()
            fence = extras.import_shared_fence(
                device, dxgi_shared_handle=info["handle"]
            )
            assert fence.type == "dxgi-shared-handle"
            memory.begin_access(
                texture, fences=[fence], signaled_values=state.signaled_values[:1]
            )
            memory.end_access(texture)

        # The options of each D3D backend: D3D11 may skip the fence at the end
        # of the access, D3D12 may treat the texture as a swapchain buffer
        if adapter.info["backend_type"] == "D3D11":
            memory.begin_access(texture, requires_end_access_fence=False)
        else:
            memory.begin_access(texture, is_swapchain=True)
        _clear_to(device, texture, (0.0, 0.0, 1.0, 1.0))
        memory.end_access(texture)
        device.queue.on_submitted_work_done_sync()
        assert (d3d.pixels(texture11, WIDTH, HEIGHT) == [0, 0, 255, 255]).all()
        del texture, memory
    finally:
        device.queue.on_submitted_work_done_sync()
        d3d.close_handle(handle)
        d3dutils.release(texture11)
        d3d.close()


@pytest.mark.skipif(sys.platform != "win32", reason="D3D12 is Windows")
def test_shared_buffer_memory_of_host_memory():
    # Integrated GPUs (and WARP) on D3D12: memory of this process as a buffer
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    feature = "shared-buffer-memory-host-pointer"
    if feature not in adapter.features:
        pytest.skip(f"Adapter lacks {feature}")
    device = adapter.request_device_sync(required_features=[feature])
    import mmap

    pages = mmap.mmap(-1, 65536)
    host = memoryview(pages)
    array = np.frombuffer(host, np.uint32)
    array[:] = np.arange(array.size)
    memory = extras.import_shared_buffer_memory(device, host_memory=host)
    assert memory.properties["size"] == 65536
    buffer = memory.create_buffer()
    memory.begin_access(buffer, initialized=True)
    data = device.queue.read_buffer(buffer)
    memory.end_access(buffer)
    assert (np.frombuffer(data, np.uint32) == np.arange(array.size)).all()
