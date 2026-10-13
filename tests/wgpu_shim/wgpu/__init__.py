"""A stand-in for wgpu-py, for testing only: ``import wgpu`` gives wgpudawn.

This is ``wgpudawn.install_as_wgpu()`` in the form of a package named
``wgpu``, so that it also satisfies the requirement on wgpu-py of libraries
such as pygfx, and their test suites run on wgpudawn unmodified.

It is not shipped with wgpudawn: wgpudawn and wgpu-py are co-installable, and
this package takes the place of wgpu-py.
"""

import wgpudawn

wgpudawn.install_as_wgpu()
