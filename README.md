# wgpudawn

WebGPU for Python, on [Dawn](https://dawn.googlesource.com/dawn).

`wgpudawn` is the API of [wgpu-py](https://github.com/pygfx/wgpu-py) with
Dawn (Google's WebGPU implementation, the one in Chrome) as its backend,
instead of wgpu-native.

> **What this project is.** It only aims to provide a Dawn reference
> implementation that follows the great architecture and design of wgpu-py,
> from the [pygfx/wgpu-py](https://github.com/pygfx/wgpu-py) project. All
> credit for the API, the design and most of the code goes to its authors.
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
Dawn's Emdawnwebgpu) and pygfx, unmodified. It needs a browser with WebGPU and
JSPI, such as a recent Chrome or Edge. Every example is run in headless Chrome
when the site is built; the gallery shows what works and what does not.

## Status

Early. The wgpu-py tests that do not depend on wgpu-native specifics pass, and
so does the unit test suite of [pygfx](https://github.com/pygfx/pygfx) (see
below).

Differences with wgpu-py:

* Shaders are compiled by Tint, which follows the WGSL spec strictly; naga
  (wgpu-native) accepts some shaders that Tint rejects.
* No wgpu-native extras (`wgpu.backends.wgpu_native.extras`: GLSL shaders,
  pipeline statistics queries, multi-draw-indirect-count, ...), and no
  wgpu-native specific features and limits. Dawn has its own non-standard
  features, e.g. `unorm16-texture-formats`.
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
  (`webgpu_cdef.h`) is generated from Dawn's `webgpu.h` by `tools/gen_cdef.py`.
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
