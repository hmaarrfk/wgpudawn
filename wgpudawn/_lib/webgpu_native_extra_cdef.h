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
static const int WGPUFeatureName_SharedTextureMemoryIOSurface = 0x00050024;
static const int WGPUFeatureName_SharedTextureMemoryDmaBuf = 0x0005001F;
static const int WGPUFeatureName_SharedFenceMTLSharedEvent = 0x0005002A;
static const int WGPUFeatureName_SharedFenceSyncFD = 0x00050027;
static const int WGPUFeatureName_SharedFenceVkSemaphoreOpaqueFD = 0x00050026;
