"""Dawn's native extras: shared texture memory and shared fences.

These are Dawn features outside the WebGPU API (so wgpu-py has no equivalent):
textures in memory that another API or process owns, and the GPU
synchronization objects that go with them. Native builds only; the Pyodide
build has none of it.

An adapter that supports a kind lists it in ``adapter.features``, by the
kebab-case of Dawn's ``WGPUFeatureName`` member:
``shared-texture-memory-i-o-surface`` (macOS, an IOSurface),
``shared-texture-memory-dma-buf`` (Linux, a dmabuf), and for the fences
``shared-fence-m-t-l-shared-event`` (an MTLSharedEvent), ``shared-fence-sync-f-d``
(a sync file) and ``shared-fence-vk-semaphore-opaque-f-d`` (a Vulkan semaphore
as an opaque fd). These are not WebGPU features, so ask for them in the
``required_features`` of ``adapter.request_device_sync()``, or in the
``preferred_features`` of ``wgpudawn.preconfigure_default_device()``.

Importing memory and rendering into it::

    from wgpudawn.backends.dawn import extras

    memory = extras.import_shared_texture_memory(device, io_surface=surface_ptr)
    texture = memory.create_texture(view_formats=["bgra8unorm-srgb"])
    memory.begin_access(texture, initialized=False)
    ...  # encode and submit work that uses the texture
    state = memory.end_access(texture)
    for fence, value in zip(state.fences, state.signaled_values):
        info = fence.export()  # {"type": "mtl-shared-event", "shared_event": <ptr>}
        ...  # wait until the event's signaledValue reaches value

On Linux the dmabuf is described by its planes; the Vulkan image layout that
Dawn needs on each access is tracked by the memory (``vk_image_layout`` of
``begin_access`` overrides it). A fence of another API is imported with
:func:`import_shared_fence` and passed to ``begin_access`` to wait for that
work first.
"""

from dataclasses import dataclass, field

from ..._coreutils import str_flag_to_int
from ... import flags
from ._api import (
    GPUObjectBase,
    GPUTexture,
    enum_int2str,
    enummap,
    ffi,
    lib,
    libf,
    new_struct_p,
    to_c_string_view,
)
from ._extras_util import _native, _check_status
from ._extras_device import (
    all_toggles,
    feature_info,
    get_memory_usage,
    get_toggles,
    get_vk_instance,
    get_vk_instance_proc_addr,
    perform_idle_tasks,
    reduce_memory_usage,
    request_device,
    request_device_sync,
    set_instance_extras,
)
from ._extras_adapter import get_adapter_properties, get_format_capabilities
from ._extras_memory import (
    allocate_host_memory,
    create_buffer_from_host_memory,
    get_host_memory_alignment,
    process_events,
)
from ._extras_draw import (
    multi_draw_indexed_indirect,
    multi_draw_indexed_indirect_count,
    multi_draw_indirect,
    multi_draw_indirect_count,
    write_timestamp,
)

__all__ = [
    "GPUSharedFence",
    "GPUSharedTextureMemory",
    "SharedTextureMemoryEndAccessState",
    "all_toggles",
    "allocate_host_memory",
    "create_buffer_from_host_memory",
    "feature_info",
    "get_adapter_properties",
    "get_format_capabilities",
    "get_host_memory_alignment",
    "get_memory_usage",
    "get_toggles",
    "get_vk_instance",
    "get_vk_instance_proc_addr",
    "import_shared_fence",
    "import_shared_texture_memory",
    "multi_draw_indexed_indirect",
    "multi_draw_indexed_indirect_count",
    "multi_draw_indirect",
    "multi_draw_indirect_count",
    "perform_idle_tasks",
    "process_events",
    "reduce_memory_usage",
    "request_device",
    "request_device_sync",
    "set_instance_extras",
    "write_timestamp",
]


_fence_types = {
    "VkSemaphoreOpaqueFD": "vk-semaphore-opaque-fd",
    "SyncFD": "sync-fd",
    "MTLSharedEvent": "mtl-shared-event",
}


def _fence_type_name(value):
    for name, kebab in _fence_types.items():
        if getattr(lib, f"WGPUSharedFenceType_{name}", None) == value:
            return kebab
    return hex(value)


def import_shared_texture_memory(
    device,
    *,
    label="",
    io_surface=None,
    dma_buf=None,
    opaque_fd=None,
    allow_storage_binding=False,
):
    """Import externally allocated memory as a :class:`GPUSharedTextureMemory`.

    Arguments:
        device (GPUDevice): The device, created with the feature for this kind of memory.
        label (str): A human-readable label. Optional.
        io_surface (int): macOS: the ``IOSurfaceRef``, as an integer.
        dma_buf (dict): Linux: ``{"size": (width, height), "drm_format": fourcc,
            "drm_modifier": modifier, "planes": [{"fd": fd, "offset": 0, "stride": bytes}, ...]}``.
        opaque_fd (dict): Linux: memory of a Vulkan image exported as an opaque
            fd (by another Vulkan device, or CUDA): ``{"fd": fd,
            "vk_image_create_info": address, "memory_type_index": int,
            "allocation_size": int, "dedicated_allocation": bool}``, where the
            address is that of the ``VkImageCreateInfo`` of the image (with a
            ``VkExternalMemoryImageCreateInfo`` for opaque fds chained, and
            ``VK_IMAGE_USAGE_TRANSFER_DST_BIT`` in its usage): Dawn makes the
            same image on the memory. Feature ``shared-texture-memory-opaque-f-d``.
        allow_storage_binding (bool): IOSurface only: allow the ``STORAGE_BINDING``
            usage (writing from compute shaders), if the surface's format permits it.

    Exactly one of ``io_surface``, ``dma_buf`` and ``opaque_fd`` must be given.
    The memory keeps a reference to the handle (an IOSurface is retained; the
    fds are duplicated), so the caller's can be released afterwards.
    """
    if sum(x is not None for x in (io_surface, dma_buf, opaque_fd)) != 1:
        raise TypeError("Give exactly one of io_surface, dma_buf and opaque_fd")
    if io_surface is not None:
        chained = new_struct_p(
            "WGPUSharedTextureMemoryIOSurfaceDescriptor *",
            ioSurface=ffi.cast("void *", int(io_surface)),
            allowStorageBinding=bool(allow_storage_binding),
        )
        chained.chain.sType = lib.WGPUSType_SharedTextureMemoryIOSurfaceDescriptor
    elif opaque_fd is not None:
        chained = new_struct_p(
            "WGPUSharedTextureMemoryOpaqueFDDescriptor *",
            vkImageCreateInfo=ffi.cast(
                "void *", int(opaque_fd["vk_image_create_info"])
            ),
            memoryFD=int(opaque_fd["fd"]),
            memoryTypeIndex=int(opaque_fd["memory_type_index"]),
            allocationSize=int(opaque_fd["allocation_size"]),
            dedicatedAllocation=bool(opaque_fd.get("dedicated_allocation", False)),
        )
        chained.chain.sType = lib.WGPUSType_SharedTextureMemoryOpaqueFDDescriptor
    else:
        planes = ffi.new(
            "WGPUSharedTextureMemoryDmaBufPlane[]", max(len(dma_buf["planes"]), 1)
        )
        for i, plane in enumerate(dma_buf["planes"]):
            planes[i].fd = int(plane["fd"])
            planes[i].offset = int(plane.get("offset", 0))
            planes[i].stride = int(plane["stride"])
        size = tuple(dma_buf["size"]) + (1,) * (3 - len(dma_buf["size"]))
        chained = new_struct_p(
            "WGPUSharedTextureMemoryDmaBufDescriptor *",
            size=new_struct_p(
                "WGPUExtent3D *",
                width=size[0],
                height=size[1],
                depthOrArrayLayers=size[2],
            )[0],
            drmFormat=int(dma_buf["drm_format"]),
            drmModifier=int(dma_buf.get("drm_modifier", 0)),
            planeCount=len(dma_buf["planes"]),
            planes=planes,
        )
        chained.chain.sType = lib.WGPUSType_SharedTextureMemoryDmaBufDescriptor
    struct = new_struct_p(
        "WGPUSharedTextureMemoryDescriptor *",
        nextInChain=ffi.cast("WGPUChainedStruct *", chained),
        label=to_c_string_view(label),
    )
    id = _native("wgpuDeviceImportSharedTextureMemory")(device._internal, struct)
    if id == ffi.NULL:
        raise RuntimeError("wgpuDeviceImportSharedTextureMemory returned NULL")
    # Dawn's Vulkan backend tracks the image layout of each access
    vulkan = dma_buf is not None or opaque_fd is not None
    return GPUSharedTextureMemory(label, id, device, vulkan=vulkan)


def import_shared_fence(
    device,
    *,
    label="",
    mtl_shared_event=None,
    sync_fd=None,
    vk_semaphore_opaque_fd=None,
):
    """Import a synchronization object of another API as a :class:`GPUSharedFence`.

    Arguments:
        device (GPUDevice): The device, created with the feature for this kind of fence.
        label (str): A human-readable label. Optional.
        mtl_shared_event (int): macOS: the ``id<MTLSharedEvent>``, as an integer.
        sync_fd (int): Linux: a sync file descriptor.
        vk_semaphore_opaque_fd (int): Linux: a Vulkan semaphore exported as an opaque fd.

    Exactly one of the handles must be given. A fence made this way is passed
    to :meth:`GPUSharedTextureMemory.begin_access` so the GPU waits for it.
    """
    given = [
        (mtl_shared_event, "WGPUSharedFenceMTLSharedEventDescriptor", "sharedEvent"),
        (sync_fd, "WGPUSharedFenceSyncFDDescriptor", "handle"),
        (
            vk_semaphore_opaque_fd,
            "WGPUSharedFenceVkSemaphoreOpaqueFDDescriptor",
            "handle",
        ),
    ]
    given = [(value, ctype, key) for value, ctype, key in given if value is not None]
    if len(given) != 1:
        raise TypeError(
            "Give exactly one of mtl_shared_event, sync_fd and vk_semaphore_opaque_fd"
        )
    value, ctype, key = given[0]
    if key == "sharedEvent":
        chained = new_struct_p(f"{ctype} *", sharedEvent=ffi.cast("void *", int(value)))
    else:
        chained = new_struct_p(f"{ctype} *", handle=int(value))
    chained.chain.sType = getattr(lib, "WGPUSType_" + ctype[len("WGPU") :])
    struct = new_struct_p(
        "WGPUSharedFenceDescriptor *",
        nextInChain=ffi.cast("WGPUChainedStruct *", chained),
        label=to_c_string_view(label),
    )
    id = _native("wgpuDeviceImportSharedFence")(device._internal, struct)
    if id == ffi.NULL:
        raise RuntimeError("wgpuDeviceImportSharedFence returned NULL")
    return GPUSharedFence(label, id, device)


VK_IMAGE_LAYOUT_UNDEFINED = 0
VK_IMAGE_LAYOUT_GENERAL = 1


@dataclass
class SharedTextureMemoryEndAccessState:
    """What :meth:`GPUSharedTextureMemory.end_access` returns.

    ``fences`` and ``signaled_values`` go together: the GPU work on the texture
    is done when each fence has reached its value. ``vk_image_layout`` is the
    ``(old_layout, new_layout)`` of the Vulkan image for memory imported as a
    dmabuf or an opaque fd (Vulkan), ``None`` otherwise.
    """

    initialized: bool
    fences: list = field(default_factory=list)
    signaled_values: list = field(default_factory=list)
    vk_image_layout: tuple | None = None


class GPUSharedFence(GPUObjectBase):
    """A GPU synchronization object shared with another API.

    Returned by :meth:`GPUSharedTextureMemory.end_access` for the work Dawn
    submitted, or made from another API's object by :func:`import_shared_fence`.
    """

    _release_function = None  # set on first use: the native build has it

    @property
    def type(self):
        """The kind of fence: ``"mtl-shared-event"``, ``"sync-fd"`` or ``"vk-semaphore-opaque-fd"``."""
        info = new_struct_p("WGPUSharedFenceExportInfo *")
        _native("wgpuSharedFenceExportInfo")(self._internal, info)
        return _fence_type_name(info.type)

    def export(self):
        """The fence's handle, as a dict with its ``"type"``.

        ``{"type": "mtl-shared-event", "shared_event": <id<MTLSharedEvent> as int>}``,
        ``{"type": "sync-fd", "fd": <int>}`` or ``{"type": "vk-semaphore-opaque-fd", "fd": <int>}``.
        The handle stays owned by the fence: the pointer is valid while the fence
        lives (retain it to keep it longer), and an fd must be ``os.dup()``'d
        to outlive it. Waiting is done with the other API: an fd with
        ``select.poll()`` (a sync fd) or Vulkan (an opaque fd), the event with
        Metal, until ``signaledValue`` reaches the value that came with the fence.
        """
        kind = self.type
        if kind == "mtl-shared-event":
            chained = new_struct_p("WGPUSharedFenceMTLSharedEventExportInfo *")
            chained.chain.sType = lib.WGPUSType_SharedFenceMTLSharedEventExportInfo
        elif kind == "sync-fd":
            chained = new_struct_p("WGPUSharedFenceSyncFDExportInfo *")
            chained.chain.sType = lib.WGPUSType_SharedFenceSyncFDExportInfo
        elif kind == "vk-semaphore-opaque-fd":
            chained = new_struct_p("WGPUSharedFenceVkSemaphoreOpaqueFDExportInfo *")
            chained.chain.sType = lib.WGPUSType_SharedFenceVkSemaphoreOpaqueFDExportInfo
        else:
            raise RuntimeError(f"Cannot export a fence of type {kind}")
        info = new_struct_p(
            "WGPUSharedFenceExportInfo *",
            nextInChain=ffi.cast("WGPUChainedStruct *", chained),
        )
        _native("wgpuSharedFenceExportInfo")(self._internal, info)
        if kind == "mtl-shared-event":
            return {
                "type": kind,
                "shared_event": int(ffi.cast("uintptr_t", chained.sharedEvent)),
            }
        return {"type": kind, "fd": int(chained.handle)}

    def _release(self):
        if self._internal is not None and libf is not None:
            type(self)._release_function = _native("wgpuSharedFenceRelease")
            super()._release()


class GPUSharedTextureMemory(GPUObjectBase):
    """Externally allocated memory that textures can be created from.

    Made by :func:`import_shared_texture_memory`. Textures created from it
    may only be used on the queue between :meth:`begin_access` and
    :meth:`end_access`, and only one of them at a time.
    """

    _release_function = None  # set on first use: the native build has it

    def __init__(self, label, internal, device, *, vulkan=False):
        super().__init__(label, internal, device)
        # A dmabuf is Vulkan's: each access then carries the image layout,
        # which this object tracks from UNDEFINED through what EndAccess reports.
        self._vulkan = vulkan
        self._vk_image_layout = VK_IMAGE_LAYOUT_UNDEFINED
        struct = new_struct_p("WGPUSharedTextureMemoryProperties *")
        status = _native("wgpuSharedTextureMemoryGetProperties")(internal, struct)
        _check_status(status, "wgpuSharedTextureMemoryGetProperties")
        self._properties = {
            "usage": int(struct.usage),
            "size": (
                struct.size.width,
                struct.size.height,
                struct.size.depthOrArrayLayers,
            ),
            "format": enum_int2str["TextureFormat"][struct.format],
        }

    @property
    def properties(self):
        """``{"usage", "size", "format"}``: the usage a texture may have (an int
        of :class:`wgpudawn.TextureUsage` flags), its size and its format."""
        return self._properties

    def is_device_lost(self):
        """Whether the device that imported the memory has been lost."""
        return bool(_native("wgpuSharedTextureMemoryIsDeviceLost")(self._internal))

    def create_texture(self, *, label="", usage=None, view_formats=()):
        """Create a texture on the memory. It has the memory's size and format.

        Arguments:
            label (str): A human-readable label. Optional.
            usage (TextureUsageFlags): The usage, a subset of ``properties["usage"]``;
                that whole usage by default.
            view_formats (list of TextureFormat): Formats that a view may have
                besides the texture's own, e.g. its sRGB twin.
        """
        props = self._properties
        if usage is None:
            usage = props["usage"]
        elif isinstance(usage, str):
            usage = str_flag_to_int(flags.TextureUsage, usage)
        c_view_formats = ffi.NULL
        if view_formats:
            c_view_formats = ffi.new(
                "WGPUTextureFormat []",
                [enummap[f"TextureFormat.{f}"] for f in view_formats],
            )
        c_size = new_struct_p(
            "WGPUExtent3D *",
            width=props["size"][0],
            height=props["size"][1],
            depthOrArrayLayers=props["size"][2],
        )[0]
        struct = new_struct_p(
            "WGPUTextureDescriptor *",
            label=to_c_string_view(label),
            size=c_size,
            mipLevelCount=1,
            sampleCount=1,
            dimension="2d",
            format=props["format"],
            usage=int(usage),
            viewFormatCount=len(view_formats),
            viewFormats=c_view_formats,
        )
        id = _native("wgpuSharedTextureMemoryCreateTexture")(self._internal, struct)
        if id == ffi.NULL:
            raise RuntimeError("wgpuSharedTextureMemoryCreateTexture returned NULL")
        tex_info = {
            "size": props["size"],
            "mip_level_count": 1,
            "sample_count": 1,
            "dimension": "2d",
            "format": props["format"],
            "usage": int(usage),
            "texture_binding_view_dimension": None,
        }
        return GPUTexture(label, id, self._device, tex_info)

    def begin_access(
        self,
        texture,
        *,
        initialized=True,
        concurrent_read=False,
        fences=(),
        signaled_values=(),
        vk_image_layout=None,
    ):
        """Start using ``texture`` (made by :meth:`create_texture`) on the queue.

        Arguments:
            texture (GPUTexture): The texture to access.
            initialized (bool): Whether the memory holds data; if not, Dawn
                clears it before the first use.
            concurrent_read (bool): Read-only access that other users may share.
            fences (list of GPUSharedFence): Fences to wait for on the GPU before
                the texture is used, with their ``signaled_values``.
            signaled_values (list of int): The value each fence must reach.
            vk_image_layout (tuple): Memory imported as a dmabuf or opaque fd only: the
                ``(old_layout, new_layout)`` of the Vulkan image, as ``VkImageLayout``
                values. By default the layout that the last :meth:`end_access`
                reported (``UNDEFINED`` at first) to ``GENERAL``.
        """
        if len(fences) != len(signaled_values):
            raise ValueError("fences and signaled_values must have the same length")
        c_fences = ffi.new(
            "WGPUSharedFence[]", [f._internal for f in fences] or [ffi.NULL]
        )
        c_values = ffi.new("uint64_t[]", list(signaled_values) or [0])
        chained = None
        if self._vulkan and vk_image_layout is None:
            vk_image_layout = (self._vk_image_layout, VK_IMAGE_LAYOUT_GENERAL)
        if vk_image_layout is not None:
            old_layout, new_layout = vk_image_layout
            chained = new_struct_p(
                "WGPUSharedTextureMemoryVkImageLayoutBeginState *",
                oldLayout=int(old_layout),
                newLayout=int(new_layout),
            )
            chained.chain.sType = (
                lib.WGPUSType_SharedTextureMemoryVkImageLayoutBeginState
            )
        struct = new_struct_p(
            "WGPUSharedTextureMemoryBeginAccessDescriptor *",
            nextInChain=ffi.cast("WGPUChainedStruct *", chained)
            if chained
            else ffi.NULL,
            concurrentRead=bool(concurrent_read),
            initialized=bool(initialized),
            fenceCount=len(fences),
            fences=c_fences,
            signaledValueCount=len(signaled_values),
            signaledValues=c_values,
        )
        status = _native("wgpuSharedTextureMemoryBeginAccess")(
            self._internal, texture._internal, struct
        )
        _check_status(status, "wgpuSharedTextureMemoryBeginAccess")

    def end_access(self, texture):
        """Stop using ``texture`` on the queue; what to wait for is returned.

        Arguments:
            texture (GPUTexture): The texture given to :meth:`begin_access`.

        Returns a :class:`SharedTextureMemoryEndAccessState`. Its fences are
        owned by the caller (released with the objects).
        """
        chained = None
        if self._vulkan:
            chained = new_struct_p("WGPUSharedTextureMemoryVkImageLayoutEndState *")
            chained.chain.sType = lib.WGPUSType_SharedTextureMemoryVkImageLayoutEndState
        state = new_struct_p(
            "WGPUSharedTextureMemoryEndAccessState *",
            nextInChain=ffi.cast("WGPUChainedStruct *", chained)
            if chained
            else ffi.NULL,
        )
        status = _native("wgpuSharedTextureMemoryEndAccess")(
            self._internal, texture._internal, state
        )
        _check_status(status, "wgpuSharedTextureMemoryEndAccess")
        fences = []
        for i in range(state.fenceCount):
            # The state owns its fences and FreeMembers releases them: take a
            # reference for the object that outlives it.
            _native("wgpuSharedFenceAddRef")(state.fences[i])
            fences.append(GPUSharedFence("", state.fences[i], self._device))
        values = [int(state.signaledValues[i]) for i in range(state.signaledValueCount)]
        layout = None
        if chained:
            layout = (int(chained.oldLayout), int(chained.newLayout))
            self._vk_image_layout = layout[1]
        result = SharedTextureMemoryEndAccessState(
            bool(state.initialized), fences, values, layout
        )
        _native("wgpuSharedTextureMemoryEndAccessStateFreeMembers")(state[0])
        return result

    def _release(self):
        if self._internal is not None and libf is not None:
            type(self)._release_function = _native("wgpuSharedTextureMemoryRelease")
            super()._release()
