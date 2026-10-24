
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
// The device and driver UUIDs of a Vulkan adapter (16 bytes each, into out32);
// returns 0 when Dawn does not give them.
int wgpu_dawn_vulkan_uuids(WGPUAdapter adapter, uint8_t * out32);
// D3D12 and D3D11 (Windows; NULL elsewhere)
void * wgpu_dawn_d3d12_device(WGPUDevice device);
void * wgpu_dawn_d3d12_command_queue(WGPUDevice device);
void * wgpu_dawn_d3d11_device(WGPUDevice device);
void * wgpu_dawn_dxgi_adapter(WGPUAdapter adapter);
WGPUSharedTextureMemory wgpu_dawn_import_d3d12_texture(WGPUDevice device, void * resource, const char * label);
WGPUSharedBufferMemory wgpu_dawn_import_d3d12_buffer(WGPUDevice device, void * resource, const char * label);
WGPUSharedTextureMemory wgpu_dawn_import_d3d11_texture(WGPUDevice device, void * texture, const char * label);
// Metal (macOS; nothing elsewhere)
void wgpu_dawn_metal_wait_for_commands_to_be_scheduled(WGPUDevice device);
