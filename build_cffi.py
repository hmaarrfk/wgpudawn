"""cffi (API / out-of-line mode) build script for ``wgpudawn._lib._wgpu_dawn``.

The same cdef (wgpudawn/_lib/webgpu_cdef.h, generated from webgpu.h) is
compiled for two targets:

* native: linked against Dawn (``webgpu_dawn``). Set ``DAWN_PREFIX`` to the
  install prefix of Dawn; it defaults to ``$CONDA_PREFIX`` / ``sys.prefix``.
  If the prefix has a static library (as made by ``tools/build_dawn.py``, and
  as in Dawn's release archives), Dawn is linked into the extension, which is
  what the wheels do. Otherwise the shared library is used.
* Pyodide (``pyodide build``): compiled with Emdawnwebgpu, Dawn's webgpu.h
  implementation on top of the browser's ``navigator.gpu``. The pinned
  Emdawnwebgpu release is downloaded unless ``EMDAWNWEBGPU_PKG`` points to an
  extracted ``emdawnwebgpu_pkg`` directory.
"""

import hashlib
import io
import os
import re
import subprocess
import sys
import sysconfig
import urllib.request
import zipfile

from cffi import FFI
from cffi import recompiler as _cffi_recompiler

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "wgpudawn", "_lib")
BUILD = os.path.join(HERE, "build", "wgpudawn_gen")
MODULE_NAME = "wgpudawn._lib._wgpu_dawn"

# The Dawn release that the cdef was generated from. Native builds must link
# against the same release (tools/build_dawn.py builds it).
DAWN_TAG = "v20260929.200159"
EMDAWN_ZIP_SHA256 = "d697687e82b7377fc63f162fff0ef1cc5f025828aa4ff6ec4ac52566c949fe5f"
EMDAWN_URL = (
    f"https://github.com/google/dawn/releases/download/{DAWN_TAG}/"
    f"emdawnwebgpu_pkg-{DAWN_TAG}.zip"
)


def is_emscripten():
    plat = os.environ.get("_PYTHON_HOST_PLATFORM", "") or sysconfig.get_platform()
    return plat.startswith("emscripten") or plat.startswith("pyodide")


def get_emdawnwebgpu_pkg():
    pkg = os.environ.get("EMDAWNWEBGPU_PKG")
    if pkg:
        return pkg
    pkg = os.path.join(HERE, "build", "emdawnwebgpu_pkg")
    if not os.path.isdir(pkg):
        print(f"Downloading {EMDAWN_URL}")
        data = urllib.request.urlopen(EMDAWN_URL).read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != EMDAWN_ZIP_SHA256:
            raise RuntimeError(f"Unexpected sha256 {digest} for {EMDAWN_URL}")
        zipfile.ZipFile(io.BytesIO(data)).extractall(os.path.join(HERE, "build"))
    return pkg


cdef = open(os.path.join(SRC, "webgpu_cdef.h")).read()
cdef += "\nint wgpu_dawn_install(const char* code);\n"
if not is_emscripten():
    cdef += open(os.path.join(SRC, "webgpu_native_extra_cdef.h")).read()
    cdef += (
        "\nsize_t wgpu_dawn_enumerate_adapters(WGPUInstance instance,"
        " WGPUAdapter * adapters, size_t max_count);\n"
    )

# Native: true adapter enumeration. webgpu.h has no way to enumerate adapters
# (wgpuInstanceRequestAdapter only returns the "best" one, so e.g. lavapipe is
# never returned on a machine with a GPU), but Dawn's native C++ API does.
NATIVE_PREAMBLE = """
#include <webgpu/webgpu.h>
#include <dawn/native/DawnNative.h>

static int wgpu_dawn_install(const char* code) { (void)code; return 0; }

// Get all adapters of the instance (all backends). Fills up to max_count
// adapters (each with a new reference), and returns the total count.
static size_t wgpu_dawn_enumerate_adapters(
    WGPUInstance instance, WGPUAdapter* adapters, size_t max_count) {
  // A WGPUInstance is a dawn::native::InstanceBase*. The wrapper adds a ref
  // and releases it again when it goes out of scope.
  dawn::native::Instance wrapper(
      reinterpret_cast<dawn::native::InstanceBase*>(instance));
  std::vector<dawn::native::Adapter> found =
      wrapper.EnumerateAdapters(static_cast<const WGPURequestAdapterOptions*>(nullptr));
  for (size_t i = 0; i < found.size() && i < max_count; i++) {
    adapters[i] = found[i].Get();
    wgpuAdapterAddRef(adapters[i]);
  }
  return found.size();
}
"""

ffibuilder = FFI()
ffibuilder.cdef(cdef)


def find_dawn():
    """Find Dawn. Returns (include_dir, lib_dir, is_static)."""
    candidates = [
        os.environ.get("DAWN_PREFIX"),
        os.environ.get("CONDA_PREFIX"),
        sys.prefix,
    ]
    static_names = ("libwebgpu_dawn.a", "webgpu_dawn_static.lib")
    shared_names = ("libwebgpu_dawn.so", "libwebgpu_dawn.dylib", "webgpu_dawn.dll")
    for prefix in candidates:
        if not prefix:
            continue
        for sub in ("", "Library"):  # conda on Windows uses <prefix>/Library
            base = os.path.join(prefix, sub)
            include_dir = os.path.join(base, "include")
            if not os.path.isfile(os.path.join(include_dir, "webgpu", "webgpu.h")):
                continue
            for libsub in ("lib", "lib64"):
                lib_dir = os.path.join(base, libsub)
                if not os.path.isdir(lib_dir):
                    continue
                names = set(os.listdir(lib_dir))
                bin_names = set()
                if os.path.isdir(os.path.join(base, "bin")):
                    bin_names = set(os.listdir(os.path.join(base, "bin")))
                if names.intersection(shared_names) or bin_names.intersection(
                    shared_names
                ):
                    return include_dir, lib_dir, False
                if names.intersection(static_names) or "webgpu_dawn.lib" in names:
                    return include_dir, lib_dir, True
    raise RuntimeError(
        "Could not find Dawn (include/webgpu/webgpu.h and the webgpu_dawn library). "
        "Build it with 'python tools/build_dawn.py --prefix <dir>' and set DAWN_PREFIX=<dir>."
    )


def get_native_build_args():
    try:
        include_dir, lib_dir, is_static = find_dawn()
    except RuntimeError as err:
        # Not fatal here: this module is also loaded for commands that do not
        # compile anything (e.g. sdist). Compiling will fail on webgpu.h.
        print(f"WARNING: {err}", file=sys.stderr)
        return {"libraries": ["webgpu_dawn"]}
    print(f"Using Dawn ({'static' if is_static else 'shared'}) from {lib_dir}")
    kwargs = {
        "include_dirs": [include_dir],
        "library_dirs": [lib_dir],
        "libraries": ["webgpu_dawn"],
        "extra_link_args": [],
    }
    if sys.platform.startswith("win"):
        kwargs["extra_compile_args"] = ["/std:c++20", "/O2", "/DNDEBUG"]
        if is_static:
            # What Dawn's own CMake config links to (DawnTargets.cmake)
            kwargs["libraries"] += ["user32", "onecore_apiset", "dxguid"]
    elif sys.platform == "darwin":
        kwargs["extra_compile_args"] = ["-std=c++20", "-O2", "-DNDEBUG"]
        if is_static:
            for name in (
                "CoreFoundation",
                "Foundation",
                "IOSurface",
                "QuartzCore",
                "Cocoa",
                "IOKit",
                "Metal",
            ):
                kwargs["extra_link_args"] += ["-framework", name]
            # Don't export Dawn's symbols from the extension
            kwargs["extra_link_args"] += [
                "-Wl,-dead_strip",
                "-Wl,-exported_symbol,_PyInit__wgpu_dawn",
            ]
        else:
            kwargs["runtime_library_dirs"] = [lib_dir]
    else:
        kwargs["extra_compile_args"] = ["-std=c++20", "-O2", "-DNDEBUG"]
        if is_static:
            kwargs["libraries"] += ["dl", "rt", "pthread"]
            # Don't export Dawn's symbols from the extension, and drop what is unused
            kwargs["extra_link_args"] += [
                "-Wl,--exclude-libs,ALL",
                "-Wl,--gc-sections",
                "-Wl,--strip-all",
            ]
        else:
            kwargs["runtime_library_dirs"] = [lib_dir]
    return kwargs


if is_emscripten():
    pkg = get_emdawnwebgpu_pkg()
    os.makedirs(BUILD, exist_ok=True)
    subprocess.check_call(
        [
            sys.executable,
            os.path.join(HERE, "tools", "gen_emdawn_glue.py"),
            pkg,
            os.path.join(SRC, "emdawn_glue.js"),
            os.path.join(BUILD, "emdawn_cpp_funcs.h"),
            os.environ.get("EMCC", "emcc"),
        ]
    )
    ffibuilder.set_source(
        MODULE_NAME,
        '#include <webgpu/webgpu.h>\nextern "C" int wgpu_dawn_install(const char* code);\n',
        source_extension=".cpp",
        sources=[os.path.relpath(os.path.join(SRC, "emdawn_glue.cpp"), os.getcwd())],
        include_dirs=[
            os.path.join(pkg, "webgpu", "include"),
            os.path.join(pkg, "webgpu", "src"),
            BUILD,
        ],
        extra_compile_args=["-std=c++20", "-O2", "-DNDEBUG"],
    )
else:
    ffibuilder.set_source(
        MODULE_NAME,
        NATIVE_PREAMBLE,
        source_extension=".cpp",
        **get_native_build_args(),
    )


# %% Keep the GIL for cheap, non-blocking calls
#
# In API mode, cffi releases the GIL (and saves/restores errno) around every C
# call. For calls that record into a pass or bundle encoder, that is a large
# part of their cost (about 15 ns of a ~45 ns binding call), and pointless:
# they are cheap, never block, and never call back into Python. So for these
# functions only, we drop the GIL release from the C source that cffi
# generates. All other functions (waits, present, submit, object creation,
# ...) keep releasing the GIL. The Cython-based Dawn backend makes the same
# trade-off.

KEEP_GIL_PREFIXES = (
    "wgpuRenderPassEncoder",
    "wgpuComputePassEncoder",
    "wgpuRenderBundleEncoder",
)
_GIL_LINES = (
    "  Py_BEGIN_ALLOW_THREADS\n",
    "  _cffi_restore_errno();\n",
    "  _cffi_save_errno();\n",
    "  Py_END_ALLOW_THREADS\n",
)


def keep_gil_for_hot_calls(c_source):
    """Remove the GIL release from the cffi wrappers of the hot functions."""
    out = []
    current = None
    n_patched = 0
    for line in c_source.splitlines(keepends=True):
        m = re.match(r"_cffi_f_(\w+)\(PyObject \*self", line)
        if m:
            current = m.group(1) if m.group(1).startswith(KEEP_GIL_PREFIXES) else None
        elif line.startswith("}"):
            current = None
        if current is not None and line in _GIL_LINES:
            n_patched += line == _GIL_LINES[0]
            continue
        out.append(line)
    if n_patched == 0:  # e.g. cffi changed its output; still correct, just slower
        print("Warning: keep_gil_for_hot_calls() did not patch any functions")
    return "".join(out), n_patched


_ori_make_c_source = _cffi_recompiler.make_c_source


def _make_c_source(ffi, module_name, preamble, target_c_file, verbose=False):
    if ffi is not ffibuilder:
        return _ori_make_c_source(ffi, module_name, preamble, target_c_file, verbose)
    f = io.StringIO()
    _ori_make_c_source(ffi, module_name, preamble, f, verbose)
    source, n = keep_gil_for_hot_calls(f.getvalue())
    print(f"Keeping the GIL in {n} hot encoder functions")
    try:
        with open(target_c_file) as f1:
            if f1.read() == source:
                return False
    except OSError:
        pass
    with open(target_c_file, "w") as f1:
        f1.write(source)
    return True


# Used by both cffi's setuptools integration and ffibuilder.compile()
_cffi_recompiler.make_c_source = _make_c_source


if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
