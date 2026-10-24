"""A minimal Vulkan, through ctypes, for the tests of Dawn's extras: another
Vulkan device on the GPU of a Dawn device (made on Dawn's VkInstance), that
makes images on memory exported as an opaque fd, and reads and writes their
pixels. 64-bit only.
"""

import ctypes
import os

from wgpudawn.backends.dawn import extras

c_u32, c_u64, c_ptr, c_float = (
    ctypes.c_uint32,
    ctypes.c_uint64,
    ctypes.c_void_p,
    ctypes.c_float,
)

VK_FORMAT_R8G8B8A8_UNORM = 37
VK_IMAGE_TILING_LINEAR = 1
VK_IMAGE_USAGE = 0x1 | 0x2 | 0x4 | 0x10  # transfer src/dst, sampled, color attachment
VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT = 0x1
VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT = 0x2
VK_MEMORY_PROPERTY_HOST_COHERENT_BIT = 0x4


class Extent3D(ctypes.Structure):
    _fields_ = [("width", c_u32), ("height", c_u32), ("depth", c_u32)]


class QueueCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("flags", c_u32),
        ("queueFamilyIndex", c_u32),
        ("queueCount", c_u32),
        ("pQueuePriorities", ctypes.POINTER(c_float)),
    ]


class DeviceCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("flags", c_u32),
        ("queueCreateInfoCount", c_u32),
        ("pQueueCreateInfos", ctypes.POINTER(QueueCreateInfo)),
        ("enabledLayerCount", c_u32),
        ("ppEnabledLayerNames", c_ptr),
        ("enabledExtensionCount", c_u32),
        ("ppEnabledExtensionNames", ctypes.POINTER(ctypes.c_char_p)),
        ("pEnabledFeatures", c_ptr),
    ]


class ExternalMemoryImageCreateInfo(ctypes.Structure):
    _fields_ = [("sType", c_u32), ("pNext", c_ptr), ("handleTypes", c_u32)]


class ImageCreateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("flags", c_u32),
        ("imageType", c_u32),
        ("format", c_u32),
        ("extent", Extent3D),
        ("mipLevels", c_u32),
        ("arrayLayers", c_u32),
        ("samples", c_u32),
        ("tiling", c_u32),
        ("usage", c_u32),
        ("sharingMode", c_u32),
        ("queueFamilyIndexCount", c_u32),
        ("pQueueFamilyIndices", c_ptr),
        ("initialLayout", c_u32),
    ]


class MemoryRequirements(ctypes.Structure):
    _fields_ = [("size", c_u64), ("alignment", c_u64), ("memoryTypeBits", c_u32)]


class MemoryType(ctypes.Structure):
    _fields_ = [("propertyFlags", c_u32), ("heapIndex", c_u32)]


class MemoryHeap(ctypes.Structure):
    _fields_ = [("size", c_u64), ("flags", c_u32)]


class MemoryProperties(ctypes.Structure):
    _fields_ = [
        ("memoryTypeCount", c_u32),
        ("memoryTypes", MemoryType * 32),
        ("memoryHeapCount", c_u32),
        ("memoryHeaps", MemoryHeap * 16),
    ]


class ExportMemoryAllocateInfo(ctypes.Structure):
    _fields_ = [("sType", c_u32), ("pNext", c_ptr), ("handleTypes", c_u32)]


class MemoryDedicatedAllocateInfo(ctypes.Structure):
    _fields_ = [("sType", c_u32), ("pNext", c_ptr), ("image", c_u64), ("buffer", c_u64)]


class MemoryAllocateInfo(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("allocationSize", c_u64),
        ("memoryTypeIndex", c_u32),
    ]


class MemoryGetFdInfo(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("memory", c_u64),
        ("handleType", c_u32),
    ]


class ImageSubresource(ctypes.Structure):
    _fields_ = [("aspectMask", c_u32), ("mipLevel", c_u32), ("arrayLayer", c_u32)]


class SubresourceLayout(ctypes.Structure):
    _fields_ = [
        ("offset", c_u64),
        ("size", c_u64),
        ("rowPitch", c_u64),
        ("arrayPitch", c_u64),
        ("depthPitch", c_u64),
    ]


class QueueFamilyProperties(ctypes.Structure):
    _fields_ = [
        ("queueFlags", c_u32),
        ("queueCount", c_u32),
        ("timestampValidBits", c_u32),
        ("minImageTransferGranularity", Extent3D),
    ]


class IDProperties(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("deviceUUID", ctypes.c_uint8 * 16),
        ("driverUUID", ctypes.c_uint8 * 16),
        ("deviceLUID", ctypes.c_uint8 * 8),
        ("deviceNodeMask", c_u32),
        ("deviceLUIDValid", c_u32),
    ]


class Properties2(ctypes.Structure):
    _fields_ = [
        ("sType", c_u32),
        ("pNext", c_ptr),
        ("properties", ctypes.c_uint8 * 2048),
    ]


def _check(result, what):
    if result != 0:
        raise RuntimeError(f"{what} failed: VkResult {result}")


class VulkanDevice:
    """A Vulkan device on the same GPU as ``device`` (a Vulkan GPUDevice)."""

    def __init__(self, device, adapter):
        self.instance = extras.get_vk_instance(device)
        self._device = device  # keeps Dawn's instance alive
        uuid = extras.get_adapter_properties(adapter)["vulkan_uuids"]["device_uuid"]

        def ifn(name, restype, *argtypes):
            address = extras.get_vk_instance_proc_addr(device, name)
            if not address:
                raise RuntimeError(f"No {name}")
            return ctypes.CFUNCTYPE(restype, *argtypes)(address)

        enumerate_devices = ifn(
            "vkEnumeratePhysicalDevices",
            ctypes.c_int32,
            c_ptr,
            ctypes.POINTER(c_u32),
            ctypes.POINTER(c_ptr),
        )
        get_properties2 = ifn("vkGetPhysicalDeviceProperties2", None, c_ptr, c_ptr)
        get_families = ifn(
            "vkGetPhysicalDeviceQueueFamilyProperties",
            None,
            c_ptr,
            ctypes.POINTER(c_u32),
            c_ptr,
        )
        get_memory_properties = ifn(
            "vkGetPhysicalDeviceMemoryProperties", None, c_ptr, c_ptr
        )
        create_device = ifn(
            "vkCreateDevice", ctypes.c_int32, c_ptr, c_ptr, c_ptr, ctypes.POINTER(c_ptr)
        )
        self._get_device_proc_addr = ifn(
            "vkGetDeviceProcAddr", c_ptr, c_ptr, ctypes.c_char_p
        )

        count = c_u32(0)
        _check(
            enumerate_devices(self.instance, ctypes.byref(count), None),
            "vkEnumeratePhysicalDevices",
        )
        physical = (c_ptr * count.value)()
        _check(
            enumerate_devices(self.instance, ctypes.byref(count), physical),
            "vkEnumeratePhysicalDevices",
        )
        for handle in physical:
            ids = IDProperties(sType=1000071004)
            props = Properties2(sType=1000059001, pNext=ctypes.addressof(ids))
            get_properties2(handle, ctypes.byref(props))
            if bytes(ids.deviceUUID) == uuid:
                self.physical = handle
                break
        else:
            raise RuntimeError("Dawn's GPU is not among Vulkan's")

        self.memory_properties = MemoryProperties()
        get_memory_properties(self.physical, ctypes.byref(self.memory_properties))
        count = c_u32(0)
        get_families(self.physical, ctypes.byref(count), None)
        families = (QueueFamilyProperties * count.value)()
        get_families(self.physical, ctypes.byref(count), families)

        priority = c_float(1.0)
        queue_info = QueueCreateInfo(
            sType=2,
            queueFamilyIndex=0,
            queueCount=1,
            pQueuePriorities=ctypes.pointer(priority),
        )
        extensions = (ctypes.c_char_p * 1)(b"VK_KHR_external_memory_fd")
        info = DeviceCreateInfo(
            sType=3,
            queueCreateInfoCount=1,
            pQueueCreateInfos=ctypes.pointer(queue_info),
            enabledExtensionCount=1,
            ppEnabledExtensionNames=extensions,
        )
        self.device = c_ptr()
        _check(
            create_device(
                self.physical, ctypes.byref(info), None, ctypes.byref(self.device)
            ),
            "vkCreateDevice",
        )

        self.create_image = self._fn(
            "vkCreateImage", ctypes.c_int32, c_ptr, c_ptr, c_ptr, ctypes.POINTER(c_u64)
        )
        self.destroy_image = self._fn("vkDestroyImage", None, c_ptr, c_u64, c_ptr)
        self.get_requirements = self._fn(
            "vkGetImageMemoryRequirements", None, c_ptr, c_u64, c_ptr
        )
        self.allocate = self._fn(
            "vkAllocateMemory",
            ctypes.c_int32,
            c_ptr,
            c_ptr,
            c_ptr,
            ctypes.POINTER(c_u64),
        )
        self.free = self._fn("vkFreeMemory", None, c_ptr, c_u64, c_ptr)
        self.bind = self._fn(
            "vkBindImageMemory", ctypes.c_int32, c_ptr, c_u64, c_u64, c_u64
        )
        self.get_fd = self._fn(
            "vkGetMemoryFdKHR",
            ctypes.c_int32,
            c_ptr,
            c_ptr,
            ctypes.POINTER(ctypes.c_int),
        )
        self.get_layout = self._fn(
            "vkGetImageSubresourceLayout", None, c_ptr, c_u64, c_ptr, c_ptr
        )
        self.map = self._fn(
            "vkMapMemory",
            ctypes.c_int32,
            c_ptr,
            c_u64,
            c_u64,
            c_u64,
            c_u32,
            ctypes.POINTER(c_ptr),
        )
        self.unmap = self._fn("vkUnmapMemory", None, c_ptr, c_u64)
        self.destroy_device = self._fn("vkDestroyDevice", None, c_ptr, c_ptr)

    def _fn(self, name, restype, *argtypes):
        address = self._get_device_proc_addr(self.device, name.encode())
        if not address:
            raise RuntimeError(f"No {name}")
        return ctypes.CFUNCTYPE(restype, *argtypes)(address)

    def create_exported_image(self, width, height):
        """A linear RGBA8 image in host-visible memory that is exported as an
        opaque fd. Returns a dict with what Dawn's import needs."""
        external = ExternalMemoryImageCreateInfo(
            sType=1000072001, handleTypes=VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT
        )
        create_info = ImageCreateInfo(
            sType=14,
            pNext=ctypes.addressof(external),
            flags=0x8,  # MUTABLE_FORMAT: Dawn may make sRGB views of RGBA8
            imageType=1,
            format=VK_FORMAT_R8G8B8A8_UNORM,
            extent=Extent3D(width, height, 1),
            mipLevels=1,
            arrayLayers=1,
            samples=1,
            tiling=VK_IMAGE_TILING_LINEAR,
            usage=VK_IMAGE_USAGE,
        )
        image = c_u64()
        _check(
            self.create_image(
                self.device, ctypes.byref(create_info), None, ctypes.byref(image)
            ),
            "vkCreateImage",
        )
        requirements = MemoryRequirements()
        self.get_requirements(self.device, image, ctypes.byref(requirements))
        wanted = (
            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
        )
        for index in range(self.memory_properties.memoryTypeCount):
            flags = self.memory_properties.memoryTypes[index].propertyFlags
            if requirements.memoryTypeBits & (1 << index) and flags & wanted == wanted:
                break
        else:
            self.destroy_image(self.device, image, None)
            raise RuntimeError("No host-visible memory type for the image")
        dedicated = MemoryDedicatedAllocateInfo(sType=1000127001, image=image.value)
        export = ExportMemoryAllocateInfo(
            sType=1000072002,
            pNext=ctypes.addressof(dedicated),
            handleTypes=VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
        )
        allocate_info = MemoryAllocateInfo(
            sType=5,
            pNext=ctypes.addressof(export),
            allocationSize=requirements.size,
            memoryTypeIndex=index,
        )
        memory = c_u64()
        _check(
            self.allocate(
                self.device, ctypes.byref(allocate_info), None, ctypes.byref(memory)
            ),
            "vkAllocateMemory",
        )
        _check(self.bind(self.device, image, memory, 0), "vkBindImageMemory")
        fd_info = MemoryGetFdInfo(
            sType=1000074002,
            memory=memory.value,
            handleType=VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
        )
        fd = ctypes.c_int(-1)
        _check(
            self.get_fd(self.device, ctypes.byref(fd_info), ctypes.byref(fd)),
            "vkGetMemoryFdKHR",
        )
        layout = SubresourceLayout()
        subresource = ImageSubresource(aspectMask=1)
        self.get_layout(
            self.device, image, ctypes.byref(subresource), ctypes.byref(layout)
        )
        return {
            "image": image.value,
            "memory": memory.value,
            "fd": fd.value,
            "size": requirements.size,
            "memory_type_index": index,
            "row_pitch": layout.rowPitch,
            "offset": layout.offset,
            "width": width,
            "height": height,
            # Must stay alive while Dawn reads them (during the import)
            "_create_info": create_info,
            "_external": external,
        }

    def pixels(self, image):
        """The pixels of the image, read through the CPU: (height, width, 4) uint8."""
        import numpy as np

        data = c_ptr()
        _check(
            self.map(
                self.device, image["memory"], 0, image["size"], 0, ctypes.byref(data)
            ),
            "vkMapMemory",
        )
        try:
            raw = (ctypes.c_uint8 * image["size"]).from_address(data.value)
            rows = np.frombuffer(raw, np.uint8)[image["offset"] :]
            pitch = image["row_pitch"]
            rows = rows[: pitch * image["height"]].reshape(image["height"], pitch)
            return (
                rows[:, : image["width"] * 4]
                .reshape(image["height"], image["width"], 4)
                .copy()
            )
        finally:
            self.unmap(self.device, image["memory"])

    def fill(self, image, rgba):
        """Write one color into every pixel of the image, through the CPU."""
        import numpy as np

        data = c_ptr()
        _check(
            self.map(
                self.device, image["memory"], 0, image["size"], 0, ctypes.byref(data)
            ),
            "vkMapMemory",
        )
        try:
            raw = (ctypes.c_uint8 * image["size"]).from_address(data.value)
            rows = np.frombuffer(raw, np.uint8)[image["offset"] :]
            pitch = image["row_pitch"]
            rows = rows[: pitch * image["height"]].reshape(image["height"], pitch)
            rows[:, : image["width"] * 4].reshape(image["height"], image["width"], 4)[
                :
            ] = rgba
        finally:
            self.unmap(self.device, image["memory"])

    def release(self, image):
        self.destroy_image(self.device, image["image"], None)
        self.free(self.device, image["memory"], None)
        if image["fd"] >= 0:
            os.close(image["fd"])
            image["fd"] = -1

    def close(self):
        if self.device:
            self.destroy_device(self.device, None)
            self.device = c_ptr()
