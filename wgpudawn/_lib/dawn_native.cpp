
// Functions on Dawn's native C++ API, for wgpudawn.backends.dawn.extras.
// Declared in dawn_native_cdef.h. Native builds only.

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
