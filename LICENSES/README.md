# Licenses of what the wheels contain

The wheels of wgpudawn statically link Dawn, which is built from source by
`tools/build_dawn.py` together with the third-party libraries that it uses.

* Dawn and Tint: BSD 3-Clause, see `DAWN-LICENSE`.
* Abseil, SPIRV-Tools, SPIRV-Headers, Vulkan-Headers, Vulkan-Utility-Libraries:
  Apache License 2.0 (Vulkan-Headers: Apache 2.0 OR MIT).
* Vulkan Memory Allocator, DirectX-Headers (Windows): MIT.

The exact set and versions are those in the `DEPS` file of the Dawn release in
`upstream.json`; their license texts are in the `third_party` directory of
Dawn's source tree.
