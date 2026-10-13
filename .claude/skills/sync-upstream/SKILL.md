---
name: sync-upstream
description: Bring wgpudawn up to date with a new wgpu-py release (or wgpu-py main) and optionally a new Dawn release, verify it, push it, and (with "release") tag it so that CI publishes to PyPI. Use for "sync with upstream", "update to wgpu-py X", "bump Dawn", "make a release".
argument-hint: "[wgpu-py tag or 'main'] [dawn=latest] [release]"
---

# Sync wgpudawn with wgpu-py (and Dawn)

wgpudawn is wgpu-py with the wgpu-native backend replaced by a Dawn backend.
Its goal is to be a drop-in replacement: for every wgpu-py release X.Y.Z there
is a wgpudawn X.Y.Z with the same API. `upstream.json` records what the code
currently corresponds to. Your job is to move it forward and to leave the
repository released or ready to release, with as little input from the user as
possible. Do not ask questions that you can answer by reading or running code.

Arguments (all optional): `$ARGUMENTS`

* a wgpu-py tag (`v0.33.0`) or `main`: the target. Default: the latest wgpu-py
  release tag.
* `dawn=latest`: also update Dawn, with the `update-dawn` skill. Default: keep
  Dawn, unless the port needs a newer one (say so in the report).
* `release`: after CI is green on main, push the version tag. Without it, stop
  before tagging and print the command.

## 1. Find out what changed

```sh
python tools/upstream_diff.py [target]          # commits + files, grouped
python tools/upstream_diff.py [target] --diff [paths]
```

If it says "Up to date" and there is no Dawn bump, check whether the latest tag
of this repository is the mirrored version; if it is, report that there is
nothing to do and stop.

Read the wgpu-py CHANGELOG section for the target too: it says what is
user-visible.

## 2. Port

The source of each file, and how to carry a change over:

| wgpu-py | wgpudawn | how |
|---|---|---|
| `wgpu/*.py`, `wgpu/utils/`, `wgpu/__pyinstaller/` | `wgpudawn/` (same name) | apply the diff; module references `wgpu.` -> `wgpudawn.`; the logger is `"wgpudawn"` |
| `wgpu/resources/webgpu.idl` | `wgpudawn/resources/webgpu.idl` | copy, then run codegen (step 3) |
| `wgpu/enums.py`, `flags.py`, `structs.py`, `resources/codegen_report.md` | same | never edit: codegen writes them |
| `wgpu/backends/wgpu_native/_api.py`, `_helpers.py` | `wgpudawn/backends/dawn/_api.py`, `_helpers.py` | by hand: understand the change and make the equivalent one. The Dawn backend started as a copy, so most methods have the same structure, but it calls Dawn's `webgpu.h`, raises errors via `SafeLibCalls`, and has no `extras` |
| `wgpu/backends/wgpu_native/extras.py`, `_poller.py`, `wgpu/resources/*.h`, `js_webgpu`, `tools/`, `docs/`, `tests_mem/` | - | not ported |
| `codegen/` | `codegen/` | apply the diff. Here `wgpu_native_patcher.py` is `backend_patcher.py` (without `write_mappings`), `hparser.get_h_parser()` parses `wgpudawn/_lib/webgpu_cdef.h`, and only `backends/dawn` is patched |
| `tests/*.py` | `tests/*.py` | apply the diff; `import wgpu` -> `import wgpudawn as wgpu`, `from wgpu` -> `from wgpudawn`. `test_wgpu_native_X.py` is `test_wgpu_X.py` here. Tests of wgpu-native specifics (extras, poller, naga error messages) are not ported |
| `examples/` | `examples/` | same rules as the tests; skip examples that need wgpu-native extras |
| `pyproject.toml` | `pyproject.toml` | only dependency / python-version changes |

Rules:

* Keep the diff with wgpu-py small: do not reformat, rename or "improve"
  ported code. That is what keeps the next sync cheap.
* When Dawn behaves differently and both behaviors are valid WebGPU, keep
  Dawn's behavior and adapt the test, with a comment that says why. When the
  difference would break a user of wgpu-py (missing method, different return
  type, different exception type), fix the backend instead.
* A new API method that the Dawn backend cannot implement yet must raise
  `NotImplementedError` with a clear message, and be listed in the report.
* When a test shader is rejected by Tint, check the WGSL spec. If the shader is
  wrong, fix the shader (and consider sending the fix to wgpu-py).

## 3. Codegen

```sh
python codegen            # rewrites enums/flags/structs/_mappings, annotates _api.py
grep -n "FIXME" wgpudawn/backends/dawn/_api.py wgpudawn/_classes.py
```

Resolve every `FIXME` that codegen adds (unknown C function or struct field,
new or changed IDL method), then run it again until it is stable.
`wgpudawn/resources/codegen_report.md` must not contain `ERROR`.

## 4. Dawn

Dawn is updated on its own, by the `update-dawn` skill. Do that first (or
after), as a separate commit, when `dawn=` is given or when the port needs
API that the pinned Dawn release does not have.

## 5. Build and verify

```sh
python tools/build_dawn.py --prefix ../dawn-prefix        # no-op when up to date
DAWN_PREFIX=$PWD/../dawn-prefix pip install --no-build-isolation -e .
pip install --no-deps ./tests/wgpu_shim                   # test-only `wgpu` -> wgpudawn
ruff format . && ruff check .
pytest tests codegen
```

Then the test suite of pygfx on top of wgpudawn (CI does the same):

```sh
git clone --depth 1 https://github.com/pygfx/pygfx ../pygfx-src   # or git pull
pip install -e "../pygfx-src[tests]" && pip install --no-deps ./tests/wgpu_shim
(cd ../pygfx-src && pytest tests)
```

`pip list` must show `wgpu` at the mirrored version with no wgpu-native
library in it (that would be the real wgpu-py; reinstall the shim).
Everything must pass. A failure in pygfx's tests is a bug in wgpudawn until
shown otherwise; do not skip tests to get to green.

## 6. Record

* `upstream.json`: `wgpu-py.version` and `wgpu-py.commit` (the full sha of the
  target; for `main`, the version stays that of the last release).
* `wgpudawn/__init__.py`: `wgpu_py_version`.
* `tests/wgpu_shim/pyproject.toml`: `version`.
* `README.md`: the "Differences with wgpu-py" list, if it changed.

`tests/test_meta.py` checks that these agree.

## 7. Commit, push, release

Commit on `main` (follow the user's commit message conventions) and push. Then
watch CI (`gh run watch`, or `gh run list --branch main`): all jobs of the `CI`
workflow must pass, on all six platforms. Fix what fails and push again; a
platform-specific failure is not a reason to drop the platform.

The version is the git tag (no `v`); there is no version number in the source.
It has four numbers, `X.Y.Z.N`: `X.Y.Z` is the wgpu-py version that wgpudawn
mirrors, and `N` counts the wgpudawn releases for it (Dawn updates, fixes),
starting at 0.

* Synced to a wgpu-py release `vX.Y.Z` -> tag `X.Y.Z.0`.
* A wgpudawn-only fix or a Dawn update on top of that -> the next `N`
  (`git tag --list "X.Y.Z.*"` shows the last one).
* Synced to wgpu-py `main` between releases -> also the next `N` of the last
  wgpu-py release, when it is worth releasing; otherwise no tag.

With the `release` argument, once CI is green for the commit:
`git tag X.Y.Z.N && git push origin X.Y.Z.N`. The tag build publishes to PyPI,
which cannot be undone, so only tag a commit whose CI run you saw pass, and
check afterwards that the publish job succeeded and that
`pip index versions wgpudawn` shows the version. Without `release`, print those
two commands instead.

## 8. Report

End with: the wgpu-py range that was ported, the Dawn release, what was ported
by hand in the backend, tests that were adapted or not ported and why, API that
is not implemented, the CI run, and the tag (pushed or to push).
