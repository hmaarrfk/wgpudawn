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


class _GbmBuffer:
    """A linear ARGB8888 dmabuf from GBM on the render node of the adapter
    (a machine with several GPUs has several)."""

    def __init__(self, adapter, width, height):
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
        self.drm_format = (
            ord("A") | (ord("R") << 8) | (ord("2") << 16) | (ord("4") << 24)
        )  # AR24
        self.bo = gbm.gbm_bo_create(
            self.dev, width, height, self.drm_format, (1 << 2) | (1 << 4)
        )  # rendering, linear
        if not self.bo:
            pytest.skip("gbm_bo_create failed")
        self.buffer_fd = gbm.gbm_bo_get_fd(self.bo)
        self.stride = gbm.gbm_bo_get_stride(self.bo)
        self.modifier = gbm.gbm_bo_get_modifier(self.bo)
        self.width, self.height = width, height

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


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="dmabuf is Linux")
def test_dma_buf_round_trip():
    if not can_use_wgpu_lib:
        pytest.skip("Needs wgpu lib")
    adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
    if DMA_BUF not in adapter.features:
        pytest.skip(f"Adapter lacks {DMA_BUF}")
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
