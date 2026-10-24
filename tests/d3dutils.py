"""A minimal D3D11, through ctypes and COM vtables, for the tests of Dawn's
extras on Windows: a D3D11 device on the adapter of a Dawn device, that makes
shared textures (NT handles) and reads and writes their pixels. 64-bit only.
"""

import ctypes
import uuid

import numpy as np

HRESULT = ctypes.c_long
c_u32, c_ptr = ctypes.c_uint32, ctypes.c_void_p

DXGI_FORMAT_R8G8B8A8_UNORM = 28
D3D11_BIND_SHADER_RESOURCE = 0x8
D3D11_BIND_RENDER_TARGET = 0x20
D3D11_RESOURCE_MISC_SHARED = 0x2
D3D11_RESOURCE_MISC_SHARED_NTHANDLE = 0x800
D3D11_USAGE_STAGING = 3
D3D11_CPU_ACCESS_READ = 0x20000
D3D11_MAP_READ = 1
DXGI_SHARED_RESOURCE_READ = 0x80000000
DXGI_SHARED_RESOURCE_WRITE = 1
IID_IDXGIResource1 = uuid.UUID("30961379-4609-4a41-998e-54fe567ee0c1")


class SampleDesc(ctypes.Structure):
    _fields_ = [("Count", c_u32), ("Quality", c_u32)]


class Texture2DDesc(ctypes.Structure):
    _fields_ = [
        ("Width", c_u32),
        ("Height", c_u32),
        ("MipLevels", c_u32),
        ("ArraySize", c_u32),
        ("Format", c_u32),
        ("SampleDesc", SampleDesc),
        ("Usage", c_u32),
        ("BindFlags", c_u32),
        ("CPUAccessFlags", c_u32),
        ("MiscFlags", c_u32),
    ]


class SubresourceData(ctypes.Structure):
    _fields_ = [("pSysMem", c_ptr), ("SysMemPitch", c_u32), ("SysMemSlicePitch", c_u32)]


class MappedSubresource(ctypes.Structure):
    _fields_ = [("pData", c_ptr), ("RowPitch", c_u32), ("DepthPitch", c_u32)]


def _method(obj, index, restype, *argtypes):
    """The method at ``index`` of the vtable of COM object ``obj`` (an int)."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(c_ptr)))[0]
    prototype = ctypes.WINFUNCTYPE(restype, c_ptr, *argtypes)
    function = prototype(vtable[index])
    return lambda *args: function(obj, *args)


def _check(hr, what):
    if hr < 0:
        raise RuntimeError(f"{what} failed: HRESULT 0x{hr & 0xFFFFFFFF:08x}")


def release(obj):
    if obj:
        _method(obj, 2, c_u32)()


class D3D11Device:
    """A D3D11 device on the GPU of a DXGI adapter (an ``IDXGIAdapter *``)."""

    def __init__(self, dxgi_adapter):
        d3d11 = ctypes.WinDLL("d3d11")
        create = d3d11.D3D11CreateDevice
        create.restype = HRESULT
        create.argtypes = [c_ptr, c_u32, c_ptr, c_u32, c_ptr, c_u32, c_u32]
        create.argtypes += [
            ctypes.POINTER(c_ptr),
            ctypes.POINTER(c_u32),
            ctypes.POINTER(c_ptr),
        ]
        device, context, level = c_ptr(), c_ptr(), c_u32()
        # D3D_DRIVER_TYPE_UNKNOWN (0) is required when an adapter is given
        hr = create(
            dxgi_adapter, 0, None, 0, None, 0, 7,
            ctypes.byref(device), ctypes.byref(level), ctypes.byref(context),
        )  # fmt: skip
        _check(hr, "D3D11CreateDevice")
        self.device, self.context = device.value, context.value
        self._close_handle = ctypes.WinDLL("kernel32").CloseHandle

    def _create_texture(self, desc, data=None):
        init = None
        if data is not None:
            init = SubresourceData(
                pSysMem=data.ctypes.data, SysMemPitch=data.shape[1] * 4
            )
        texture = c_ptr()
        create = _method(self.device, 5, HRESULT, c_ptr, c_ptr, ctypes.POINTER(c_ptr))
        hr = create(
            ctypes.byref(desc),
            ctypes.byref(init) if init else None,
            ctypes.byref(texture),
        )
        _check(hr, "ID3D11Device::CreateTexture2D")
        return texture.value

    def create_shared_texture(self, pixels):
        """A shared RGBA8 texture with these pixels ((h, w, 4) uint8), and an
        NT handle to it: ``(texture, handle)``."""
        h, w = pixels.shape[:2]
        desc = Texture2DDesc(
            Width=w,
            Height=h,
            MipLevels=1,
            ArraySize=1,
            Format=DXGI_FORMAT_R8G8B8A8_UNORM,
            SampleDesc=SampleDesc(1, 0),
            BindFlags=D3D11_BIND_SHADER_RESOURCE | D3D11_BIND_RENDER_TARGET,
            MiscFlags=D3D11_RESOURCE_MISC_SHARED | D3D11_RESOURCE_MISC_SHARED_NTHANDLE,
        )
        texture = self._create_texture(desc, np.ascontiguousarray(pixels))
        resource = c_ptr()
        iid = (ctypes.c_byte * 16).from_buffer_copy(IID_IDXGIResource1.bytes_le)
        query = _method(texture, 0, HRESULT, c_ptr, ctypes.POINTER(c_ptr))
        _check(query(ctypes.byref(iid), ctypes.byref(resource)), "QueryInterface")
        handle = c_ptr()
        create_handle = _method(
            resource.value, 13, HRESULT, c_ptr, c_u32, c_ptr, ctypes.POINTER(c_ptr)
        )
        access = DXGI_SHARED_RESOURCE_READ | DXGI_SHARED_RESOURCE_WRITE
        hr = create_handle(None, access, None, ctypes.byref(handle))
        release(resource.value)
        _check(hr, "IDXGIResource1::CreateSharedHandle")
        self.flush()
        return texture, handle.value

    def flush(self):
        _method(self.context, 111, None)()

    def pixels(self, texture, w, h):
        """Read the pixels of an RGBA8 texture through a staging texture."""
        desc = Texture2DDesc(
            Width=w,
            Height=h,
            MipLevels=1,
            ArraySize=1,
            Format=DXGI_FORMAT_R8G8B8A8_UNORM,
            SampleDesc=SampleDesc(1, 0),
            Usage=D3D11_USAGE_STAGING,
            CPUAccessFlags=D3D11_CPU_ACCESS_READ,
        )
        staging = self._create_texture(desc)
        try:
            _method(self.context, 47, None, c_ptr, c_ptr)(
                staging, texture
            )  # CopyResource
            mapped = MappedSubresource()
            map_ = _method(self.context, 14, HRESULT, c_ptr, c_u32, c_u32, c_u32, c_ptr)
            _check(map_(staging, 0, D3D11_MAP_READ, 0, ctypes.byref(mapped)), "Map")
            try:
                raw = (ctypes.c_uint8 * (mapped.RowPitch * h)).from_address(
                    mapped.pData
                )
                rows = np.frombuffer(raw, np.uint8).reshape(h, mapped.RowPitch)
                return rows[:, : w * 4].reshape(h, w, 4).copy()
            finally:
                _method(self.context, 15, None, c_ptr, c_u32)(staging, 0)  # Unmap
        finally:
            release(staging)

    def close_handle(self, handle):
        self._close_handle(c_ptr(handle))

    def close(self):
        release(self.context)
        release(self.device)
        self.context = self.device = None
