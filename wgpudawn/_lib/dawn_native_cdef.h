
// Functions on Dawn's native C++ API (dawn/native/*.h), implemented in
// dawn_native.cpp. Native builds only; used by wgpudawn.backends.dawn.extras.
// A list of strings is returned as a count, and filled up to max_count.
void wgpu_dawn_set_backend_validation_level(WGPUInstance instance, int level);
size_t wgpu_dawn_all_toggles(const char ** names, const char ** descriptions, int * stages, size_t max_count);
size_t wgpu_dawn_adapter_toggles(WGPUAdapter adapter, const char ** names, size_t max_count);
size_t wgpu_dawn_device_toggles(WGPUDevice device, const char ** names, size_t max_count);
int wgpu_dawn_feature_info(int feature, const char ** name, const char ** description, int * experimental);
void wgpu_dawn_memory_usage(WGPUDevice device, uint64_t * out7);
void wgpu_dawn_allocator_memory(WGPUDevice device, uint64_t * out4);
int wgpu_dawn_reduce_memory_usage(WGPUDevice device);
void wgpu_dawn_perform_idle_tasks(WGPUDevice device);
// Vulkan backend (zero/NULL on a build or device without it)
void * wgpu_dawn_vk_instance(WGPUDevice device);
void * wgpu_dawn_vk_get_instance_proc_addr(WGPUDevice device, const char * name);
