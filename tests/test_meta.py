"""Test that the versions that are recorded in several places are consistent."""

import json
import os
import re

import pytest

import wgpudawn
from testutils import run_tests

ROOT = os.path.abspath(os.path.join(__file__, "..", ".."))

if not os.path.isfile(os.path.join(ROOT, "upstream.json")):
    pytest.skip("Not running from the repository", allow_module_level=True)


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_wgpu_py_version():
    upstream = json.loads(read("upstream.json"))
    version = upstream["wgpu-py"]["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert len(upstream["wgpu-py"]["commit"]) == 40

    assert wgpudawn.wgpu_py_version == version
    # The test-only stand-in for wgpu-py has the version of the real thing
    shim = read("tests", "wgpu_shim", "pyproject.toml")
    assert f'\nversion = "{version}"\n' in shim


def test_dawn_version():
    tag = json.loads(read("upstream.json"))["dawn"]["tag"]
    assert f'\nDAWN_TAG = "{tag}"\n' in read("build_cffi.py")

    import wgpudawn.backends.dawn as dawn

    assert "v" + dawn.__version__ == tag


def test_version():
    assert isinstance(wgpudawn.__version__, str)
    assert all(isinstance(i, int) for i in wgpudawn.version_info[:3])
    # Also for the versions that tags give: pre-releases and X.Y.Z.N
    for version, info in [
        ("0.32.0.1", (0, 32, 0, 1)),
        ("0.0.1rc1", (0, 0, 1, "rc1")),
        ("0.0.1.dev3+g1234abc", (0, 0, 1, "dev3")),
        ("0.0.0+g1234abc.dirty", (0, 0, 0)),
    ]:
        assert wgpudawn._version_info(version) == info


if __name__ == "__main__":
    run_tests(globals())
