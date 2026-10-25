# Work log

wgpudawn is maintained by AI agents (see the README). This is the log of that
work: one entry per working session, newest first, with what was asked, what
was done, what it took, and what was learned about working this way. It is
part of the repository so that anybody can see how the project is made, and so
that the next agent starts from what the previous ones learned.

**Agents: you maintain this file.** At the end of every session that changes
the repository (a skill run or anything else), add an entry at the top of
[Sessions](#sessions):

1. `python tools/session_stats.py --markdown` prints the header of the entry
   with the facts (duration, human prompts, model, tokens, API-equivalent
   cost), from the transcript of the session. Do not estimate these by hand.
2. Fill in: what the human asked for (paraphrased, one line per request, in
   order; never paste prompts verbatim or anything private), what was
   delivered (with commit hashes, CI runs, releases), what went wrong and how
   it was found, and what is left open.
3. If the session taught something that the next agent should do differently,
   add or sharpen a line in [Practices](#practices), and, when it is a rule
   for a specific task, in the skill for that task (`.claude/skills/`). A
   practice that turned out wrong is removed, not kept with a caveat.

Keep entries factual and short. The numbers are the transcript's; the cost is
what the tokens would cost at the list prices of the API
(`tools/model_prices.json`), not a bill.

## Practices

What has worked, and what has not, in running this project with agents. Each
line is here because of something that happened; the session that taught it is
in parentheses.

**Giving the work**

* When the cause is known and the fix is in scope, make the fix, not a
  workaround with "say if you want the real fix": the human asked for larger
  steps after the barn lamp got a graceful failure first. (2026-10-14)
* State the goal and the constraints, not the steps: "standalone, co-installable,
  version from tags, wheels for these platforms, test by running pygfx's test
  suite" was enough to build the project. The constraints ("never ship a `wgpu`
  module") are what the agent cannot guess. (2026-10-12)
* Say what you will not decide ("you may push directly to main") and what
  stays yours (tags publish to PyPI). An agent that knows where the line is
  does not stop to ask on the near side of it. (2026-10-12)
* Steer while it works. Short messages mid-session ("also upload the Pyodide
  wheel", "explain why each one cannot run") were cheaper than a longer brief
  up front, because they were written after seeing results. (2026-10-12)

**Doing the work**

* A constant in the cdef can carry its value and still be checked: cffi's API
  mode compares `static const int X = value;` with the real header when the
  extension is built, and a wrong value fails the build. So native-only enum
  members (sTypes, feature names) are written with their values, which is
  what lets codegen read them. (2026-10-24)
* Test an interop extra against the other API, not only through Dawn: a
  round trip through Dawn alone passed while the UUIDs were 4 bytes off and
  the dmabuf test silently used another GPU's node. And a check that compares
  two falses passes for the wrong reason: test that the names you test for
  exist. (2026-10-24)
* A fence or handle that an API object owns dies with the object: keep the
  object, not only the exported fd or pointer, until the wait is done; a
  closed fd polls as ready at once (`POLLNVAL`), which looks like success.
  (2026-10-24)
* Make the truth mechanical. Every claim the project makes is produced by a
  command: the version by the git tag, the bindings by `tools/update_dawn.py`,
  "this example works" by `website/check.mjs`, the numbers in this file by
  `tools/session_stats.py`. Then a later agent can re-derive instead of
  trusting. (2026-10-12)
* Check the checker. The first version of the example checker reported 193
  working examples; 7 of them drew nothing, because the browser reports GPU
  validation errors asynchronously and the checker did not listen. A native
  run of the same examples showed it. A pass that cannot fail is not a
  result. (2026-10-12)
* Reproduce where the error is loud. The same failure was an anonymous
  "invalid pipeline" in the browser and a precise WGSL error with a line
  number natively. Debug in the environment that tells you the most, then
  confirm in the one that matters. (2026-10-12)
* Run the real thing early, on every platform. Local Linux was green for an
  hour while the first CI run found: a compiler too old on one macOS runner,
  a Windows DLL search rule, and GPU features missing on virtual machines.
  None were visible from one machine. (2026-10-12)
* Slow steps go first and in the background (Dawn builds, CI); do not wait on
  them, and do not cancel them with an unrelated push. Scope caches so that a
  change for one platform does not rebuild five others. (2026-10-12)
* When a difference is the other implementation being wrong per the spec
  (pygfx shaders that Dawn rejects), do not paper over it: record it with the
  rule and the fix, and show it as a known failure. (2026-10-12)

* Never cut the output of the command that decides whether to push. A check
  whose last two lines were all that was read had crashed at start. Read the
  exit code and the summary line, or do not push. (2026-10-12)
* Look at the product, not only at its tests. The first deployment had black
  thumbnails while every job was green, because nothing asserted that a
  picture shows something. Add the assertion when you find such a gap (the
  checker now refuses a mostly black gallery). (2026-10-12)
* When a fix for an environment you cannot see fails twice, change the
  approach instead of guessing a third time: pictures that need a GPU are
  taken where there is one, and kept in the repository. (2026-10-12)
* Measure before and after, with a harness that stays: "fast" became
  `check.mjs --warm`, which reports click-to-first-frame for every example and
  fails when warm and cold disagree. (2026-10-12)

**Using several agents**

* Parallelize by ownership of files, not by topic: one agent owned three
  website files, one the backend, one read-only research; the main session
  kept CI and the build tooling. Nothing collided. State in each brief which
  files are off limits. (2026-10-12)
* Research agents before building: "is there an imgui wheel for this exact
  Pyodide?" (yes, on PyPI) and "can PyTorch run here?" (yes, and it would not
  help) each took a few minutes and saved a build that was not needed and a
  feature that was not worth it. Ask for evidence and for what was verified
  versus inferred. (2026-10-12)
* An agent's report is a claim, not a result: the main session re-ran what
  mattered (the examples that were said to be broken) before acting on it.
  (2026-10-12)

* A page that diagnoses must itself be run after every change of what it
  tests: the wgpudawn step of `diagnose.html` broke when the site moved from
  wheels to a bundle, and nobody saw, because the page was only read. (2026-10-13)
* `can_run_sync()` being true does not mean `run_sync` works (Safari 27). Do
  the waiting with `await` wherever the code is ours, and keep blocking for
  what an example itself asks. (2026-10-13)

* When a browser on a device you do not have fails, show the message of the
  error before anything else (not only its stack), and find a way to
  reproduce it locally: here the same engine with the device's user agent
  did, after five rounds without. (2026-10-13)
* A web server of a check must serve what the site serves: `check.mjs` had
  no type for `.wasm`, which only mattered once the site hosted Pyodide
  itself, and looked like a hang. (2026-10-13)

**Limits and irreversible steps**

* Publishing (a tag, hence PyPI) only from a commit whose CI run was seen
  green, and only when the human has said to. Everything before that is
  cheap to redo; that step is not. (2026-10-12)
* Outward actions on other people's projects (issues, pull requests upstream)
  are proposed to the human with the text ready, not done. (2026-10-12)

* A fix removes the first error, not the last. After fixing what an example
  reported, run it again in the browser before saying that it works: the
  limits of a browser are lower than those of a native device. (2026-10-13)

* A picture that "looks plausible" is not checked. Compare the picture from
  the browser with the same example rendered natively before it becomes the
  reference; a grid with holes looks like a design. (2026-10-13)
* When the calls and the data on the GPU are right and the picture is wrong,
  the data was wrong before it got there: check the values, not the
  plumbing. And a browser is a different machine: its clock is coarse on
  purpose. (2026-10-13)

## Sessions

<!-- Newest first. `python tools/session_stats.py --markdown` makes the header. -->

## 2026-10-25 - The website job: a flaky `synced_video`

Same session as the entries below.

Asked: why the website failed on the work-log commit after 0.32.0.4.

* Run 40157548256 (`2cbe40e`, only `WORKLOG.md` changed): `Website` failed
  on `feature_demo/synced_video`. The first attempt failed after 8 s with a
  lost device or a page that did not respond (that is what qualifies it for
  the retry). The retry timed out after 240 s. In the four runs before, it
  passed in 7 to 10 s. Locally, the site of that very run passes it in 4 s,
  three times out of three.
* Class: the checker, on the runner. The example re-uploads three 512x512
  textures every frame at `max_fps=999`, on SwiftShader with four browsers
  at once. It is flaky there, not broken.
* The first error could not be read: the retry overwrote it in
  `results.json`, and the log shows only the last line, which was the
  example's own output. `check.mjs` now keeps the first error as `first`
  and also logs the line that names the cause.
* Re-ran the failed job once: `Website` and `Deploy the website` passed.

## 2026-10-24 - 0.32.0.4: the rest of shared texture memory, and CUDA

Same session as the entries below.

Asked: what Dawn has for sharing buffers and images (read and write), then
"add them", with the NVIDIA GPU's Vulkan driver installed (without a
reboot) to test CUDA.

* Audit against Dawn's `webgpu.h` and the backends' `EnableFeature` calls.
  Buffers can't be imported as shared memory on Vulkan or Metal (only on
  D3D12), and Dawn never exports memory. For images, three options were
  missing: D3D11's `requiresEndAccessFence`, D3D12's `isSwapchain`, and
  Metal's commands-scheduled future. All three are now added (`d0e0c5a`).
* Dawn rejects the D3D options on other backends, but a rejected
  BeginAccess still holds the memory, so the next access fails too. We now
  refuse them in Python before calling Dawn.
* The NVIDIA Vulkan driver, installed without packages or a reboot:
  * `apt install libnvidia-gl-610` would have moved the machine to driver
    615 (kernel module included) while 610 is loaded.
  * Instead, the files came from NVIDIA's 610.57.04 `.run` (checksum
    verified), installed in `~/.local` with an ICD json there.
  * Vulkan on NVIDIA starts through EGL, so it also needs an EGL vendor
    file (`/usr/share/glvnd/egl_vendor.d/90_nvidia_local.json`, after
    Mesa's).
* New tests:
  * CUDA and Dawn on one Vulkan image in device memory, both directions,
    with Dawn's semaphore waited on by CUDA's stream on the GPU. Passes on
    the 4090; `tests/cudautils.py` uses the driver API through ctypes.
  * A host-memory buffer shared with another process.
  * Mappable `STORAGE` buffers.
  * The dmabuf tests now look for an adapter with a GBM backend (NVIDIA
    has none installed here).
* CI 40156298765: on macOS, the IOSurface test with the Metal wait passed.
  On Windows, the DXGI test with the D3D option passed.
* Tagged 0.32.0.4 once the test jobs were green, as the owner asked
  (tag run started while the website job was still building).

## 2026-10-24 - 0.32.0.3: one test that needed wgpu-py

Same session as the entries below.

* The owner's conda-forge agent found the problem by reading the 0.32.0.2
  sdist: `test_do_not_import_utils_submodules` ran `import wgpu.utils` in a
  subprocess. That works only with the shim or wgpu-py installed, which our
  CI always has.
* Fixed in `0bc3500`. Verified by running the sdist's `tests/` in a venv
  with neither the shim nor wgpu-py.
  * 0.32.0.2: 1 failed.
  * 0.32.0.3: 228 passed, 8 skipped.
  * Without a GPU driver: 66 passed, 99 skipped.
* Released as 0.32.0.3 (tag run 40149518295) once the test jobs were green,
  without waiting for the website job, as for 0.32.0.2. PyPI's 8 hashes
  match CI's.
* Practice: run the sdist's tests in an environment that has neither the
  shim nor wgpu-py. Our CI has both, so it can't catch this.

## 2026-10-24 - 0.32.0.2: what conda-forge's recipe found

Same session as the entries below.

Asked: does conda-forge's recipe (staged-recipes#35347) need any of our
fixes? Then: "do it, release 0.32.0.2 ahead of the pages being built".

* The recipe built on all three platforms; its tests failed, each platform
  for its own reason. Two of the reasons were ours:
  * Linux (77 failures): no Vulkan driver in the container, and
    `request_adapter()` gave out Dawn's Null backend adapter, which reads
    back garbage. `enumerate_adapters()` already left it out. Now
    `request_adapter()` raises unless `WGPU_BACKEND_TYPE=Null`.
    `tests/conftest.py` turns "Request adapter failed" into a skip when
    there is no adapter.
  * The sdist had no test helpers: `MANIFEST.in` now includes `tests/*.py`
    (not the shim).
* Two were conda-forge's `dawn` feedstock, both CMake flags that
  `tools/build_dawn.py` already sets:
  * Windows: d3dcompiler_47 fails to load with error 87, so
    `DAWN_FORCE_SYSTEM_COMPONENT_LOAD` is needed.
  * macOS: "SPIR-V is disallowed", so `TINT_BUILD_SPV_READER` is needed.
* Reproduced locally with `VK_ICD_FILENAMES=/nonexistent.json`.
  * Before the fix: `Null backend via Null`.
  * After: 66 passed, 99 skipped, no failures.
  * From the sdist's `tests/` alone: 229 passed.
* Released directly as 0.32.0.2 (commit `84e78e5`, CI 40147478032, tag run
  40147928801). The owner asked not to wait for the website job, so the tag
  went out once all the test jobs were green. No candidate first: the only
  packaging change was the sdist's file list, which I checked by building
  it.

## 2026-10-24 - Release 0.32.0.1: the Dawn extras

Same session as the entry below (whole session, from 2026-10-13: 278.6 h
wall clock, 10.5 h agent working, 84 human prompts, $126.01 at API list
prices).

Asked: "Let's release it as you see fit."

* Commit `28402de`, CI 40101869649 green: every test job 221 to 227 passed,
  with only the platform skips.
* `build_cffi.py` had changed since 0.32.0.0 (the C++ layer on
  `dawn/native`), so it went out as `0.32.0.1rc1` first (tag run
  40106352422). PyPI's 8 hashes matched CI's, a clean venv found the Intel
  GPU and 42 features, and pip found a wheel for each of the six native
  platforms. The Windows wheels bundle the same two MSVC DLLs as 0.32.0.0.
  Then `0.32.0.1` went out on the same commit (tag run 40106845681).

## 2026-10-24 - Dawn beyond WebGPU: the extras, one area at a time

| | |
|---|---|
| Session | `7a75407f-39ea-41af-b578-d4d4c430723c` |
| When (UTC) | 2026-10-13T00:51:56+00:00 to 2026-10-24T14:00:59+00:00 |
| Duration | 277.15 h wall clock, 10.09 h agent working |
| Human prompts | 82 (14444 words) |
| Subagents | 6 |
| Model | `claude-opus-5-5` (Anthropic): 1435 requests; tokens: 3,060 input, 957,686 output, 346,549,611 cache read, 5,481,365 cache write; $123.71 at API list prices |
| API-equivalent cost | $123.71 (estimate; see tools/session_stats.py) |

(The numbers are those of the whole session, which began on 2026-10-13.)

Asked: work through the audit's list on its own, exposing what wgpu-py's
extras and Dawn offer beyond WebGPU, without waiting for review.

* `b5a5b34`: all 63 of Dawn's own features in `adapter.features` (there
  were five).
* `3e53c88`: wgpu-py's extras that Dawn has, with wgpu-py's signatures
  (`multi_draw_indirect` and variants, `write_timestamp`,
  `set_instance_extras`, `request_device_sync`); Dawn's toggles per
  instance, adapter and device; `feature_info`; memory statistics; the
  Vulkan instance and its proc addr. A C++ layer on `dawn/native`
  (`_lib/dawn_native.cpp`).
* `0030803`: adapter properties (Vulkan driver and UUIDs, DRM nodes, D3D
  shader model and LUID, memory heaps, subgroup matrices), DRM format
  modifiers, zero-copy buffers on host memory (`host-mapped-pointer`).
* `a37e34b`: Vulkan memory exported as an opaque fd (from another Vulkan
  device, or CUDA) as shared texture memory.
* `bbcef5f`: video: the multi-planar formats (NV12, P010, ...) and their
  planes, external textures (YUV to RGB in the sampler), and the `aspect`
  of copies and views, which the backend ignored (as wgpu-py's does).
* `392056c`: Windows: DXGI shared handles, D3D12 resources, D3D11 textures,
  DXGI fences, shared buffer memory, the native D3D objects; Metal's
  scheduling wait.
* Every extra is tested against the other API: Vulkan (a second VkDevice on
  Dawn's instance, through ctypes), GBM dmabufs (RGBA and NV12), D3D11
  (through COM vtables, on CI only), numpy memory under a compute shader.
* Found by those tests: the Vulkan UUIDs were read 4 bytes off (a C++
  struct's members in its base's tail padding); the dmabuf test used the
  NVIDIA render node while Dawn ran on the Intel GPU, and skipped; the D3D
  adapter properties never worked (a misspelt feature name); host memory
  from `malloc` loses the device on Metal and D3D12 (CI).
* A false lead, corrected before it was committed: a dmabuf that the CPU
  filled read as zeros; it looked like the first image layout, but was the
  plain `mmap` (not coherent here); `gbm_bo_map` is.
* CI: runs 40097892750, 40098506801 (Windows test fixes), 40099516204 (all
  green, website 202 ok), 40100575603 (Windows sharing). Released as
  0.32.0.1, see the entry above.

## 2026-10-24 - Two goals: wgpu-py, and Dawn beyond WebGPU

Same session as the light_view entry, continued.

* The owner widened the project: besides being wgpu-py version for version,
  wgpudawn exposes what Dawn can do beyond WebGPU (shared textures, buffers
  and fences, the native objects of the backend, ...), with wgpu-py's API as
  the reference wherever wgpu-py has, or later gets, the same capability.
* README ("What this project is", a new section "Beyond WebGPU: Dawn's
  extras" with the rules, what there is and what could come next, and the
  three layers of Dawn in "How it works"), `CLAUDE.md`, and the skills
  `sync-upstream`, `update-dawn` and `triage` now say so. New skill
  `dawn-extra`: how to find a capability in Dawn's headers and tests, bind
  it, design it after wgpu-py, and test it against the real other API.
* Audit of the shared texture extras (0.32.0.0) and of what Dawn has that is
  not bound: in the session's report to the owner; nothing changed in code.

## 2026-10-22 - Dawn's SharedTextureMemory and SharedFence as native extras, released as 0.32.0.0

| | |
|---|---|
| Session | `348e978e-7214-4dbf-b4bc-ccbd13f6008c` |
| When (UTC) | 2026-10-22T18:25:24+00:00 to 2026-10-24T12:07:11+00:00 |
| Duration | 41.7 h wall clock, 6.83 h agent working |
| Human prompts | 91 (9095 words) |
| Subagents | 3 |
| Model | `<synthetic>` (Anthropic): 1 requests; tokens: 0 input, 0 output, 0 cache read, 0 cache write; price unknown |
| Model | `claude-fable-5-1` (Anthropic): 132 requests; tokens: 3,554 input, 386,301 output, 55,377,334 cache read, 3,798,853 cache write; $80.68 at API list prices |
| Model | `claude-opus-5-5` (Anthropic): 691 requests; tokens: 1,424 input, 499,150 output, 138,286,111 cache read, 1,626,790 cache write; $49.46 at API list prices |
| API-equivalent cost | $130.14 (estimate; see tools/session_stats.py) |

Asked: expose Dawn's SharedTextureMemory and SharedFence through wgpudawn, in
the way the project binds native-only things, with tests on native builds,
then push to `main` and cut a release. (The same session first used a side
binding of those functions with ctypes against a shared Dawn, which is what
showed that the API was worth having in the package.)

* `tools/gen_cdef.py`'s native-extra mode now takes handles, enums, structs,
  functions and enum members, and writes a chained struct's sType and the
  feature names as `static const int X = value;`. cffi checks such a value
  against the real header when the extension is built (a wrong value fails
  the compile), so the constants are verified like everything else and carry
  their values. `codegen/hparser.py` reads them, so `python codegen` writes
  Dawn's native feature names into `_mappings.py` in the generator's own
  spelling (`shared-texture-memory-i-o-surface`, like
  `texture-compression-b-c`). Commits 07384d3, 0f38f0c, daaefba.
* `wgpudawn.backends.dawn.extras`: `import_shared_texture_memory()`,
  `GPUSharedTextureMemory` (properties, `create_texture()` with view formats,
  `begin_access()` / `end_access()`), `GPUSharedFence` (`type`, `export()`)
  and `import_shared_fence()`. Memory imported as a dmabuf tracks the Vulkan
  image layout itself: Dawn's Vulkan backend rejects a begin or end access
  without the layout chain, and reports the layout a pass left the image in
  (`COLOR_ATTACHMENT_OPTIMAL`, not the `GENERAL` that was asked for).
* `tests/test_dawn_extras.py` makes the memory with ctypes (an IOSurface
  through CoreFoundation, a GBM buffer on the first render node), renders
  into it, waits on the exported fences and reads the pixels back through
  the other API; it skips where the platform, the adapter or the libraries
  lack it. Checked on Apple silicon (Metal: IOSurface, MTLSharedEvent) and on
  an Intel Iris Xe (Vulkan: dmabuf, sync fd).
* Two things found by the tests: the first access of uninitialized memory
  can export two fences (Dawn's lazy clear and the pass), and a `GPUSharedFence`
  owns its fd, so a caller that keeps only the exported fd and drops the
  fence polls a closed descriptor, which `poll()` reports at once as
  `POLLNVAL`. The test asserts `POLLIN`.
* Not done: `required_features` of `preconfigure_default_device()` still
  validates against the IDL enum, so the native names go in
  `preferred_features` there (the README says so); and the conda-forge
  Dawn, which the local builds used, has no SPIR-V reader, so
  `test_compute_0_1_spirv` fails locally on `main` as before. The wheels
  build Dawn with it.
* CI: run 40089683894 on main; every build and test job green at once, the
  Website job once failed on `feature_demo/helpers_stats` (the checker's
  transient class, a page that did not respond; `validate_ndc` the same, and
  it passed on its retry) and was green on the rerun. Release 0.32.0.0, the
  first under the X.Y.Z.N scheme: tag run 40091430614, eight files on PyPI
  with the hashes of the run's artifacts, a clean install outside the
  checkout, the extras tests passing on the published wheels on macOS and
  Linux, and the release notes written.

## 2026-10-17 - light_view with an imgui panel

Same session, continued.

* `other/light_view` showed lights and materials, but its controls were a Qt
  window, so it was listed as impossible in a browser. On the pygfx branch
  of the site (`381942f`), its panel is now imgui, like `bloom` and
  `gltf_viewer`, with the same controls (colour dialogs became imgui colour
  editors). It runs on every rendercanvas backend. Not offered to pygfx yet.
* In Chrome on a GPU it draws, and clicks on the panel take effect
  (wireframe, auto rotate, a second light). 12 examples cannot run in a
  browser now: Qt and wx windows, open3d, audio, psutil.

## 2026-10-16 - Video in the browser: PyAV and FFmpeg for Pyodide

Same session, continued.

* imageio reads video with PyAV, which binds FFmpeg; neither PyPI nor Pyodide
  has them for Pyodide. (imageio's other video plugin runs an `ffmpeg`
  program as a subprocess, which a browser cannot do.)
  `website/build_pyav.sh` compiles FFmpeg 9.0.2 with the Emscripten of
  Pyodide (LGPL; the decoders, demuxers and parsers of common formats,
  encoders that need no external library) into one shared library, and builds
  PyAV 19.0.1 with `pyodide build` against it. PyAV has about 40 extension
  modules; they all load that one library (6.5 MB), found through rpath. The
  wheel is 3 MB. CI builds it in the `pyodide` job, next to freetype-py.
* Two details: FFmpeg has one object file in two of its libraries, so the
  merge allows the duplicate; and Pyodide replaces only one `$ORIGIN` per
  rpath entry, so each directory is its own entry.
* In Pyodide in Node, imageio reads all 280 frames of `cockatoo.mp4` in
  2.3 s, the first one identical to a native decode, and writes an MP4 that
  it reads back.
* The site serves the wheel to the examples that read video
  (`built_by_import` in `pyodide.json`). `feature_demo/geometry_plane` and
  `feature_demo/video_yuv` (which was listed as impossible in a browser) play
  the video. In Chrome on a GPU, all 201 examples that can run in a browser
  work; 13 cannot (Qt, wx, threads, sockets and the like).

## 2026-10-16 - All the images of image_histogram

Same session, continued.

* `other/image_histogram` offers 11 sample images of imageio in a dropdown,
  named at runtime (`f"imageio:{name}.png"`). The build only saw names written
  out in full, so the site served 4 of them, and choosing e.g. "text" failed
  to download. The build now combines the strings of such an example with
  what follows the placeholder and keeps those that are sample images of
  imageio (its list, in `build.py`). All 11 load in the browser, with their
  histograms. Two examples no longer list a file that is not a sample image
  (it was never served).

## 2026-10-15 - Sponza, from the files of one scene

Same session, continued.

* `other/sponza_scene` looks for a checkout of the whole KhronosGroup/glTF-Sample-Assets
  repository in a parent directory. The build now reads `Sponza.gltf` at a
  pinned commit and downloads only the files it refers to (71 files, 52 MB),
  served as one 48 MB data file. The page unpacks it at
  `examples/glTF-Sample-Assets/Models/Sponza/glTF`, where the example finds
  it; the example is unchanged. `GLTF_SCENES` in `build.py` lists such
  scenes.
* In Chrome on a GPU it draws in about 6 s. The picture is the same as that
  of Dawn and of wgpu-native outside the browser, which are pixel-identical
  to each other. A comparison at a different canvas size first looked like a
  difference: some small white flowers show at 640x480 and not at the
  page's 839x629, natively too. 199 of the 200 examples that can run in a
  browser now work; the last one plays a video, which needs PyAV.

## 2026-10-15 - A draw callback that waits for the GPU

Same session, continued.

* `validation/validate_view_offset` draws an offscreen canvas four times from
  inside the draw callback of the visible canvas, and each time reads the
  picture back from the GPU. rendercanvas draws in an animation frame of the
  browser, and Python called from there cannot wait (no stack that JSPI can
  suspend). The page now calls the paint of rendercanvas through Pyodide's
  `callPromising`, so a draw callback can use the blocking API of wgpu, as on
  a desktop. The example itself is unchanged. It looks like pygfx's reference
  screenshot. In Chrome on a GPU 198 of 200 examples work, and the other
  examples behave as before. In a browser without JSPI (Safari on iOS) the
  page paints as before.
* The page sized the canvas of that example from the first `size=(...)` in
  its source, which is the offscreen canvas's; it now skips offscreen
  canvases. No other example's size changed.
* Locally, headless Chrome 154 on SwiftShader loses the GPU device of every
  example within half a second (`introductory/cube` too), so checks without
  a GPU are only meaningful in CI.

## 2026-10-13 - 0.0.2, and an example that asks the GPU what it allows

Same session, continued.

* 0.0.2: the same code as 0.0.1; the logo in the README has an absolute
  address, because PyPI does not resolve relative ones (and the page of a
  release cannot be changed afterwards). It was the first tag whose GitHub
  release was made by the publish job: pushing the tag is the whole release.
* `other/image_histogram` used 1024 invocations per compute workgroup, WebGPU
  guarantees 256, and so it failed on the software GPU that checks the site.
  On the pygfx branch the example now reads the limit of the device and
  uses chunks of 16x16 or 8x8 pixels. The picture is identical, pixel for
  pixel, with both, also on a device made with the default limits (where the
  previous version fails). It is in the list of examples that must work.
* `anisotropy_barn_lamp`: pygfx gives every texture map a uniform buffer of
  its own, and this material reaches 13 in the fragment shader where WebGPU
  guarantees 12. The example now asks for 13 and, where the GPU does not have
  it, shows a text in the scene that says why. Dawn offers 12 on every GPU
  tried, in Chrome too, so the site shows the text; wgpu-native draws the
  lamp as before. The cause in pygfx is not fixed.
* Then the cause, in one step (the human asked for larger steps): the mesh
  shaders put the uv transforms of all texture maps of a material in one
  uniform buffer, which the maps keep up to date. The lamp needs 6 uniform
  buffers instead of 13 and draws on Dawn, pixel-identical to wgpu-native;
  the limit request in the example is reverted. pygfx's tests pass on both
  backends. On wgpu-native, 141 examples render identically before and
  after, and the other 27 differ as much as two runs of the old code do. In
  Chrome on a GPU, 197 of 200 work; the 3 left cannot work in a browser.
* Issue 3 lists every example that does not work, or did not, with the commit
  that fixed it.

## 2026-10-13 - Python starts with the gallery; the first release

Same session, continued.

* The gallery starts the interpreter by itself after it has loaded, so that
  the first example opens as the later ones do (0.1 s instead of 1.1 s
  locally).
* PyPI refused both release candidates: the publisher registered there named
  the workflow `wheels.yml`, the repository had `ci.yml`. The error message
  of PyPI lists what the run claimed, not what PyPI expects, so only the
  human could see the difference. The workflow file is renamed.
* 0.0.1 is on PyPI, with a release on GitHub; the publish job makes the
  release from now on.
* Objects were missing in the browser (most spheres of pbr2 in Safari, a
  seventh of the images of labelled_image_grid in Chrome). The reference
  picture in this repository had the holes too, and had passed as "looks
  plausible". Every WebGPU call was right and so were the buffers on the
  GPU; the positions in them were not. pygfx uses `perf_counter_ns()` as the
  version of a transform, browsers limit the resolution of that clock, and
  the second of two changes in one tick was lost. Fixed on the pygfx branch;
  all pictures of the gallery were made again, on a GPU, and looked at.

## 2026-10-13 - The website on a branch of pygfx with the fixes it needs

Same session, continued (15.4 h wall clock, 48 human prompts by now). The
human opened an example in Safari on a Mac and pasted the error; then asked
for a branch of pygfx with what needs fixing there, an issue that lists such
branches, and whether the site had them.

* Safari rejects `let tex: texture_2d<f32> = colorTex;` in pygfx's
  anti-aliasing shaders. The specification agrees with Safari; Tint and naga
  let it pass. Found by dumping the shaders natively and reading line 114.
* `hmaarrfk/pygfx@webgpu-portability`: four commits (textureSample in uniform
  control flow, the physical material within 4 bind groups, the texture view
  of ComputeShader, the `let`). Checked on wgpudawn and on wgpu-native, where
  the pictures are the same before and after. Not offered upstream: issue 2
  lists the branches of other projects and why each matters.
* The site and the pygfx job of CI now build from that branch
  (`upstream.json` has the repository too). Nine more examples work; the
  site says that pygfx has fixes on top, and no longer says "unmodified".
* Two examples got past their first error and met the next limit: 13 uniform
  buffers per stage (12 guaranteed), 1024 invocations per workgroup (256).
  The notes say that now.

## 2026-10-13 - Safari on iOS: the cause, and a Pyodide that the site patches

Same session, continued. The human ran `diagnose.html` on an iPhone five more
times, the last three from a server on the local network, which made each
round a minute instead of a deployment.

* The reports had the stack of the fatal error and never its message: an
  Error's `stack` has the message in Chrome, not in Safari. With the message
  shown it was `SuspendError: JavaScript frames found between
  WebAssembly.Suspending and WebAssembly.promising`.
* The frame numbers of the stack were mapped to names with the export table
  of `pyodide.asm.wasm` (`JsvPromise_Syncify` called by `run_sync`).
* Cause: CPython's call trampoline. Pyodide's runtime uses a JavaScript one
  when the user agent is iOS (a workaround for a WebKit bug of iOS 18.3.1),
  and JSPI cannot suspend through a JavaScript frame. Reproduced here in
  Playwright's WebKit by giving it the iPhone's user agent; gone when the
  check is removed, here and on the iPhone.
* `website/build.py` now serves the core of Pyodide itself with that check
  limited to browsers without JSPI (`IOS_TRAMPOLINE`), and the WebKit
  exception of `runner.canBlock()` is gone. All 186 examples still work in
  Chrome; the human saw the gallery work on the iPhone from the local server.
* 0.0.1rc1 did not publish (a test failed on `version_info` of a
  pre-release: fixed). 0.0.1rc2 built and tested everywhere and was refused
  by PyPI: no trusted publisher matches (owner's to configure).

## 2026-10-13 - Everything that was due: Dawn, the CI, the first release candidate

Same session, continued: the human asked for an issue to track the Safari
crash (#1), for everything out of date to be updated, and said to push the
release candidate. Totals of the whole session at this point: see the header
that `python tools/session_stats.py --markdown` prints (about 11 h wall
clock, 31 human prompts, `claude-opus-5-5` (Anthropic)).

* **Dawn** v20260929.200159 -> v20261009.190412 (`update-dawn`): one added
  feature enum in the header, nothing to adapt. Tests, pygfx's tests and the
  benchmark verified locally before the push.
* **CI** (`refresh-infra`), verified by a run on a branch (38387421642)
  before `main`: the actions at their current majors, cibuildwheel 4.3.1,
  Python 3.15 in the test matrix, puppeteer-core 25, webgpu 0.6.2, ruff
  0.17.0. cibuildwheel 4 repairs Windows wheels with delvewheel, so they now
  carry `msvcp140*.dll`; found by comparing the contents of the wheels of the
  two runs, kept, and noted in `LICENSES/README.md`.
* **0.0.1rc1** tagged on a3097e6, the newest commit whose CI was green at
  that moment (not on the commits above, which were not yet tested on `main`).
* Left as it is: `ilammy/msvc-dev-cmd@v1` (runs on a deprecated Node.js; no
  newer release exists), `ubuntu-latest` (moves to Ubuntu 26 from 2026-10-19;
  not tried ahead), FreeType 2.13.3 for the website (2.15.0 exists; the
  pictures cannot be compared on this machine right now).

## 2026-10-13 - Safari: examples without stack switching

Same session as the entry below, continued after the human ran
`diagnose.html` on an iPhone (Safari 27.0.1) and pasted the report. Totals of
the whole session at this point: 9.56 h wall clock, 4.14 h agent working, 28
human prompts, `claude-opus-5-5` (Anthropic), $60.14 at API list prices.

**What the report said.** WebGPU works, JSPI exists and works in a bare
WebAssembly module, `pyodide.ffi.can_run_sync()` is true, and the first
`pyodide.ffi.run_sync` is a fatal error of the interpreter. Every example
used it at least once: to get the GPU device.

**What changed**

* `webhost.warm()` awaits the adapter and the device before an example runs,
  so an example that only draws needs no stack switch, in any browser.
* Where blocking cannot work (`runner.canBlock()`: no JSPI, or WebKit;
  `?jspi=0` / `?jspi=1` override it), `can_run_sync` says no, so that the
  blocking API raises an exception instead of crashing the interpreter.
* `check.mjs --no-blocking` checks the site as such a browser runs it: 182 of
  the 186 working examples start without an error in Chrome that way. The
  four that need blocking read back from the GPU (`offscreen`,
  `hirez_screenshot`) or configure the device themselves (`gpu_selection`,
  `reactive_rendering`).
* `diagnose.html`: the tests that do not block run first, so that a report
  from Safari says whether the rest works; its wgpudawn step asked for a wheel
  that the site no longer has (it failed everywhere) and now uses the bundle.

**Not verified.** No Safari here: that the examples now run on the iPhone is
expected from the report, not seen. And the pictures of this check were
blank, with the previous build too (headless Chrome did not show the canvas
on this machine at the time), so "works" here is "started without an error".

## 2026-10-13 - Creating the project: package, wheels, website, maintenance

| | |
|---|---|
| Session | `7a75407f-39ea-41af-b578-d4d4c430723c` |
| When (UTC) | 2026-10-13T00:51:56+00:00 to 2026-10-13T05:17:59+00:00 |
| Duration | 4.43 h wall clock, 3.59 h agent working |
| Human prompts | 26 (1288 words) |
| Subagents | 6 |
| Model | `claude-opus-5-5` (Anthropic): 506 requests; tokens: 1,088 input, 310,952 output, 148,252,520 cache read, 3,536,259 cache write; $55.55 at API list prices |
| API-equivalent cost | $55.55 (estimate; see tools/session_stats.py) |

**What the human asked for** (paraphrased, in order)

1. Turn the declined pull request pygfx/wgpu-py#840 into a standalone, co-installable
   package `wgpudawn`: version from git tags, wheels for Windows, macOS and Linux on
   x86-64 and arm64, tested by running pygfx's test suite through a test-only `wgpu` shim.
2. Mirror wgpu-py's versions so that it is a drop-in replacement, and write skills so that
   one command keeps the project up to date.
3. Say in the README what the project is: a Dawn reference implementation after wgpu-py's
   design, maintained by AI agents.
4. Publish the Pyodide wheel too. (PyPI was pre-registered by the human.)
5. How to get around rendercanvas and pygfx importing `wgpu` by name?
6. A dedicated skill for following Dawn aggressively; versions as X.Y.Z.N.
7. A github.io site with pygfx's examples running in the browser; a skill for it; make it
   sleek and visual; find out whether imgui-bundle and PyTorch can run there.
8. Explain, per example, why it cannot run.
9. A work log with practices, in the repository, maintained by the agents.
10. Review the maintenance tasks, write a skill for each and one that runs them all.
11. Feedback on the first deployment: highlighting, aspect ratios, full screen; make the
    sun the logo.
12. Help diagnose an iPhone on which the examples spin forever.
13. Make navigating between examples fast; the pages need not be real pages.

**What was delivered**

* The package: wgpu-py 0.32.0 (+6 commits) with the Dawn backend of #840, Dawn
  v20260929.200159 linked statically, one abi3 wheel per platform (6) plus a Pyodide
  wheel; `wgpudawn.install_as_wgpu()`; 226 tests; pygfx's 354 unit tests pass on it.
  First fully green CI on all platforms: run 38335939446; with the website as it is now: run 38349679065.
* The website, https://www.markharfouche.com/wgpudawn/ : 186 of 214 pygfx examples run in
  the browser (imgui included); 14 do not work yet and 14 cannot run in a browser, each
  with its reason. One interpreter for the whole visit: 108 ms median from click to first
  frame (was 2.3 to 4.6 s). `diagnose.html` tests a browser step by step.
* Nine skills (`maintain`, `update-dawn`, `sync-upstream`, `update-website`, `ci-doctor`,
  `release`, `refresh-infra`, `triage`, `upstream-report`), `tools/maintenance_status.py`,
  `tools/update_dawn.py`, `tools/upstream_diff.py`, and this log with
  `tools/session_stats.py`.
* Commits beef83d to 8327285 on `main`. Six subagents: two research (imgui-bundle: a
  wheel for our Pyodide exists on PyPI; PyTorch: possible but not useful here), the site's
  design, native debugging of failing examples, the maintenance review, and the fast
  navigation.

**What went wrong, and how it was found**

* CI, first runs: Xcode 15 cannot compile Dawn (moved the build to macos-15); Windows could
  not load `d3dcompiler_47.dll` (`DAWN_FORCE_SYSTEM_COMPONENT_LOAD`); macOS runners lack
  timestamp queries; pytest picked up two conftests in the pygfx job. All only visible on
  the runners.
* The example checker reported 193 working examples when 186 were: GPU validation errors
  arrive asynchronously in a browser and nothing listened. Found by running the same
  examples natively. The seven are pygfx shaders and layouts that Dawn rejects per the
  WGSL and WebGPU specs.
* A push without having seen the check pass: I had cut the checker's output to two lines,
  which hid a crash at start-up that I had just introduced (binding its server to
  127.0.0.1). The website job failed; fixed in the next commit.
* The first deployment had black thumbnails, and nobody had looked: without a GPU, Chrome
  leaves a WebGPU canvas black. Two attempts to fix it on the runner failed (software
  compositing flags; reading the canvas back in the page). The pictures are now taken on a
  GPU and kept in the repository; the checker refuses a mostly black gallery.

**Open**

* No release yet: the first tag (a release candidate) is the human's to push, or to ask
  for (`/release`).
* iPhone/Safari: Pyodide reports a fatal error at the first JSPI stack switch. The site now
  avoids that switch on import and shows the error; a report from `diagnose.html` on the
  phone is needed to say more.
* Reports for pygfx (in `website/notes.json`): `textureSample` in non-uniform control flow
  in three shaders; five bind groups for some materials; a NaN constant in an example. To
  be filed upstream, with the human's go-ahead (`/upstream-report`).
* Dawn is six releases behind (`/update-dawn`); action versions and Python 3.15
  (`/refresh-infra`). See `python tools/maintenance_status.py`.
