"""Build Dawn from source, as a static library, for linking into wgpudawn.

The wheels of wgpudawn contain Dawn itself (statically linked into the
``wgpudawn._lib._wgpu_dawn`` extension), so that they have no dependencies
other than the GPU drivers of the system. This script builds the pinned Dawn
release (``DAWN_TAG`` in ``build_cffi.py``) and installs it into a prefix,
which is then passed to the build of wgpudawn via ``DAWN_PREFIX``::

    python tools/build_dawn.py --prefix /path/to/dawn-prefix
    DAWN_PREFIX=/path/to/dawn-prefix pip install .

It needs git, CMake (>= 3.22), Ninja and a C++20 compiler. On Linux it also
needs the headers of X11, xcb and Wayland (the libraries are loaded at
runtime, only when a surface for that window system is created).

The script does nothing if the prefix already contains this Dawn release, so
it is cheap to call from a CI job that caches the prefix.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DAWN_URL = "https://github.com/google/dawn.git"


def get_dawn_tag():
    with open(os.path.join(ROOT, "build_cffi.py")) as f:
        return re.search(r'^DAWN_TAG = "(.+?)"', f.read(), re.M).group(1)


def run(cmd, **kwargs):
    print("+", " ".join(cmd), flush=True)
    subprocess.check_call(cmd, **kwargs)


def get_cmake_args(prefix):
    args = [
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DCMAKE_POSITION_INDEPENDENT_CODE=ON",
        "-DCMAKE_INSTALL_LIBDIR=lib",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DDAWN_FETCH_DEPENDENCIES=ON",
        "-DDAWN_ENABLE_INSTALL=ON",
        # One static library with everything (Dawn, Tint, SPIRV-Tools, Abseil, ...)
        "-DDAWN_BUILD_MONOLITHIC_LIBRARY=STATIC",
        "-DDAWN_BUILD_SAMPLES=OFF",
        "-DDAWN_BUILD_TESTS=OFF",
        "-DDAWN_BUILD_PROTOBUF=OFF",
        "-DDAWN_USE_GLFW=OFF",
        "-DTINT_BUILD_TESTS=OFF",
        "-DTINT_BUILD_CMD_TOOLS=OFF",
        "-DTINT_BUILD_IR_BINARY=OFF",
        # The OpenGL backends are not built: they need EGL/ANGLE, and are not
        # WebGPU-conformant. Vulkan, Metal and D3D11/12 are (per platform).
        "-DDAWN_ENABLE_DESKTOP_GL=OFF",
        "-DDAWN_ENABLE_OPENGLES=OFF",
        "-DTINT_BUILD_GLSL_WRITER=OFF",
        "-DTINT_BUILD_GLSL_VALIDATOR=OFF",
    ]
    if sys.platform.startswith("linux"):
        args += ["-DDAWN_USE_X11=ON", "-DDAWN_USE_WAYLAND=ON"]
    if sys.platform.startswith("win"):
        # Use the same (dynamic, release) C runtime as CPython extensions
        args += ["-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreadedDLL"]
    return args


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", required=True, help="Where to install Dawn")
    parser.add_argument(
        "--work-dir",
        default=os.path.join(ROOT, "build", "dawn"),
        help="Where to clone and build Dawn (default: build/dawn)",
    )
    parser.add_argument("--jobs", "-j", type=int, default=0)
    parser.add_argument(
        "--keep", action="store_true", help="Keep the source and build directories"
    )
    args, extra_cmake_args = parser.parse_known_args()

    tag = get_dawn_tag()
    prefix = os.path.abspath(args.prefix)
    stamp = os.path.join(prefix, "DAWN_VERSION")
    if os.path.isfile(stamp) and open(stamp).read().strip() == tag:
        print(f"Dawn {tag} is already installed in {prefix}")
        return

    src = os.path.join(os.path.abspath(args.work_dir), "src")
    build = os.path.join(os.path.abspath(args.work_dir), "out")
    if not os.path.isdir(os.path.join(src, ".git")):
        os.makedirs(os.path.dirname(src), exist_ok=True)
        run(["git", "clone", "--depth", "1", "--branch", tag, DAWN_URL, src])

    cmake_args = ["cmake", "-S", src, "-B", build, "-G", "Ninja"]
    cmake_args += get_cmake_args(prefix) + extra_cmake_args
    run(cmake_args)
    # The default target: the install step needs more than just webgpu_dawn
    build_cmd = ["cmake", "--build", build]
    if args.jobs:
        build_cmd += ["--parallel", str(args.jobs)]
    run(build_cmd)
    if os.path.isdir(prefix):
        # Empty it, rather than remove it: it can be a mount point
        for name in os.listdir(prefix):
            path = os.path.join(prefix, name)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    run(["cmake", "--install", build])
    with open(stamp, "w") as f:
        f.write(tag + "\n")
    # The license texts of Dawn and of what is linked into it, for the wheels
    shutil.copy(os.path.join(src, "LICENSE"), os.path.join(prefix, "LICENSE.dawn"))

    if not args.keep:
        shutil.rmtree(args.work_dir, ignore_errors=True)
    print(f"Installed Dawn {tag} in {prefix}")


if __name__ == "__main__":
    main()
