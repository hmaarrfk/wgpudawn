# Licenses of what the wheels contain

The wheels of wgpudawn statically link Dawn, which is built from source by
`tools/build_dawn.py` together with the third-party libraries that it compiles
in. Their license texts are in this directory, and are part of every wheel:

| Component | License | Text |
|---|---|---|
| Dawn and Tint | BSD 3-Clause | `DAWN-LICENSE` |
| Abseil | Apache 2.0 | `ABSEIL-LICENSE` |
| SPIRV-Tools | Apache 2.0 | `SPIRV-TOOLS-LICENSE` |
| SPIRV-Headers | MIT-style (Khronos) | `SPIRV-HEADERS-LICENSE` |
| Vulkan-Headers | Apache 2.0 OR MIT | `VULKAN-HEADERS-LICENSE.md` |
| Vulkan-Utility-Libraries | Apache 2.0 | `VULKAN-UTILITY-LIBRARIES-LICENSE.md` |

These are the libraries that the build of the Dawn release in `upstream.json`
compiles (the directories under `third_party/` in its build tree). When Dawn
is updated, compare that list and these texts with the new release (the
`update-dawn` skill has the step).

The Windows wheels also contain Microsoft's C++ runtime (`msvcp140.dll`,
`msvcp140_atomic_wait.dll`, in `wgpudawn.libs/`), which `delvewheel` copies
from the build machine (the default repair step of cibuildwheel 4). These are
redistributable files of Visual Studio, under Microsoft's terms for them.
