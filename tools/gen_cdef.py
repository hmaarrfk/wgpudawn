"""Generate the cffi cdef for wgpu_dawn from a webgpu.h, and diff two headers.

The cdef is generated from Emdawnwebgpu's ``webgpu.h``. At the same Dawn tag
this header is a strict subset of Dawn's native ``webgpu.h`` (see ``diff``), so
the same cdef, and therefore the same compiled binding layer and the same Python
code, works for both targets. Because cffi runs in API (out-of-line) mode, the C
compiler checks the cdef against the real header of each target at build time
(struct layouts, enum values, function signatures); constants are declared as
``...`` so they take the value of the target (e.g. ``WGPU_STRLEN`` is
``SIZE_MAX``, which differs between wasm32 and 64-bit native).

Usage::

    python gen_cdef.py cdef path/to/emdawnwebgpu_pkg/webgpu/include/webgpu/webgpu.h > ../src/wgpu_dawn/webgpu_cdef.h
    python gen_cdef.py native-extra path/to/dawn/webgpu.h path/to/emdawn/webgpu.h > ../src/wgpu_dawn/webgpu_native_extra_cdef.h
    python gen_cdef.py diff path/to/emdawn/webgpu.h path/to/dawn/webgpu.h
"""

import re
import subprocess
import sys


def make_cdef(header, cc="cc"):
    src = open(header).read()
    consts = sorted(set(re.findall(r"^#define (WGPU_[A-Z0-9_]+) \((.*)\)$", src, re.M)))
    # Integer constants only (cffi's "..." defines are integers)
    consts = [c for c, v in consts if not c.endswith("_INIT") and "NAN" not in v]
    body = re.sub(r"^#include .*$", "", src, flags=re.M)
    # dawn/webgpu.h redirects to the Emscripten header when __EMSCRIPTEN__ is set
    body = body.replace("#ifdef __EMSCRIPTEN__", "#if 0")
    out = subprocess.check_output(
        [cc, "-E", "-P", "-x", "c", "-", "-DWGPU_SKIP_PROCS"], input=body.encode()
    ).decode()
    text = "\n".join(ln for ln in out.splitlines() if ln.strip())
    text = re.sub(r"__attribute__\(\(.*?\)\)\s*", "", text)
    lines = [f"#define {c} ..." for c in consts]
    lines.append(text)
    # One Python entry point per callback type, used by the backend to receive
    # all async results (cffi "extern Python": no runtime code generation, which
    # is what makes callbacks work under WebAssembly).
    for name, args in re.findall(
        r"^typedef void \(\*(WGPU\w+Callback)\)\((.*?)\)\s*;", text, re.M
    ):
        lines.append(f'extern "Python" void _wgpu_dawn_{name}({args});')
    return "\n".join(lines) + "\n"


# Native-only declarations that wgpudawn.backends.dawn uses, in dependency
# order: the window-system surface sources (_helpers.py), and Dawn's shared
# texture memory and shared fences (extras.py). None of it exists in
# Emdawnwebgpu's header, so it is compiled into native builds only
# (build_cffi.py). A chained struct brings its WGPUSType member and the
# feature names their WGPUFeatureName member as ``static const int`` with the
# value of the header: cffi checks that value against the real header at build
# time, and codegen reads it (codegen/hparser.py).
NATIVE_EXTRA_HANDLES = [  # typedef struct XImpl* X;
    "WGPUSharedTextureMemory",
    "WGPUSharedFence",
]
NATIVE_EXTRA_ENUMS = [
    "WGPUSharedFenceType",
]
NATIVE_EXTRA_STRUCTS = [
    "WGPUSurfaceSourceXlibWindow",
    "WGPUSurfaceSourceWaylandSurface",
    "WGPUSurfaceSourceXCBWindow",
    "WGPUSurfaceSourceMetalLayer",
    "WGPUSurfaceSourceWindowsHWND",
    "WGPUSharedTextureMemoryDescriptor",
    "WGPUSharedTextureMemoryIOSurfaceDescriptor",
    "WGPUSharedTextureMemoryDmaBufPlane",
    "WGPUSharedTextureMemoryDmaBufDescriptor",
    "WGPUSharedTextureMemoryProperties",
    "WGPUSharedTextureMemoryBeginAccessDescriptor",
    "WGPUSharedTextureMemoryEndAccessState",
    "WGPUSharedTextureMemoryVkImageLayoutBeginState",
    "WGPUSharedTextureMemoryVkImageLayoutEndState",
    "WGPUSharedFenceDescriptor",
    "WGPUSharedFenceExportInfo",
    "WGPUSharedFenceMTLSharedEventDescriptor",
    "WGPUSharedFenceMTLSharedEventExportInfo",
    "WGPUSharedFenceSyncFDDescriptor",
    "WGPUSharedFenceSyncFDExportInfo",
    "WGPUSharedFenceVkSemaphoreOpaqueFDDescriptor",
    "WGPUSharedFenceVkSemaphoreOpaqueFDExportInfo",
]
NATIVE_EXTRA_FUNCTIONS = [
    "wgpuDeviceImportSharedTextureMemory",
    "wgpuDeviceImportSharedFence",
    "wgpuSharedTextureMemoryGetProperties",
    "wgpuSharedTextureMemoryCreateTexture",
    "wgpuSharedTextureMemoryBeginAccess",
    "wgpuSharedTextureMemoryEndAccess",
    "wgpuSharedTextureMemoryEndAccessStateFreeMembers",
    "wgpuSharedTextureMemoryIsDeviceLost",
    "wgpuSharedTextureMemoryAddRef",
    "wgpuSharedTextureMemoryRelease",
    "wgpuSharedFenceExportInfo",
    "wgpuSharedFenceAddRef",
    "wgpuSharedFenceRelease",
]
NATIVE_EXTRA_ENUM_MEMBERS = [  # of enums that the shared cdef has
    "WGPUFeatureName_SharedTextureMemoryIOSurface",
    "WGPUFeatureName_SharedTextureMemoryDmaBuf",
    "WGPUFeatureName_SharedFenceMTLSharedEvent",
    "WGPUFeatureName_SharedFenceSyncFD",
    "WGPUFeatureName_SharedFenceVkSemaphoreOpaqueFD",
]


def _find(pattern, text, what):
    m = re.search(pattern, text, re.M | re.S)
    if m is None:
        raise ValueError(f"{what} not found in the native header")
    return m


def _enum_member_line(member, native, shared):
    """``static const int MEMBER = value;`` unless the shared cdef has it."""
    if re.search(r"\b%s\b" % member, shared):
        return None
    value = _find(r"^\s*%s = (0x[0-9A-Fa-f]+|\d+)," % member, native, member).group(1)
    return f"static const int {member} = {value};"


def make_native_extra_cdef(native_header, shared_header, cc="cc"):
    """Extra cdef for native builds only (not available in Emdawnwebgpu)."""
    text = make_cdef(native_header, cc)
    shared = make_cdef(shared_header, cc)
    lines = []
    for name in NATIVE_EXTRA_HANDLES:
        lines.append(f"typedef struct {name}Impl* {name};")
    for name in NATIVE_EXTRA_ENUMS:
        m = _find(r"^typedef enum %s \{.*?^\} %s\s*;" % (name, name), text, name)
        lines.append(m.group(0))
    for name in NATIVE_EXTRA_STRUCTS:
        m = _find(r"^typedef struct %s \{.*?^\} %s\s*;" % (name, name), text, name)
        lines.append(m.group(0))
        # A chained struct's sType: a member of WGPUSType, which in the shared
        # cdef only has the members of the Emdawnwebgpu header.
        if re.search(r"WGPUChainedStruct(Out)? chain;", m.group(0)):
            line = _enum_member_line(f"WGPUSType_{name[len('WGPU') :]}", text, shared)
            if line:
                lines.append(line)
    for name in NATIVE_EXTRA_FUNCTIONS:
        m = _find(r"^[^\n]*\b%s\([^\n]*\)\s*;" % name, text, name)
        lines.append(" ".join(m.group(0).split()))
    for member in NATIVE_EXTRA_ENUM_MEMBERS:
        line = _enum_member_line(member, text, shared)
        if line:
            lines.append(line)
    return "\n".join(lines) + "\n"


def declarations(cdef):
    from cffi import FFI

    ffi = FFI()
    ffi.cdef(cdef)
    return ffi._parser._declarations


def describe(tp):
    if not hasattr(tp, "_get_c_name"):
        return repr(tp)
    name = type(tp).__name__
    if name in ("StructType", "UnionType"):
        return [
            (n, t._get_c_name())
            for n, t in zip(tp.fldnames or (), tp.fldtypes or (), strict=True)
        ]
    if name == "EnumType":
        return list(zip(tp.enumerators, tp.enumvalues, strict=True))
    return tp._get_c_name()


def diff(header_a, header_b):
    a = declarations(make_cdef(header_a))
    b = declarations(make_cdef(header_b))
    only_a = sorted(k for k in a if k not in b)
    only_b = sorted(k for k in b if k not in a)
    print(f"declarations: A={len(a)} B={len(b)} common={len(set(a) & set(b))}")
    print(f"only in A ({len(only_a)}):", " ".join(only_a))
    print(f"only in B ({len(only_b)})")
    for k in sorted(set(a) & set(b)):
        da, db = describe(a[k][0]), describe(b[k][0])
        if da == db:
            continue
        if isinstance(da, list) and isinstance(db, list):
            removed, added = set(da) - set(db), set(db) - set(da)
            kind = "B adds members" if not removed else "INCOMPATIBLE"
            print(f"  {k}: {kind}; A-B={sorted(removed)} B-A: {len(added)} items")
        else:
            print(f"  {k}: INCOMPATIBLE\n    A: {da}\n    B: {db}")


if __name__ == "__main__":
    if sys.argv[1] == "cdef":
        sys.stdout.write(make_cdef(sys.argv[2]))
    elif sys.argv[1] == "native-extra":
        sys.stdout.write(make_native_extra_cdef(sys.argv[2], sys.argv[3]))
    elif sys.argv[1] == "diff":
        diff(sys.argv[2], sys.argv[3])
