"""Move wgpudawn to another Dawn release: the mechanical part.

    python tools/update_dawn.py            # the latest release of google/dawn
    python tools/update_dawn.py v20261009.190412

This downloads the headers of that release (the Emdawnwebgpu package and
Dawn's native headers, both release assets), and then:

* regenerates ``wgpudawn/_lib/webgpu_cdef.h`` and ``webgpu_native_extra_cdef.h``;
* checks that the Emdawnwebgpu header is still a subset of the native one
  (the same cdef is compiled for both), and prints what changed in the cdef;
* updates the Dawn tag (and the sha256 of the Emdawnwebgpu package) in
  ``build_cffi.py``, ``wgpudawn/_lib/__init__.py`` and ``upstream.json``.

What is left after that is not mechanical: rebuild Dawn and the extension, run
codegen, and adapt the backend to what changed. See
.claude/skills/update-dawn/SKILL.md.
"""

import difflib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB = os.path.join(ROOT, "wgpudawn", "_lib")
API = "https://api.github.com/repos/google/dawn/releases"

sys.path.insert(0, os.path.dirname(__file__))
import gen_cdef  # noqa: E402


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "wgpudawn"})
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token and "api.github.com" in url:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request) as f:
        return f.read()


def get_release(tag):
    url = f"{API}/tags/{tag}" if tag else f"{API}/latest"
    release = json.loads(fetch(url))
    assets = {a["name"]: a["browser_download_url"] for a in release["assets"]}
    tag = release["tag_name"]
    emdawn = assets.get(f"emdawnwebgpu_pkg-{tag}.zip")
    headers = [url for name, url in assets.items() if name.startswith("dawn-headers-")]
    if not emdawn or not headers:
        raise SystemExit(f"Release {tag} lacks the Emdawnwebgpu package or headers")
    return tag, emdawn, headers[0]


def sub(path, pattern, repl):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    text, n = re.subn(pattern, repl, text, flags=re.M)
    if n != 1:
        raise SystemExit(f"Expected one match of {pattern!r} in {path}, got {n}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_and_diff(name, new):
    path = os.path.join(LIB, name)
    with open(path, encoding="utf-8") as f:
        old = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    diff = list(
        difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
    )
    changed = [ln for ln in diff if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
    print(f"\n## {name}: {len(changed)} changed lines")
    for line in changed[:200]:
        print(line)
    if len(changed) > 200:
        print(f"... and {len(changed) - 200} more (see git diff)")


def main():
    tag, emdawn_url, headers_url = get_release(sys.argv[1] if sys.argv[1:] else None)
    with open(os.path.join(ROOT, "upstream.json"), encoding="utf-8") as f:
        upstream = json.load(f)
    print(f"Dawn: {upstream['dawn']['tag']} -> {tag}")

    work = os.path.join(ROOT, "build", "dawn-update", tag)
    os.makedirs(work, exist_ok=True)
    emdawn_zip = fetch(emdawn_url)
    sha256 = hashlib.sha256(emdawn_zip).hexdigest()
    zipfile.ZipFile(io.BytesIO(emdawn_zip)).extractall(work)
    with tarfile.open(fileobj=io.BytesIO(fetch(headers_url))) as tar:
        tar.extractall(work, filter="data")
    emdawn_h = os.path.join(
        work, "emdawnwebgpu_pkg", "webgpu", "include", "webgpu", "webgpu.h"
    )
    native_h = os.path.join(work, "dawn-headers", "include", "dawn", "webgpu.h")

    print("\n## Emdawnwebgpu's header (A) versus the native header (B)")
    print("## There must be nothing 'only in A', and nothing INCOMPATIBLE.")
    gen_cdef.diff(emdawn_h, native_h)

    write_and_diff("webgpu_cdef.h", gen_cdef.make_cdef(emdawn_h))
    write_and_diff(
        "webgpu_native_extra_cdef.h",
        gen_cdef.make_native_extra_cdef(native_h, emdawn_h),
    )

    sub(
        os.path.join(ROOT, "build_cffi.py"), r'^DAWN_TAG = ".*"$', f'DAWN_TAG = "{tag}"'
    )
    sub(
        os.path.join(ROOT, "build_cffi.py"),
        r'^EMDAWN_ZIP_SHA256 = ".*"$',
        f'EMDAWN_ZIP_SHA256 = "{sha256}"',
    )
    sub(
        os.path.join(LIB, "__init__.py"),
        r'^dawn_version = ".*"$',
        f'dawn_version = "{tag}"',
    )
    upstream["dawn"]["tag"] = tag
    with open(os.path.join(ROOT, "upstream.json"), "w", encoding="utf-8") as f:
        json.dump(upstream, f, indent=2)
        f.write("\n")
    subprocess.call(["git", "-C", ROOT, "status", "--short"])


if __name__ == "__main__":
    main()
