typedef struct WGPUSharedTextureMemoryImpl* WGPUSharedTextureMemory;
typedef struct WGPUSharedFenceImpl* WGPUSharedFence;
typedef enum WGPUSharedFenceType {
    WGPUSharedFenceType_VkSemaphoreOpaqueFD = 0x00000001,
    WGPUSharedFenceType_SyncFD = 0x00000002,
    WGPUSharedFenceType_VkSemaphoreZirconHandle = 0x00000003,
    WGPUSharedFenceType_DXGISharedHandle = 0x00000004,
    WGPUSharedFenceType_MTLSharedEvent = 0x00000005,
    WGPUSharedFenceType_EGLSync = 0x00000006,
    WGPUSharedFenceType_Force32 = 0x7FFFFFFF
} WGPUSharedFenceType ;
typedef struct WGPUSurfaceSourceXlibWindow {
    WGPUChainedStruct chain;
    void * display;
    uint64_t window;
} WGPUSurfaceSourceXlibWindow ;
typedef struct WGPUSurfaceSourceWaylandSurface {
    WGPUChainedStruct chain;
    void * display;
    void * surface;
} WGPUSurfaceSourceWaylandSurface ;
typedef struct WGPUSurfaceSourceXCBWindow {
    WGPUChainedStruct chain;
    void * connection;
    uint32_t window;
} WGPUSurfaceSourceXCBWindow ;
typedef struct WGPUSurfaceSourceMetalLayer {
    WGPUChainedStruct chain;
    void * layer;
} WGPUSurfaceSourceMetalLayer ;
typedef struct WGPUSurfaceSourceWindowsHWND {
    WGPUChainedStruct chain;
    void * hinstance;
    void * hwnd;
} WGPUSurfaceSourceWindowsHWND ;
typedef struct WGPUSharedTextureMemoryDescriptor {
    WGPUChainedStruct * nextInChain;
    WGPUStringView label;
} WGPUSharedTextureMemoryDescriptor ;
typedef struct WGPUSharedTextureMemoryIOSurfaceDescriptor {
    WGPUChainedStruct chain;
    void * ioSurface;
    WGPUBool allowStorageBinding;
} WGPUSharedTextureMemoryIOSurfaceDescriptor ;
static const int WGPUSType_SharedTextureMemoryIOSurfaceDescriptor = 0x00050023;
typedef struct WGPUSharedTextureMemoryDmaBufPlane {
    int fd;
    uint64_t offset;
    uint32_t stride;
} WGPUSharedTextureMemoryDmaBufPlane ;
typedef struct WGPUSharedTextureMemoryDmaBufDescriptor {
    WGPUChainedStruct chain;
    WGPUExtent3D size;
    uint32_t drmFormat;
    uint64_t drmModifier;
    size_t planeCount;
    WGPUSharedTextureMemoryDmaBufPlane const * planes;
} WGPUSharedTextureMemoryDmaBufDescriptor ;
static const int WGPUSType_SharedTextureMemoryDmaBufDescriptor = 0x0005001E;
typedef struct WGPUSharedTextureMemoryProperties {
    WGPUChainedStruct * nextInChain;
    WGPUTextureUsage usage;
    WGPUExtent3D size;
    WGPUTextureFormat format;
} WGPUSharedTextureMemoryProperties ;
typedef struct WGPUSharedTextureMemoryBeginAccessDescriptor {
    WGPUChainedStruct * nextInChain;
    WGPUBool concurrentRead;
    WGPUBool initialized;
    size_t fenceCount;
    WGPUSharedFence const * fences;
    size_t signaledValueCount;
    uint64_t const * signaledValues;
} WGPUSharedTextureMemoryBeginAccessDescriptor ;
typedef struct WGPUSharedTextureMemoryEndAccessState {
    WGPUChainedStruct * nextInChain;
    WGPUBool initialized;
    size_t fenceCount;
    WGPUSharedFence const * fences;
    size_t signaledValueCount;
    uint64_t const * signaledValues;
} WGPUSharedTextureMemoryEndAccessState ;
typedef struct WGPUSharedTextureMemoryVkImageLayoutBeginState {
    WGPUChainedStruct chain;
    int32_t oldLayout;
    int32_t newLayout;
} WGPUSharedTextureMemoryVkImageLayoutBeginState ;
static const int WGPUSType_SharedTextureMemoryVkImageLayoutBeginState = 0x00050027;
typedef struct WGPUSharedTextureMemoryVkImageLayoutEndState {
    WGPUChainedStruct chain;
    int32_t oldLayout;
    int32_t newLayout;
} WGPUSharedTextureMemoryVkImageLayoutEndState ;
static const int WGPUSType_SharedTextureMemoryVkImageLayoutEndState = 0x00050028;
typedef struct WGPUSharedFenceDescriptor {
    WGPUChainedStruct * nextInChain;
    WGPUStringView label;
} WGPUSharedFenceDescriptor ;
typedef struct WGPUSharedFenceExportInfo {
    WGPUChainedStruct * nextInChain;
    WGPUSharedFenceType type;
} WGPUSharedFenceExportInfo ;
typedef struct WGPUSharedFenceMTLSharedEventDescriptor {
    WGPUChainedStruct chain;
    void * sharedEvent;
} WGPUSharedFenceMTLSharedEventDescriptor ;
static const int WGPUSType_SharedFenceMTLSharedEventDescriptor = 0x00050032;
typedef struct WGPUSharedFenceMTLSharedEventExportInfo {
    WGPUChainedStruct chain;
    void * sharedEvent;
} WGPUSharedFenceMTLSharedEventExportInfo ;
static const int WGPUSType_SharedFenceMTLSharedEventExportInfo = 0x00050033;
typedef struct WGPUSharedFenceSyncFDDescriptor {
    WGPUChainedStruct chain;
    int handle;
} WGPUSharedFenceSyncFDDescriptor ;
static const int WGPUSType_SharedFenceSyncFDDescriptor = 0x0005002C;
typedef struct WGPUSharedFenceSyncFDExportInfo {
    WGPUChainedStruct chain;
    int handle;
} WGPUSharedFenceSyncFDExportInfo ;
static const int WGPUSType_SharedFenceSyncFDExportInfo = 0x0005002D;
typedef struct WGPUSharedFenceVkSemaphoreOpaqueFDDescriptor {
    WGPUChainedStruct chain;
    int handle;
} WGPUSharedFenceVkSemaphoreOpaqueFDDescriptor ;
static const int WGPUSType_SharedFenceVkSemaphoreOpaqueFDDescriptor = 0x0005002A;
typedef struct WGPUSharedFenceVkSemaphoreOpaqueFDExportInfo {
    WGPUChainedStruct chain;
    int handle;
} WGPUSharedFenceVkSemaphoreOpaqueFDExportInfo ;
static const int WGPUSType_SharedFenceVkSemaphoreOpaqueFDExportInfo = 0x0005002B;
typedef struct WGPUDawnTogglesDescriptor {
    WGPUChainedStruct chain;
    size_t enabledToggleCount;
    const char* const * enabledToggles;
    size_t disabledToggleCount;
    const char* const * disabledToggles;
} WGPUDawnTogglesDescriptor ;
static const int WGPUSType_DawnTogglesDescriptor = 0x0005000A;
WGPUSharedTextureMemory wgpuDeviceImportSharedTextureMemory(WGPUDevice device, WGPUSharedTextureMemoryDescriptor const * descriptor) ;
WGPUSharedFence wgpuDeviceImportSharedFence(WGPUDevice device, WGPUSharedFenceDescriptor const * descriptor) ;
WGPUStatus wgpuSharedTextureMemoryGetProperties(WGPUSharedTextureMemory sharedTextureMemory, WGPUSharedTextureMemoryProperties * properties) ;
WGPUTexture wgpuSharedTextureMemoryCreateTexture(WGPUSharedTextureMemory sharedTextureMemory, WGPUTextureDescriptor const * descriptor) ;
WGPUStatus wgpuSharedTextureMemoryBeginAccess(WGPUSharedTextureMemory sharedTextureMemory, WGPUTexture texture, WGPUSharedTextureMemoryBeginAccessDescriptor const * descriptor) ;
WGPUStatus wgpuSharedTextureMemoryEndAccess(WGPUSharedTextureMemory sharedTextureMemory, WGPUTexture texture, WGPUSharedTextureMemoryEndAccessState * descriptor) ;
void wgpuSharedTextureMemoryEndAccessStateFreeMembers(WGPUSharedTextureMemoryEndAccessState sharedTextureMemoryEndAccessState) ;
WGPUBool wgpuSharedTextureMemoryIsDeviceLost(WGPUSharedTextureMemory sharedTextureMemory) ;
void wgpuSharedTextureMemoryAddRef(WGPUSharedTextureMemory sharedTextureMemory) ;
void wgpuSharedTextureMemoryRelease(WGPUSharedTextureMemory sharedTextureMemory) ;
void wgpuSharedFenceExportInfo(WGPUSharedFence sharedFence, WGPUSharedFenceExportInfo * info) ;
void wgpuSharedFenceAddRef(WGPUSharedFence sharedFence) ;
void wgpuSharedFenceRelease(WGPUSharedFence sharedFence) ;
static const int WGPUFeatureName_DawnInternalUsages = 0x00050000;
static const int WGPUFeatureName_DawnMultiPlanarFormats = 0x00050001;
static const int WGPUFeatureName_DawnNative = 0x00050002;
static const int WGPUFeatureName_ChromiumExperimentalTimestampQueryInsidePasses = 0x00050003;
static const int WGPUFeatureName_ImplicitDeviceSynchronization = 0x00050004;
static const int WGPUFeatureName_TransientAttachments = 0x00050006;
static const int WGPUFeatureName_MSAARenderToSingleSampled = 0x00050007;
static const int WGPUFeatureName_D3D11MultithreadProtected = 0x00050008;
static const int WGPUFeatureName_ANGLETextureSharing = 0x00050009;
static const int WGPUFeatureName_PixelLocalStorageCoherent = 0x0005000A;
static const int WGPUFeatureName_PixelLocalStorageNonCoherent = 0x0005000B;
static const int WGPUFeatureName_MultiPlanarFormatExtendedUsages = 0x0005000D;
static const int WGPUFeatureName_MultiPlanarFormatP010 = 0x0005000E;
static const int WGPUFeatureName_HostMappedPointer = 0x0005000F;
static const int WGPUFeatureName_MultiPlanarRenderTargets = 0x00050010;
static const int WGPUFeatureName_MultiPlanarFormatNv12a = 0x00050011;
static const int WGPUFeatureName_FramebufferFetch = 0x00050012;
static const int WGPUFeatureName_BufferMapExtendedUsages = 0x00050013;
static const int WGPUFeatureName_AdapterPropertiesMemoryHeaps = 0x00050014;
static const int WGPUFeatureName_AdapterPropertiesD3D = 0x00050015;
static const int WGPUFeatureName_AdapterPropertiesVk = 0x00050016;
static const int WGPUFeatureName_DawnFormatCapabilities = 0x00050017;
static const int WGPUFeatureName_DawnDrmFormatCapabilities = 0x00050018;
static const int WGPUFeatureName_MultiPlanarFormatNv16 = 0x00050019;
static const int WGPUFeatureName_MultiPlanarFormatNv24 = 0x0005001A;
static const int WGPUFeatureName_MultiPlanarFormatP210 = 0x0005001B;
static const int WGPUFeatureName_MultiPlanarFormatP410 = 0x0005001C;
static const int WGPUFeatureName_SharedTextureMemoryVkDedicatedAllocation = 0x0005001D;
static const int WGPUFeatureName_SharedTextureMemoryAHardwareBuffer = 0x0005001E;
static const int WGPUFeatureName_SharedTextureMemoryDmaBuf = 0x0005001F;
static const int WGPUFeatureName_SharedTextureMemoryOpaqueFD = 0x00050020;
static const int WGPUFeatureName_SharedTextureMemoryZirconHandle = 0x00050021;
static const int WGPUFeatureName_SharedTextureMemoryDXGISharedHandle = 0x00050022;
static const int WGPUFeatureName_SharedTextureMemoryD3D11Texture2D = 0x00050023;
static const int WGPUFeatureName_SharedTextureMemoryIOSurface = 0x00050024;
static const int WGPUFeatureName_SharedTextureMemoryEGLImage = 0x00050025;
static const int WGPUFeatureName_SharedFenceVkSemaphoreOpaqueFD = 0x00050026;
static const int WGPUFeatureName_SharedFenceSyncFD = 0x00050027;
static const int WGPUFeatureName_SharedFenceVkSemaphoreZirconHandle = 0x00050028;
static const int WGPUFeatureName_SharedFenceDXGISharedHandle = 0x00050029;
static const int WGPUFeatureName_SharedFenceMTLSharedEvent = 0x0005002A;
static const int WGPUFeatureName_SharedBufferMemoryD3D12Resource = 0x0005002B;
static const int WGPUFeatureName_StaticSamplers = 0x0005002C;
static const int WGPUFeatureName_YCbCrVulkanSamplers = 0x0005002D;
static const int WGPUFeatureName_ShaderModuleCompilationOptions = 0x0005002E;
static const int WGPUFeatureName_DawnLoadResolveTexture = 0x0005002F;
static const int WGPUFeatureName_DawnPartialLoadResolveTexture = 0x00050030;
static const int WGPUFeatureName_DawnTexelCopyBufferRowAlignment = 0x00050032;
static const int WGPUFeatureName_FlexibleTextureViews = 0x00050033;
static const int WGPUFeatureName_SharedFenceEGLSync = 0x00050035;
static const int WGPUFeatureName_DawnDeviceAllocatorControl = 0x00050036;
static const int WGPUFeatureName_AdapterPropertiesWGPU = 0x00050037;
static const int WGPUFeatureName_SharedBufferMemoryFromWindowsHandle = 0x00050038;
static const int WGPUFeatureName_SharedTextureMemoryD3D12Resource = 0x00050039;
static const int WGPUFeatureName_ChromiumExperimentalSamplingResourceTable = 0x0005003A;
static const int WGPUFeatureName_Unorm16FormatsForExternalTexture = 0x0005003B;
static const int WGPUFeatureName_OpaqueYCbCrAndroidForExternalTexture = 0x0005003C;
static const int WGPUFeatureName_Unorm16Filterable = 0x0005003D;
static const int WGPUFeatureName_RenderPassRenderArea = 0x0005003E;
static const int WGPUFeatureName_AdapterPropertiesDrm = 0x0005003F;
static const int WGPUFeatureName_DawnAllowUndefinedLoadStoreOp = 0x00050040;
static const int WGPUFeatureName_BufferMapWriteExtendedUsages = 0x00050041;
static const int WGPUFeatureName_SharedBufferMemoryHostPointer = 0x00050042;
