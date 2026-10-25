<h1><img src="https://raw.githubusercontent.com/hmaarrfk/wgpudawn/main/website/logo.svg" alt="" width="40" height="40" align="top"> wgpudawn</h1>

WebGPU for Python, on [Dawn](https://dawn.googlesource.com/dawn).

**[See it run in your browser: the pygfx examples, live, on wgpudawn.](https://www.markharfouche.com/wgpudawn/)**

`wgpudawn` is the API of [wgpu-py](https://github.com/pygfx/wgpu-py) with
Dawn (Google's WebGPU implementation, the one in Chrome) as its backend,
instead of wgpu-native.

> **What this project is.** It has two aims:
>
> 1. **A drop-in replacement for wgpu-py**, version for version. It follows
>    the great architecture and design of wgpu-py, from the
>    [pygfx/wgpu-py](https://github.com/pygfx/wgpu-py) project: all credit
>    for the API, the design and most of the code goes to its authors. Code
>    written for wgpu-py runs unchanged on wgpudawn.
> 2. **More of the GPU than WebGPU gives.** Dawn can do much that WebGPU
>    (in the browser or native) cannot: share textures and buffers with
>    other APIs and processes, synchronize with them through fences, and
>    reach the Vulkan, Metal and D3D objects underneath. wgpudawn exposes
>    that to Python, in its own module, next to the wgpu-py API and without
>    changing it (see [Beyond WebGPU](#beyond-webgpu-dawns-extras)).
>
> This project is maintained by AI agents instead of humans: the code, the
> ports of new wgpu-py releases and the releases themselves are made by an
> agent (see [Versions and releases](#versions-and-releases)).

It is a standalone package:

* The wheels contain Dawn (statically linked); there is nothing else to install
  apart from the GPU drivers of the system.
* It is co-installable with wgpu-py: it only provides the `wgpudawn` module.
* One wheel per platform works for all supported Python versions (abi3).

```sh
pip install wgpudawn
```

```py
import wgpudawn as wgpu

adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
device = adapter.request_device_sync()
print(adapter.summary)
```

The API is documented at https://wgpu-py.readthedocs.io; replace `wgpu` by
`wgpudawn`. `wgpudawn.wgpu_py_version` is the version of wgpu-py that this
version of wgpudawn mirrors.

## In the browser

**[The gallery](https://www.markharfouche.com/wgpudawn/)** runs the examples of
[pygfx](https://github.com/pygfx/pygfx) in your browser, on wgpudawn: Pyodide,
the Pyodide wheel of wgpudawn (which uses the WebGPU of the browser through
Dawn's Emdawnwebgpu) and pygfx (for now with a few fixes on top, see issue 2). It needs a browser with WebGPU and
JSPI, such as a recent Chrome or Edge. Every example is run in headless Chrome
when the site is built; the gallery shows what works and what does not.

## Status

Early. The wgpu-py tests that do not depend on wgpu-native specifics pass, and
so does the unit test suite of [pygfx](https://github.com/pygfx/pygfx) (see
below).

Differences with wgpu-py:

* Shaders are compiled by Tint, which follows the WGSL spec strictly; naga
  (wgpu-native) accepts some shaders that Tint rejects.
* Of wgpu-native's extras (`wgpu.backends.wgpu_native.extras`), only what
  Dawn can do (see [Beyond WebGPU](#beyond-webgpu-dawns-extras)): no GLSL
  shaders, pipeline statistics queries or API traces, and no wgpu-native
  specific features and limits. Dawn has its own non-standard
  features, e.g. `unorm16-texture-formats`.
* Dawn's own extras: see [Beyond WebGPU](#beyond-webgpu-dawns-extras).
* Devices always have the `core-features-and-limits` feature.
* The backends are Vulkan (Linux, Windows), Metal (macOS), and D3D12/D3D11
  (Windows). There is no OpenGL backend.
* Validation errors are raised at the call that causes them, and
  `push_error_scope()` / `pop_error_scope_async()`, `get_compilation_info_async()`
  and the device-lost promise are implemented.

### Libraries that `import wgpu`

Libraries such as pygfx and rendercanvas import `wgpu` by name, so by default
they use wgpu-py, also when wgpudawn is installed. To run them on wgpudawn,
opt in before anything imports `wgpu`:

```py
import wgpudawn

wgpudawn.install_as_wgpu()

import pygfx  # `import wgpu` now gives wgpudawn, in this process
```

After that, `wgpu` and its submodules are wgpudawn's (the same module
objects), and `wgpu.__version__` is `wgpudawn.wgpu_py_version`. wgpudawn never
installs a `wgpu` module on disk, so it stays co-installable with wgpu-py.

CI runs the unit tests of pygfx this way, using `tests/wgpu_shim`: a test-only
package named `wgpu` that calls `install_as_wgpu()`, and that takes the place
of wgpu-py so that pygfx's requirement on it is satisfied. It is not part of
the wgpudawn package.

## Beyond WebGPU: Dawn's extras

WebGPU is designed to be safe and portable, so it leaves out what only some
platforms can do, and everything that touches memory or synchronization of
another API. Dawn implements those parts anyway, for Chrome's own use: video
frames from a decoder or a camera without a copy, textures shared with
another process or another API (Vulkan, Metal, D3D, OpenGL/EGL), fences to
synchronize with them, multi-planar video formats, and access to the native
objects of the backend. wgpudawn exposes them to Python, so that a program
can, for example, render into a buffer that a compositor or a video encoder
reads, or display what a camera wrote, without a round trip through the CPU.

They are in `wgpudawn.backends.dawn.extras` (native builds only; the Pyodide
build runs on the browser's WebGPU, which has none of it). The rules:

* The wgpu-py API is not changed by them: a program that does not use the
  extras behaves exactly as on wgpu-py. They are functions and classes in
  their own module, in the style of wgpu-py (snake_case, dicts for
  descriptors, `GPU*` classes), like wgpu-py's own
  `wgpu.backends.wgpu_native.extras`.
* wgpu-py's API is the reference. Where wgpu-py has the same capability
  (in its API, or in its `wgpu.backends.wgpu_native.extras`), wgpudawn uses
  its names and signatures. Where wgpudawn has it first and wgpu-py adds it
  later, wgpudawn moves to wgpu-py's version, keeping the old name for one
  release with a deprecation warning.
* What a platform or adapter supports is in `adapter.features`, by Dawn's
  feature names in kebab case. They are not WebGPU features, so ask for them
  in the `required_features` of `request_device_sync()`, or in the
  `preferred_features` of `preconfigure_default_device()`.
* Each extra is tested with the other API on the other side (an IOSurface
  made with CoreFoundation, a dmabuf from GBM, ...), not only with Dawn.

What there is:

* **Shared texture memory and shared fences.**
  `import_shared_texture_memory()` makes a `GPUSharedTextureMemory` from
  memory that another API or process owns (an IOSurface on macOS; a dmabuf,
  or Vulkan memory exported as an opaque fd by another Vulkan program or by
  CUDA, on Linux; a D3D11/D3D12 texture shared as an NT handle, an
  `ID3D12Resource` or an `ID3D11Texture2D`, on Windows). `create_texture()` on it gives a texture to render into between
  `begin_access()` and `end_access()`. The `GPUSharedFence` objects that
  `end_access()` returns export what to wait for (an `MTLSharedEvent` and its
  value, a sync fd, an opaque-fd semaphore, or a shared `ID3D12Fence` /
  `ID3D11Fence` handle); `import_shared_fence()` goes the other way.
  `begin_access()` takes the backend's options: the Vulkan image layout,
  `requires_end_access_fence` (D3D11: skip the end fence) and `is_swapchain`
  (D3D12: a buffer of another API's swapchain). On Metal, the state that
  `end_access()` returns can `wait_for_commands_scheduled()`.
  `import_shared_buffer_memory()` does the same for buffers on Windows (a
  D3D12 resource, a shared memory handle, or host memory). Features: `shared-texture-memory-i-o-surface`,
  `shared-texture-memory-dma-buf`, `shared-fence-m-t-l-shared-event`,
  `shared-texture-memory-opaque-f-d`, `shared-fence-sync-f-d`,
  `shared-fence-vk-semaphore-opaque-f-d`.

  With CUDA (Linux): a Vulkan image in device memory, exported as an opaque
  fd, is imported by both Dawn and CUDA (`cudaImportExternalMemory`); Dawn's
  opaque-fd semaphore goes to `cudaImportExternalSemaphore`, so CUDA's stream
  waits for Dawn's work on the GPU. Dawn must run on Vulkan on the same GPU:
  `get_adapter_properties(adapter)["vulkan_uuids"]["device_uuid"]` is CUDA's
  device UUID. Dawn imports memory and does not export its own: the image is
  made by Vulkan (or the other API), and Dawn wraps it.

* **wgpu-py's extras that Dawn has**, with wgpu-py's signatures:
  `multi_draw_indirect()`, `multi_draw_indexed_indirect()` and their
  `_count` variants, `write_timestamp()`, `set_instance_extras()` (the
  backends, validation layers and DXC; and Dawn's toggles) and
  `request_device_sync()` (with Dawn's device toggles; Dawn cannot write a
  trace). Dawn calls some of its features experimental (`feature_info()`
  says which, e.g. `multi-draw-indirect`): they need
  `set_instance_extras(enable_toggles=["allow_unsafe_apis"])`.
* **Toggles, memory and the native instance.** `all_toggles()` lists Dawn's
  toggles (workarounds, debugging aids such as `dump_shaders`,
  `skip_validation`), `get_toggles()` says which an adapter or device has;
  `get_memory_usage()`, `reduce_memory_usage()`, `perform_idle_tasks()`;
  on Vulkan, `get_vk_instance()` and `get_vk_instance_proc_addr()` let
  another library make Vulkan calls on Dawn's instance; on Windows,
  `get_d3d12_device()`, `get_d3d12_command_queue()`, `get_d3d11_device()`
  and `get_dxgi_adapter()` give the native objects (e.g. to make a D3D11
  device on Dawn's GPU); on macOS, `wait_for_commands_to_be_scheduled()`
  orders Dawn's work before Core Animation's or another Metal device's.

* **What the backend says about the GPU.** `get_adapter_properties()`: the
  Vulkan driver version and device/driver UUIDs (the UUID by which CUDA,
  OpenGL or another Vulkan program finds the same GPU), the DRM primary and
  render nodes on Linux (where to allocate a dmabuf, e.g. with GBM), the D3D
  shader model and LUID on Windows, the memory heaps, the subgroup matrix
  configurations. `get_format_capabilities()`: the DRM format modifiers with
  which a format can be imported as a dmabuf.
* **Buffers on host memory, without a copy.**
  `create_buffer_from_host_memory()` makes a `GPUBuffer` whose memory is a
  numpy array (or any writable buffer, aligned to
  `get_host_memory_alignment()`; `allocate_host_memory()` makes such
  memory): the GPU reads and writes it directly. Feature
  `host-mapped-pointer` (experimental; Vulkan except on AMD, Metal, D3D12).
  The memory may be shared with another process (an `mmap` of a file in
  `/dev/shm` or of a memfd): that process then reads what the GPU wrote,
  and writes what it reads. On an integrated GPU this is the GPU's own
  memory; on a discrete GPU the shader reaches it over PCIe.
* **Mappable GPU buffers.** With `buffer-map-extended-usages` (and
  `buffer-map-write-extended-usages`; experimental), a buffer can be both
  `MAP_READ` (or `MAP_WRITE`) and `STORAGE`, `VERTEX`, ...: the CPU maps
  the memory that shaders use, without a staging copy.

* **Video frames: multi-planar formats and external textures.** With the
  `dawn-multi-planar-formats` feature, textures can be NV12
  (`r8bg8-biplanar-420-unorm`), P010 (`r10x6bg10x6-biplanar-420-unorm`) and
  the other 4:2:0, 4:2:2 and 4:4:4 formats, made by Dawn
  (`multi-planar-format-extended-usages`, experimental) or imported (e.g. a
  dmabuf from a camera or a video decoder); their planes are views and
  copies with `aspect="plane0-only"` / `"plane1-only"`.
  `create_external_texture()` makes a texture that a shader samples as
  `texture_external`, converted to RGB on the fly (BT.601, BT.709, BT.2020,
  limited or full range, or any matrix; optionally color-managed with
  transfer functions and a gamut matrix), with crop, rotation and mirroring.
  It is bound with `{"external_texture": {}}` in the bind group layout.

What Dawn has that could come next (Dawn's `dawn/webgpu.h` and
`dawn/native/*Backend.h`): shared texture memory from EGL images and
Android hardware buffers (no Android or OpenGL build yet); the `MTLDevice`
(declared for Objective-C only); pixel local storage, framebuffer fetch,
resource tables. They are added one at a time, each with a test against the
real other API (the `dawn-extra` skill).

## Platforms

Wheels are built for:

| | x86-64 | arm64 |
|---|---|---|
| Linux (glibc >= 2.28) | yes | yes (includes Raspberry Pi 4/5 with a 64-bit OS) |
| macOS (>= 11) | yes | yes |
| Windows | yes | yes |

There is also a wheel for [Pyodide](https://pyodide.org) (Pyodide 314, i.e.
Python 3.14): there, the same bindings run on the WebGPU of the browser, via
Dawn's Emdawnwebgpu. The gallery above uses it; `website/` builds it.

## Building from source

Dawn is not downloaded or built by `pip install`; build it first:

```sh
python tools/build_dawn.py --prefix /path/to/dawn    # needs git, cmake, ninja, a C++20 compiler
DAWN_PREFIX=/path/to/dawn pip install -e ".[dev]"
pip install ./tests/wgpu_shim                        # optional: for the tests that use rendercanvas
pytest tests codegen
```

On Linux this needs the headers of X11, xcb and Wayland.
`tools/build_dawn_manylinux.sh` does the same in the manylinux image that the
wheels are built in. `DAWN_PREFIX` can also point to an extracted release
archive of Dawn (of the release in `build_cffi.py`), or to a prefix with a
shared `libwebgpu_dawn`.

How it works:

* `wgpudawn/_lib` is a cffi (API mode) extension. Its cdef
  (`webgpu_cdef.h`) is generated from Dawn's `webgpu.h` by `tools/gen_cdef.py`:
  the part that the native header and Emdawnwebgpu's share, so one cdef serves
  both. Native builds add `webgpu_native_extra_cdef.h` (what of the native
  header the extras use, also generated) and a few C++ functions on Dawn's
  native API (`dawn/native/`, in `build_cffi.py`), e.g. to enumerate all
  adapters.
* `wgpudawn/backends/dawn` implements the API with it. It started as wgpu-py's
  wgpu-native backend.
* `codegen/` is wgpu-py's code generator: it writes the enums, flags and
  structs from `webgpu.idl`, and checks the backend against the IDL and
  against Dawn's header. Run `python codegen` after changing either.

## Versions and releases

A version has four numbers, `X.Y.Z.N`: `X.Y.Z` is the version of wgpu-py that
it mirrors (same API), and `N` counts the releases of wgpudawn for that
version, which mostly are updates of Dawn. So `wgpudawn~=0.32.0` is "the API of
wgpu-py 0.32.0, on the newest Dawn". (The first releases, `0.0.x`, predate
this scheme.)

The version comes from the git tag; there is no version number in the source.
Pushing a tag builds and tests the wheels, and publishes them to PyPI.
`upstream.json` records the versions of wgpu-py and Dawn that the code
corresponds to.

Maintenance is done by AI agents, with [Claude Code](https://claude.com/claude-code)
skills that are part of this repository:

```sh
claude "/update-dawn release"       # to the latest Dawn release, verify, release X.Y.Z.N+1
claude "/sync-upstream release"     # port a new wgpu-py release, verify, release X.Y.Z.0
claude "/update-website"            # newer pygfx on the website; check every example; deploy
```

Without `release`, they stop before tagging. See `.claude/skills/`.

## License

BSD 2-clause, see `LICENSE`. wgpudawn is derived from wgpu-py (Copyright
2019-2023 Almar Klein, Korijn van Golen). The wheels include Dawn and the
libraries that it is built with; see `LICENSES/`.
