#!/usr/bin/env python3
import os
import sysconfig

from setuptools import setup


# Loads _version.py module without importing the whole package.
def get_version_and_cmdclass(pkg_path):
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location("version", os.path.join(pkg_path, "_version.py"))
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.__version__, module.get_cmdclass(pkg_path)


version, cmdclass = get_version_and_cmdclass("wgpudawn")

# The extension uses the limited API (cffi does that), so natively one wheel
# per platform works for all supported Python versions.
plat = os.environ.get("_PYTHON_HOST_PLATFORM", "") or sysconfig.get_platform()
options = {}
if not plat.startswith(("emscripten", "pyodide")):
    options["bdist_wheel"] = {"py_limited_api": "cp311"}

setup(
    version=version,
    cmdclass=cmdclass,
    cffi_modules=["build_cffi.py:ffibuilder"],
    options=options,
)
