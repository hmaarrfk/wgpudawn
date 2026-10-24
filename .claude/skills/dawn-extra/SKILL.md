---
name: dawn-extra
description: Expose a capability of Dawn that WebGPU does not have (shared texture or buffer memory, shared fences, multi-planar formats, native Vulkan/Metal/D3D objects, adapter properties of the backend, a Dawn-only feature) in wgpudawn.backends.dawn.extras - find it in Dawn's headers, design the Python API after wgpu-py's, bind it, test it against the real other API, document it. Use for "expose X from Dawn", "add a Dawn extra", "can wgpudawn share a texture with Y", "interop with CUDA/Vulkan/Metal/D3D/a camera/a video decoder", "what else could we expose from Dawn".
argument-hint: "[the capability, e.g. 'D3D12 shared textures' or 'survey']"
---

# Add a Dawn extra

wgpudawn has two goals (`CLAUDE.md`): be wgpu-py, version for version, and give
Python what Dawn can do beyond WebGPU. This skill is the second. An extra is
only worth adding when it lets a program do something it could not do with
WebGPU: share memory or synchronization with another API or process, see the
native objects underneath, use a hardware feature that WebGPU leaves out.

Arguments: `$ARGUMENTS`. `survey` (or nothing): only step 1, ending with a
ranked list of candidates and what each would let a program do. Otherwise, the
capability to add, preferably with what it is for (the use case decides the
API and the test).

## Rules

* The wgpu-py API does not change: no new arguments on its methods, no
  different behavior when the extras are not used. Extras are functions and
  classes in `wgpudawn/backends/dawn/extras.py` (or a module next to it, once
  that file grows past one topic), native builds only.
* wgpu-py is the reference. If wgpu-py has the capability, in its API or in
  `wgpu/backends/wgpu_native/extras.py` (check its main, `../wgpu-py`), use its
  names, signatures and argument types exactly, so code moves between them.
  If wgpu-py adds later what wgpudawn had first, follow wgpu-py and keep the
  old name for one release with a `DeprecationWarning`.
* Otherwise, in wgpu-py's style: snake_case functions taking the object they
  act on first (`import_shared_fence(device, ...)`), keyword-only options,
  dicts for descriptors, enums and flags as wgpu-py's strings, `GPU*` classes
  derived from `GPUObjectBase`, native handles (pointers, fds) as `int`.
  Ownership is part of the API: say in the docstring who owns a handle that
  goes in or comes out, and how long it is valid.
* A feature that the device needs is asked for by its name in
  `adapter.features` (Dawn's `WGPUFeatureName`, kebab-case as codegen spells
  it). Do not enable features behind the user's back.
* Look up native functions at call time (`_native(name)` in `extras.py`), so
  the module imports on every build and fails with a clear message where the
  function is missing.
* Every extra is tested with the other side real: memory made by the other
  API (an IOSurface through CoreFoundation, a dmabuf from GBM, a D3D12
  resource, a Vulkan image), and the result read back through that API. A
  test that only round-trips through Dawn proves nothing about interop. Tests
  skip, with the reason, where the platform, the adapter or the library is
  missing; say in the report on which machines they actually ran (the CI
  runners have no GPU on most platforms, so an extra may only be checked on a
  developer machine: say so, do not imply more).

## 1. Find it in Dawn

Dawn has three layers, and an extra may need any of them:

1. Native-only parts of `webgpu.h` (`../dawn-prefix/include/dawn/webgpu.h`;
   the part that Emdawnwebgpu's header shares is already bound). What is not
   bound yet:

   ```sh
   python tools/gen_cdef.py diff build/dawn-update/<tag>/emdawnwebgpu_pkg/webgpu/include/webgpu/webgpu.h ../dawn-prefix/include/dawn/webgpu.h
   ```

   (`tools/update_dawn.py` downloads both headers and prints the same diff.)
   Features are `WGPUFeatureName_*`; chained structs (`WGPUSType_*`) extend
   existing descriptors: `Shared*`, `DawnToggles*`, `AdapterProperties*`,
   `DawnFormatCapabilities`, external textures, multi-planar formats.
2. Dawn's native C++ API, `../dawn-prefix/include/dawn/native/`:
   `DawnNative.h` (adapters, toggles, memory statistics), `VulkanBackend.h`
   (`GetInstance`, `GetInstanceProcAddr`, `WrapVulkanImage`,
   `ExportVulkanImage`), and on other platforms `MetalBackend.h`,
   `D3D12Backend.h`, `D3D11Backend.h`. These are C++: bound through small
   C functions in `NATIVE_PREAMBLE` of `build_cffi.py` and their
   declarations in its native cdef (see `wgpu_dawn_enumerate_adapters`). Check
   that `tools/build_dawn.py` installs the header (it installs what Dawn's
   install target does).
3. Dawn's own tests show how each is used:
   `src/dawn/tests/white_box/SharedTextureMemoryTests*.cpp` (one per kind:
   `_dmabuf`, `_opaquefd`, `_win_d3d12`, ...), `SharedBufferMemoryTests*.cpp`,
   `src/dawn/tests/end2end/VideoViewsTests*.cpp` (multi-planar formats), in
   the Dawn source (`tools/build_dawn.py --keep` keeps it, in
   `../dawn-build/src`). Read them before designing: they
   show the order of calls, the required features and what each platform
   supports.

## 2. Bind it

* `webgpu.h` parts: add the handles, enums, structs, functions and feature
  enum members to the `NATIVE_EXTRA_*` lists in `tools/gen_cdef.py`, in
  dependency order, and regenerate with `python tools/update_dawn.py` at the
  pinned tag (it rewrites `webgpu_native_extra_cdef.h`). Then `python codegen`:
  new feature names appear in `_mappings.py`.
* `dawn/native` parts: a C function in `NATIVE_PREAMBLE` and its declaration
  in the native cdef of `build_cffi.py`; guard platform-specific headers with
  the platform's `#ifdef` and provide a stub that fails clearly elsewhere.
* Rebuild: `DAWN_PREFIX=$PWD/../dawn-prefix pip install --no-build-isolation -e .`
  A compile error here means the cdef and the header disagree; fix the list,
  never hand-edit the generated cdef.

Things that have bitten before:

* Feature names are codegen's kebab case of Dawn's names, e.g.
  `adapter-properties-d-3d`, `shared-texture-memory-d-x-g-i-shared-handle`,
  not what you would guess (`...-d3d`): an extra that checks a misspelt name
  silently does nothing. `test_feature_names_of_the_extras_exist` checks the
  names in docstrings and `"..." in features`; look names up in
  `_mappings.py`.
* A struct of `dawn/native/*Backend.h` derives from `wgpu::ChainedStruct(Out)`:
  do not mirror it as a C struct. The Itanium ABI puts members in the tail
  padding of the base (offset 12, not 16), MSVC does not. Declare a struct
  derived the same way in `dawn_native.cpp` (or use Dawn's header) and copy
  out in C++.
* Structs that hold a `ComPtr` (the D3D12/D3D11 descriptors) can only be
  filled in C++: import through a C function in `dawn_native.cpp`.
* Dawn hides experimental features (`feature_info()` says which) unless the
  instance has `allow_unsafe_apis`; test them in a subprocess with
  `set_instance_extras`, since the instance is process-wide.
* An adapter makes one device; request a new adapter for each device.
* Writing a dmabuf through a plain `mmap` is not coherent with the GPU
  everywhere (the GPU read zeros, differently each run); write through the
  allocator's map (`gbm_bo_map`), which the tests do.
* Host memory for Metal and D3D12 must be pages of its own (`mmap`), not part
  of a `malloc` block: those lose the device.
* Windows and macOS are only tested on CI: WARP (D3D12 and D3D11) on the
  Windows runners, Apple's paravirtual GPU on the macOS ones. The CI step
  "Show adapters" prints each adapter's features.

## 3. Implement, test, document

* `extras.py`: the API of the rules above, with docstrings that say the
  feature to ask for, the platforms, and the ownership of handles.
* `tests/test_dawn_extras.py`: the round trip with the other API (see the
  IOSurface and dmabuf tests), plus argument checks that run everywhere.
* Run `ruff format . && ruff check . && pytest tests codegen` and the pygfx
  tests (`sync-upstream`, step 5): the wgpu-py API must be untouched.
* `README.md`, "Beyond WebGPU": add the extra to "What there is" (and remove
  it from "What could come next").
* Commit on `main`, push, watch CI (`update-dawn`, step 5, for how). A
  release is the owner's decision: say in the report that the extra is
  unreleased, and that `claude "/release"` would publish it.

## 4. Report

What the extra lets a program do, its API, the feature names, on which
platforms and GPUs the test really ran (and where it skipped), what was left
out and why, and the CI run. Then the work log entry (`WORKLOG.md`).
