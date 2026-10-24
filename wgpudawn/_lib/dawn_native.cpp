
// Functions on Dawn's native C++ API, for wgpudawn.backends.dawn.extras.
// Declared in dawn_native_cdef.h. Native builds only.

#include <array>
#include <cstring>

// The Vulkan backend (built on Linux and Windows, see tools/build_dawn.py).
// Its header needs the Vulkan headers, which are not installed with Dawn, so
// its two functions are declared here; the handle types are opaque pointers,
// which is all that their (mangled) signatures need.
#if defined(__linux__) || defined(_WIN32)
#define WGPU_DAWN_HAS_VULKAN 1
struct VkInstance_T;
typedef VkInstance_T* VkInstance;
#ifdef _WIN32
#define WGPU_DAWN_VKAPI_PTR __stdcall
#else
#define WGPU_DAWN_VKAPI_PTR
#endif
typedef void(WGPU_DAWN_VKAPI_PTR* PFN_vkVoidFunction)(void);
namespace dawn::native::vulkan {
DAWN_NATIVE_EXPORT VkInstance GetInstance(WGPUDevice device);
DAWN_NATIVE_EXPORT PFN_vkVoidFunction GetInstanceProcAddr(WGPUDevice device, const char* pName);
}  // namespace dawn::native::vulkan
#endif

// dawn::native::vulkan::AdapterPropertiesVulkanUUIDs, declared the same way
// (VulkanBackend.h needs the Vulkan headers), so that each compiler lays it
// out as Dawn's: the arrays may be in the tail padding of the base (Itanium
// ABI), which a C struct cannot express.
struct WgpuDawnAdapterPropertiesVulkanUUIDs : wgpu::ChainedStructOut {
  WgpuDawnAdapterPropertiesVulkanUUIDs() {
    sType = static_cast<wgpu::SType>(WGPUSType_AdapterPropertiesVulkanUUIDs);
  }
  std::array<uint8_t, 16> deviceUUID = {};
  std::array<uint8_t, 16> driverUUID = {};
};

static int wgpu_dawn_vulkan_uuids(WGPUAdapter adapter, uint8_t* out32) {
  WgpuDawnAdapterPropertiesVulkanUUIDs uuids;
  WGPUAdapterInfo info = WGPU_ADAPTER_INFO_INIT;
  info.nextInChain = reinterpret_cast<WGPUChainedStruct*>(&uuids);
  if (wgpuAdapterGetInfo(adapter, &info) != WGPUStatus_Success) {
    return 0;
  }
  wgpuAdapterInfoFreeMembers(info);
  std::memcpy(out32, uuids.deviceUUID.data(), 16);
  std::memcpy(out32 + 16, uuids.driverUUID.data(), 16);
  return 1;
}

static dawn::native::InstanceBase* wgpu_dawn_instance_base(WGPUInstance instance) {
  return reinterpret_cast<dawn::native::InstanceBase*>(instance);
}

static void wgpu_dawn_set_backend_validation_level(WGPUInstance instance, int level) {
  dawn::native::Instance wrapper(wgpu_dawn_instance_base(instance));
  wrapper.SetBackendValidationLevel(static_cast<dawn::native::BackendValidationLevel>(level));
}

static size_t wgpu_dawn_all_toggles(
    const char** names, const char** descriptions, int* stages, size_t max_count) {
  std::vector<const dawn::native::ToggleInfo*> infos = dawn::native::AllToggleInfos();
  for (size_t i = 0; i < infos.size() && i < max_count; i++) {
    names[i] = infos[i]->name;
    descriptions[i] = infos[i]->description;
    stages[i] = static_cast<int>(infos[i]->stage);
  }
  return infos.size();
}

static size_t wgpu_dawn_copy_names(
    const std::vector<const char*>& found, const char** names, size_t max_count) {
  // The names are static strings of Dawn's toggle table
  for (size_t i = 0; i < found.size() && i < max_count; i++) {
    names[i] = found[i];
  }
  return found.size();
}

static size_t wgpu_dawn_adapter_toggles(WGPUAdapter adapter, const char** names, size_t max_count) {
  wgpu::Adapter wrapper(adapter);  // adds a reference, released at the end of scope
  return wgpu_dawn_copy_names(dawn::native::GetTogglesUsed(wrapper), names, max_count);
}

static size_t wgpu_dawn_device_toggles(WGPUDevice device, const char** names, size_t max_count) {
  return wgpu_dawn_copy_names(dawn::native::GetTogglesUsed(device), names, max_count);
}

// Returns 0 when Dawn does not know the feature.
static int wgpu_dawn_feature_info(
    int feature, const char** name, const char** description, int* experimental) {
  const dawn::native::FeatureInfo* info =
      dawn::native::GetFeatureInfo(static_cast<wgpu::FeatureName>(feature));
  if (info == nullptr) {
    return 0;
  }
  *name = info->name;
  *description = info->description;
  *experimental =
      info->featureState == dawn::native::FeatureInfo::FeatureState::Experimental ? 1 : 0;
  return 1;
}

static void wgpu_dawn_memory_usage(WGPUDevice device, uint64_t* out) {
  dawn::native::MemoryUsageInfo info = dawn::native::ComputeEstimatedMemoryUsageInfo(device);
  out[0] = info.totalUsage;
  out[1] = info.depthStencilTexturesUsage;
  out[2] = info.msaaTexturesUsage;
  out[3] = info.msaaTexturesCount;
  out[4] = info.largestMsaaTextureUsage;
  out[5] = info.texturesUsage;
  out[6] = info.buffersUsage;
}

static void wgpu_dawn_allocator_memory(WGPUDevice device, uint64_t* out) {
  dawn::native::AllocatorMemoryInfo info = dawn::native::GetAllocatorMemoryInfo(device);
  out[0] = info.totalUsedMemory;
  out[1] = info.totalAllocatedMemory;
  out[2] = info.totalLazyAllocatedMemory;
  out[3] = info.totalLazyUsedMemory;
}

static int wgpu_dawn_reduce_memory_usage(WGPUDevice device) {
  return dawn::native::ReduceMemoryUsage(device) ? 1 : 0;
}

static void wgpu_dawn_perform_idle_tasks(WGPUDevice device) {
  wgpu::Device wrapper(device);
  dawn::native::PerformIdleTasks(wrapper);
}

// The caller checks that the device is a Vulkan device: Dawn casts it.
static void* wgpu_dawn_vk_instance(WGPUDevice device) {
#ifdef WGPU_DAWN_HAS_VULKAN
  return reinterpret_cast<void*>(dawn::native::vulkan::GetInstance(device));
#else
  (void)device;
  return nullptr;
#endif
}

static void* wgpu_dawn_vk_get_instance_proc_addr(WGPUDevice device, const char* name) {
#ifdef WGPU_DAWN_HAS_VULKAN
  return reinterpret_cast<void*>(dawn::native::vulkan::GetInstanceProcAddr(device, name));
#else
  (void)device;
  (void)name;
  return nullptr;
#endif
}

// ---- Windows: D3D12 and D3D11 (the backend headers need the Windows SDK) ----

#if defined(_WIN32) && __has_include(<dawn/native/D3D12Backend.h>)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <dawn/native/D3D12Backend.h>
#define WGPU_DAWN_HAS_D3D12 1
#endif
#if defined(_WIN32) && __has_include(<dawn/native/D3D11Backend.h>)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <dawn/native/D3D11Backend.h>
#define WGPU_DAWN_HAS_D3D11 1
#endif

// The native objects are owned by Dawn; these return them without a reference
// of their own (valid while the device or adapter lives). The caller checks
// that the device is of the right backend: Dawn casts it.
static void* wgpu_dawn_d3d12_device(WGPUDevice device) {
#ifdef WGPU_DAWN_HAS_D3D12
  return dawn::native::d3d12::GetD3D12Device(device).Get();
#else
  (void)device;
  return nullptr;
#endif
}

static void* wgpu_dawn_d3d12_command_queue(WGPUDevice device) {
#ifdef WGPU_DAWN_HAS_D3D12
  return dawn::native::d3d12::GetD3D12CommandQueue(device).Get();
#else
  (void)device;
  return nullptr;
#endif
}

static void* wgpu_dawn_d3d11_device(WGPUDevice device) {
#ifdef WGPU_DAWN_HAS_D3D11
  return dawn::native::d3d11::GetD3D11Device(device).Get();
#else
  (void)device;
  return nullptr;
#endif
}

static void* wgpu_dawn_dxgi_adapter(WGPUAdapter adapter) {
#if defined(WGPU_DAWN_HAS_D3D12) || defined(WGPU_DAWN_HAS_D3D11)
  return dawn::native::d3d::GetDXGIAdapter(adapter).Get();
#else
  (void)adapter;
  return nullptr;
#endif
}

// Import an ID3D12Resource (a texture or a buffer) or an ID3D11Texture2D,
// made on the device's own ID3D12Device / ID3D11Device. The descriptors of
// these hold a ComPtr, so they are only available in C++. NULL without them.
static WGPUSharedTextureMemory wgpu_dawn_import_d3d12_texture(
    WGPUDevice device, void* resource, const char* label) {
#ifdef WGPU_DAWN_HAS_D3D12
  dawn::native::d3d12::SharedTextureMemoryD3D12ResourceDescriptor d3d;
  d3d.resource = static_cast<ID3D12Resource*>(resource);
  WGPUSharedTextureMemoryDescriptor desc = WGPU_SHARED_TEXTURE_MEMORY_DESCRIPTOR_INIT;
  desc.nextInChain = reinterpret_cast<WGPUChainedStruct*>(static_cast<wgpu::ChainedStruct*>(&d3d));
  desc.label = {label, WGPU_STRLEN};
  return wgpuDeviceImportSharedTextureMemory(device, &desc);
#else
  (void)device;
  (void)resource;
  (void)label;
  return nullptr;
#endif
}

static WGPUSharedBufferMemory wgpu_dawn_import_d3d12_buffer(
    WGPUDevice device, void* resource, const char* label) {
#ifdef WGPU_DAWN_HAS_D3D12
  dawn::native::d3d12::SharedBufferMemoryD3D12ResourceDescriptor d3d;
  d3d.resource = static_cast<ID3D12Resource*>(resource);
  WGPUSharedBufferMemoryDescriptor desc = WGPU_SHARED_BUFFER_MEMORY_DESCRIPTOR_INIT;
  desc.nextInChain = reinterpret_cast<WGPUChainedStruct*>(static_cast<wgpu::ChainedStruct*>(&d3d));
  desc.label = {label, WGPU_STRLEN};
  return wgpuDeviceImportSharedBufferMemory(device, &desc);
#else
  (void)device;
  (void)resource;
  (void)label;
  return nullptr;
#endif
}

static WGPUSharedTextureMemory wgpu_dawn_import_d3d11_texture(
    WGPUDevice device, void* texture, const char* label) {
#ifdef WGPU_DAWN_HAS_D3D11
  dawn::native::d3d11::SharedTextureMemoryD3D11Texture2DDescriptor d3d;
  d3d.texture = static_cast<ID3D11Texture2D*>(texture);
  WGPUSharedTextureMemoryDescriptor desc = WGPU_SHARED_TEXTURE_MEMORY_DESCRIPTOR_INIT;
  desc.nextInChain = reinterpret_cast<WGPUChainedStruct*>(static_cast<wgpu::ChainedStruct*>(&d3d));
  desc.label = {label, WGPU_STRLEN};
  return wgpuDeviceImportSharedTextureMemory(device, &desc);
#else
  (void)device;
  (void)texture;
  (void)label;
  return nullptr;
#endif
}

// ---- macOS: Metal ----

#if defined(__APPLE__)
namespace dawn::native::metal {
DAWN_NATIVE_EXPORT void WaitForCommandsToBeScheduled(WGPUDevice device);
}  // namespace dawn::native::metal
#endif

// Wait until the submitted work of a Metal device is scheduled, so that
// another API (or Core Animation) that uses shared memory afterwards sees it.
static void wgpu_dawn_metal_wait_for_commands_to_be_scheduled(WGPUDevice device) {
#if defined(__APPLE__)
  dawn::native::metal::WaitForCommandsToBeScheduled(device);
#else
  (void)device;
#endif
}
