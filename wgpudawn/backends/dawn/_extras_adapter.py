"""Dawn's native extras for adapters: what the backend says about the GPU
(driver, DRM device, memory heaps, LUID, UUIDs, subgroup matrices), and the
DRM format modifiers of a texture format. See extras.py.
"""

import os

from ._api import GPUAdapter, enummap, ffi, lib, new_struct_p
from ._extras_util import _native, _check_status


_heap_properties = {
    "DeviceLocal": "device-local",
    "HostVisible": "host-visible",
    "HostCoherent": "host-coherent",
    "HostUncached": "host-uncached",
    "HostCached": "host-cached",
}

_subgroup_matrix_types = {
    "F32": "f32",
    "F16": "f16",
    "U32": "u32",
    "I32": "i32",
    "U8": "u8",
    "I8": "i8",
}


def _get_info(adapter, ctype, stype):
    """wgpuAdapterGetInfo with one chained struct; returns it, or None when
    Dawn refuses it."""
    chained = new_struct_p(f"{ctype} *")
    chained.chain.sType = stype
    info = new_struct_p(
        "WGPUAdapterInfo *", nextInChain=ffi.cast("WGPUChainedStruct *", chained)
    )
    status = lib.wgpuAdapterGetInfo(adapter._internal, info)
    if status != lib.WGPUStatus_Success:
        return None
    lib.wgpuAdapterInfoFreeMembers(info[0])
    return chained


def _dri_node(major, minor, prefix):
    """The /dev/dri node with this device number, or None."""
    try:
        names = sorted(os.listdir("/dev/dri"))
    except OSError:
        return None
    for name in names:
        if name.startswith(prefix):
            path = os.path.join("/dev/dri", name)
            try:
                rdev = os.stat(path).st_rdev
            except OSError:
                continue
            if (os.major(rdev), os.minor(rdev)) == (major, minor):
                return path
    return None


def get_adapter_properties(adapter: GPUAdapter):
    """What the backend says about the adapter's GPU, as a dict with the keys
    that this adapter has:

    * ``"vk"``: ``{"driver_version"}``, the Vulkan driver version (feature
      ``adapter-properties-vk``);
    * ``"vulkan_uuids"``: ``{"device_uuid", "driver_uuid"}`` as 16 ``bytes``
      each (Vulkan adapters). The device UUID is the one that other APIs use
      for the same GPU: CUDA's ``cuDeviceGetUuid``, OpenGL's
      ``GL_EXT_memory_object``, Vulkan's ``VkPhysicalDeviceIDProperties``;
    * ``"drm"``: ``{"primary", "render"}``, the device numbers
      ``(major, minor)`` of the DRM nodes of the GPU, and ``"primary_node"``,
      ``"render_node"``, their paths in ``/dev/dri`` (feature
      ``adapter-properties-drm``, Linux). Memory to import as a dmabuf is
      allocated on this render node (e.g. with GBM);
    * ``"d3d"``: ``{"shader_model", "luid"}``, the LUID as an int (feature
      ``adapter-properties-d3d``, Windows);
    * ``"memory_heaps"``: a list of ``{"size", "properties"}`` (feature
      ``adapter-properties-memory-heaps``), with properties such as
      ``"device-local"`` and ``"host-visible"``;
    * ``"subgroup_matrix_configs"``: the shapes and types of subgroup
      matrices (feature ``chromium-experimental-subgroup-matrix``).
    """
    features = adapter.features
    result = {}
    if "adapter-properties-vk" in features:
        vk = _get_info(
            adapter, "WGPUAdapterPropertiesVk", lib.WGPUSType_AdapterPropertiesVk
        )
        if vk is not None:
            result["vk"] = {"driver_version": int(vk.driverVersion)}
    if adapter.info["backend_type"] == "Vulkan":
        uuids = ffi.new("uint8_t[32]")
        if _native("wgpu_dawn_vulkan_uuids")(adapter._internal, uuids):
            data = bytes(ffi.buffer(uuids))
            result["vulkan_uuids"] = {
                "device_uuid": data[:16],
                "driver_uuid": data[16:],
            }
    if "adapter-properties-drm" in features:
        drm = _get_info(
            adapter, "WGPUAdapterPropertiesDrm", lib.WGPUSType_AdapterPropertiesDrm
        )
        if drm is not None:
            primary = (
                (int(drm.primaryMajor), int(drm.primaryMinor))
                if drm.hasPrimary
                else None
            )
            render = (
                (int(drm.renderMajor), int(drm.renderMinor)) if drm.hasRender else None
            )
            result["drm"] = {
                "primary": primary,
                "render": render,
                "primary_node": primary and _dri_node(*primary, "card"),
                "render_node": render and _dri_node(*render, "renderD"),
            }
    if "adapter-properties-d3d" in features:
        d3d = _get_info(
            adapter, "WGPUAdapterPropertiesD3D", lib.WGPUSType_AdapterPropertiesD3D
        )
        if d3d is not None:
            result["d3d"] = {
                "shader_model": int(d3d.shaderModel),
                "luid": (int(d3d.adapterLUIDHighPart) << 32)
                | int(d3d.adapterLUIDLowPart),
            }
    if "adapter-properties-memory-heaps" in features:
        heaps = _get_info(
            adapter,
            "WGPUAdapterPropertiesMemoryHeaps",
            lib.WGPUSType_AdapterPropertiesMemoryHeaps,
        )
        if heaps is not None:
            result["memory_heaps"] = [
                {
                    "size": int(heaps.heapInfo[i].size),
                    "properties": [
                        kebab
                        for name, kebab in _heap_properties.items()
                        if heaps.heapInfo[i].properties
                        & getattr(lib, f"WGPUHeapProperty_{name}")
                    ],
                }
                for i in range(heaps.heapCount)
            ]
            _native("wgpuAdapterPropertiesMemoryHeapsFreeMembers")(heaps[0])
    if "chromium-experimental-subgroup-matrix" in features:
        configs = _get_info(
            adapter,
            "WGPUAdapterPropertiesSubgroupMatrixConfigs",
            lib.WGPUSType_AdapterPropertiesSubgroupMatrixConfigs,
        )
        if configs is not None:
            types = {
                getattr(lib, f"WGPUSubgroupMatrixComponentType_{name}"): kebab
                for name, kebab in _subgroup_matrix_types.items()
                if hasattr(lib, f"WGPUSubgroupMatrixComponentType_{name}")
            }
            result["subgroup_matrix_configs"] = [
                {
                    "component_type": types.get(c.componentType, c.componentType),
                    "result_component_type": types.get(
                        c.resultComponentType, c.resultComponentType
                    ),
                    "m": c.M,
                    "n": c.N,
                    "k": c.K,
                    "min_subgroup_size": c.minSubgroupSize,
                    "max_subgroup_size": c.maxSubgroupSize,
                }
                for c in (configs.configs[i] for i in range(configs.configCount))
            ]
            lib.wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers(configs[0])
    return result


def get_format_capabilities(adapter: GPUAdapter, format: str):
    """What the adapter can do with a texture format beyond WebGPU: the DRM
    format modifiers with which memory of this format can be imported as a
    dmabuf (Linux, feature ``dawn-drm-format-capabilities``), as
    ``{"drm_modifiers": [{"modifier": int, "plane_count": int}, ...]}``."""
    value = enummap.get(f"TextureFormat.{format}")
    if value is None:
        raise KeyError(f"Unknown texture format: {format!r}")
    if "dawn-drm-format-capabilities" not in adapter.features:
        raise RuntimeError("The adapter lacks dawn-drm-format-capabilities")
    drm = new_struct_p("WGPUDawnDrmFormatCapabilities *")
    drm.chain.sType = lib.WGPUSType_DawnDrmFormatCapabilities
    capabilities = new_struct_p(
        "WGPUDawnFormatCapabilities *",
        nextInChain=ffi.cast("WGPUChainedStruct *", drm),
    )
    status = _native("wgpuAdapterGetFormatCapabilities")(
        adapter._internal, value, capabilities
    )
    _check_status(status, "wgpuAdapterGetFormatCapabilities")
    modifiers = [
        {
            "modifier": int(drm.properties[i].modifier),
            "plane_count": int(drm.properties[i].modifierPlaneCount),
        }
        for i in range(drm.propertiesCount)
    ]
    _native("wgpuDawnDrmFormatCapabilitiesFreeMembers")(drm[0])
    return {"drm_modifiers": modifiers}
