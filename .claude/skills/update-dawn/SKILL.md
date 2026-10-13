---
name: update-dawn
description: Move wgpudawn to the latest (or a given) Dawn release, adapt the backend, verify on all platforms, push, and (with "release") tag the next X.Y.Z.N so that CI publishes to PyPI. Use for "update Dawn", "bump Dawn", "new Dawn release".
argument-hint: "[dawn tag, default: latest] [release]"
---

# Update Dawn

wgpudawn links one pinned release of Dawn into its wheels. Dawn releases
almost daily, and this project follows it aggressively: the default target is
always the latest release, and a Dawn update is released on its own, without
waiting for wgpu-py. Your job is to get from the pinned release to the target
and to leave the repository released or ready to release, without asking the
user anything that you can find out by reading or running code.

Arguments (optional): `$ARGUMENTS`

* a Dawn tag such as `v20261009.190412`. Default: the latest release.
* `release`: after CI is green on main, release the next version (step 6).

Whether this is due: `python tools/maintenance_status.py --only dawn` (it also
says how many releases behind the pin is).

Updating Dawn must not change the public API: that is defined by wgpu-py (see
`upstream.json` and the `sync-upstream` skill). If a Dawn change forces an API
change, stop at the last Dawn release that does not, and report it.

## 1. Regenerate the bindings

```sh
python tools/update_dawn.py [tag]
```

This downloads the headers of the release, regenerates
`wgpudawn/_lib/webgpu_cdef.h` and `webgpu_native_extra_cdef.h`, updates the
tag in `build_cffi.py`, `wgpudawn/_lib/__init__.py` and `upstream.json`, and
prints what changed in the cdef. Read that output:

* The Emdawnwebgpu header must stay a subset of the native one: nothing "only
  in A", nothing `INCOMPATIBLE`. If that fails, the one-cdef-for-both-targets
  design does not hold for this release; try the previous release, and report.
* Removed or renamed functions, struct fields and enum members are what the
  backend has to adapt to. Additions need nothing unless the API needs them.

If "Dawn: X -> X" (already at the target) and there is nothing else to do, say
so and stop.

The script has no dry run: it rewrites the files as soon as it has downloaded
the release (`git status` shows them; `git checkout -- .` on those files takes
it back). When the target is many releases ahead and the update fails in a way
that is not quickly understood, bisect over the releases in between
(`gh api "repos/google/dawn/releases?per_page=100" --jq '.[].tag_name'`), land
the newest one that works, and report the one that breaks and why.

## 2. Rebuild Dawn and the extension

```sh
python tools/build_dawn.py --prefix ../dawn-prefix      # ~5 min on a fast machine
DAWN_PREFIX=$PWD/../dawn-prefix pip install --no-build-isolation -e .
```

If Dawn fails to configure or build, look at what changed in its CMake options
(`CMakeLists.txt` at the root of Dawn, the `option(...)` lines) and adapt
`get_cmake_args()` in `tools/build_dawn.py`. Keep the set of backends (Vulkan,
Metal, D3D11/12; no OpenGL) and the SPIR-V reader. A compile error of the
extension means the cdef and Dawn disagree: `build_cffi.py` has the C++ helper
that uses `dawn/native/DawnNative.h`, which is not covered by the cdef.

## 3. Codegen and the backend

```sh
python codegen
grep -n "FIXME" wgpudawn/backends/dawn/_api.py
git diff wgpudawn/backends/dawn/_mappings.py wgpudawn/resources/codegen_report.md
```

Codegen marks every C call and struct in `_api.py` that no longer matches the
header with a `FIXME`. Resolve them all, and run it again until it is stable.
Then check `_mappings.py`: an enum member that disappeared and that `_api.py`
or `_helpers.py` uses by name (`grep -n "enum_str2int\|enum_int2str"`) is a bug
that codegen does not flag. `codegen_report.md` must not contain `ERROR`.

Things that have changed between Dawn releases before, to look at first:
callback signatures and `*CallbackInfo` structs, the `WGPUStringView`
conventions, feature names (`WGPUFeatureName_*`), limits (`WGPULimits`), and
the surface source structs for each window system.

## 4. Verify

```sh
pip install --no-deps ./tests/wgpu_shim
ruff format . && ruff check .
pytest tests codegen
(cd ../pygfx-src && pytest tests)        # pygfx's unit tests on wgpudawn
```

(See `sync-upstream`, step 5, for setting up `../pygfx-src` at the commit that
`upstream.json` pins, which is what CI tests. Do not move that pin here.)
Everything must pass. Tint follows the WGSL spec more strictly with each release: when a
shader is newly rejected, check the spec; if the shader is wrong, fix the
shader, and if it is a shader that pygfx generates, report it as something to
fix in pygfx rather than working around it here.

Also run `python tools/bench.py` before and after, and report regressions of
more than ~20% in the per-call numbers.

The license notices of what the wheels contain (`LICENSES/`) follow Dawn:

```sh
cmp ../dawn-prefix/LICENSE.dawn LICENSES/DAWN-LICENSE || cp ../dawn-prefix/LICENSE.dawn LICENSES/DAWN-LICENSE
diff <(curl -fsSL https://raw.githubusercontent.com/google/dawn/<old tag>/DEPS) \
     <(curl -fsSL https://raw.githubusercontent.com/google/dawn/<new tag>/DEPS) | grep -E "^[<>] +'third_party/"
```

A `third_party` dependency that was added or removed, and that is linked into
the library that `tools/build_dawn.py` builds (not a test, tool or GL/Android
dependency), goes into or out of the list in `LICENSES/README.md`, with its
license. Say so in the report: the owner reads license changes.

## 5. Commit, push, CI

Commit on `main` (follow the user's commit message conventions) and push.
Changing the tag invalidates the cached Dawn of CI, so the first run builds
Dawn on all six platforms (up to an hour on Windows). Watch the run:

```sh
run=$(gh run list --commit $(git rev-parse HEAD) --workflow CI --json databaseId --jq '.[0].databaseId')
gh run watch $run --exit-status --interval 60      # in the background: it takes 30 to 90 minutes
gh run view $run --json jobs --jq '.jobs[] | select(.conclusion != "success") | [.name, .status, .conclusion] | @tsv'
```

All jobs must pass, including the Pyodide job, which uses the Emdawnwebgpu
package of the same release, and the Website job, which runs every example of
pygfx on the new Pyodide wheel (a failure there: `update-website`, step 3).
Fix what fails and push again (the `ci-doctor` skill has the failure classes
that this project has seen). A push to `main` cancels the run of the previous
push, and with it an hour of Dawn builds: do not push anything else meanwhile.
Compilers on the CI runners are older than a local one: a Dawn that needs a
newer compiler means changing the runner image in `.github/workflows/wheels.yml`,
not dropping the platform.

## 6. Release

The version is the git tag (no `v`), with four numbers: `X.Y.Z.N`, where
`X.Y.Z` is the wgpu-py version that wgpudawn mirrors (`upstream.json`), and
`N` counts the wgpudawn releases for that version, starting at 0. A Dawn update
is the next `N`:

```sh
git tag --list "$(python -c "import json; print(json.load(open('upstream.json'))['wgpu-py']['version'])").*" --sort=-version:refname | head -1
```

(Nothing printed: no release of that wgpu-py version yet, so `N` is 0.)

With the `release` argument, once CI is green for the commit, read
`.claude/skills/release/SKILL.md` and follow it (it picks the version, tags,
watches the publish job, and verifies what PyPI has). The tag build publishes
to PyPI, which cannot be undone. Without `release`, do not tag: print
`claude "/release"` as the step that is left for the user.

## 7. Report

End with: the Dawn range (old tag -> new tag), what changed in the header that
mattered, what was adapted in the backend and in the build, tests that were
adapted and why, benchmark changes, the CI run, and the tag (pushed or to
push). If you stopped at an older release than the target, say which and why.


Finally, add the entry for this session to `WORKLOG.md` (its header comes from
`python tools/session_stats.py --markdown`; see the instructions at the top of
that file), and commit it.
