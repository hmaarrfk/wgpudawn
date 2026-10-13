"""Show what changed in wgpu-py since the commit that wgpudawn was last synced to.

wgpudawn is derived from wgpu-py; ``upstream.json`` records the wgpu-py commit
that the current code corresponds to. This script fetches wgpu-py (into
``build/upstream/wgpu-py``) and prints the changes between that commit and a
target ref, limited to what is relevant for wgpudawn::

    python tools/upstream_diff.py              # summary, up to the latest release tag
    python tools/upstream_diff.py main         # summary, up to main
    python tools/upstream_diff.py v0.33.0 --diff          # full diff
    python tools/upstream_diff.py v0.33.0 --diff wgpu/_classes.py tests

See .claude/skills/sync-upstream/SKILL.md for how the changes are ported.
"""

import argparse
import json
import os
import subprocess

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CLONE = os.path.join(ROOT, "build", "upstream", "wgpu-py")

# The parts of wgpu-py that wgpudawn has a counterpart for
RELEVANT = ["wgpu", "codegen", "tests", "examples", "conftest.py", "pyproject.toml"]
# ... except these, which are specific to the wgpu-native backend, but which
# often need an equivalent change in wgpudawn/backends/dawn (listed separately)
BACKEND = ["wgpu/backends/wgpu_native"]
IGNORED = ["wgpu/backends/js_webgpu", "wgpu/resources/*.h", "wgpu/_version.py"]


def git(*args, capture=True):
    cmd = ["git", "-C", CLONE, *args]
    if capture:
        return subprocess.check_output(cmd, text=True).strip()
    subprocess.check_call(cmd)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", nargs="?", help="Tag or branch (default: latest tag)")
    parser.add_argument("--diff", action="store_true", help="Print the full diff")
    parser.add_argument("paths", nargs="*", help="Limit --diff to these paths")
    args = parser.parse_args()

    with open(os.path.join(ROOT, "upstream.json")) as f:
        upstream = json.load(f)["wgpu-py"]

    if not os.path.isdir(os.path.join(CLONE, ".git")):
        os.makedirs(os.path.dirname(CLONE), exist_ok=True)
        subprocess.check_call(["git", "clone", "-q", upstream["repository"], CLONE])
    git("fetch", "-q", "--tags", "origin", "+refs/heads/*:refs/remotes/origin/*")

    target = args.target
    if not target:
        target = git("tag", "--sort=-version:refname", "--list", "v[0-9]*").split()[0]
    ref = target if git("tag", "--list", target) else f"origin/{target}"
    base = upstream["commit"]
    head = git("rev-parse", ref)

    if args.diff:
        exclude = [f":(exclude){p}" for p in IGNORED]
        git(
            "diff", base, head, "--", *(args.paths or RELEVANT), *exclude, capture=False
        )
        return

    print(f"wgpudawn mirrors wgpu-py {upstream['version']} ({base[:10]})")
    print(f"target: {target} = {head[:10]}, wgpu-py {git('describe', '--tags', head)}")
    is_ancestor = ["merge-base", "--is-ancestor", head, base]
    if subprocess.call(["git", "-C", CLONE, *is_ancestor]) == 0:
        print("Up to date (the target is not newer than what wgpudawn mirrors).")
        return
    print("\n## Commits\n")
    print(git("log", "--oneline", "--reverse", f"{base}..{head}"))
    exclude = [f":(exclude){p}" for p in IGNORED + BACKEND]
    print("\n## Changes to port (same file in wgpudawn)\n")
    print(git("diff", "--stat", base, head, "--", *RELEVANT, *exclude) or "(none)")
    print("\n## Changes to the wgpu-native backend (port by hand to backends/dawn)\n")
    print(git("diff", "--stat", base, head, "--", *BACKEND) or "(none)")


if __name__ == "__main__":
    main()
