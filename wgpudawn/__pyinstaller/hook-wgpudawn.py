# ruff: noqa: N999

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# Init variables that PyInstaller will pick up.
hiddenimports = []
datas = []
binaries = []

# Include our resource data and binaries.
datas += collect_data_files("wgpudawn", subdir="resources")
binaries += collect_dynamic_libs("wgpudawn")

# Always include the Dawn backend. Since an import is not needed to
# load this backend, PyInstaller does not see it by itself.
hiddenimports += ["wgpudawn.backends.auto", "wgpudawn.backends.dawn"]
