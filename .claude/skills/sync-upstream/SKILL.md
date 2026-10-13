---
name: sync-upstream
description: Port a new wgpu-py release (or wgpu-py main) to wgpudawn, verify it, push it, and (with "release") release it as X.Y.Z.0 with the release skill. Use for "sync with upstream", "sync with wgpu-py", "update to wgpu-py X", "port the new wgpu-py release", "there is a new wgpu-py".
argument-hint: "[wgpu-py tag or 'main'] [dawn=latest] [release]"
---

# Sync wgpudawn with wgpu-py (and Dawn)

wgpudawn is wgpu-py with the wgpu-native backend replaced by a Dawn backend.
Its goal is to be a drop-in replacement: for every wgpu-py release X.Y.Z there
is a wgpudawn X.Y.Z.0 with the same API. `upstream.json` records what the code
currently corresponds to. Your job is to move it forward and to leave the
repository released or ready to release, with as little input from the user as
possible. Do not ask questions that you can answer by reading or running code.

Arguments (all optional): `$ARGUMENTS`

* a wgpu-py tag (`v0.33.0`) or `main`: the target. Default: the latest wgpu-py
  release tag.
* `dawn=latest`: also update Dawn, with the `update-dawn` skill. Default: keep
  Dawn, unless the port needs a newer one (say so in the report).
* `release`: after CI is green on main, release (step 7). Without it, stop
  before tagging and print the command.

Whether this is due: `python tools/maintenance_status.py --only wgpu-py`.

## 1. Find out what changed

```sh
python tools/upstream_diff.py [target]          # commits + files, grouped
python tools/upstream_diff.py [target] --diff [paths]
```

If it says "Up to date" and there is no Dawn bump, check whether the mirrored
version has been released (`git tag --list "X.Y.Z.*"`, with `X.Y.Z` from
`upstream.json`); if it has, or if `release` was not given, report that there
is nothing to do and stop.

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
| `codegen/` | `codegen/` | apply the diff. Here `wgpu_native_patcher.py` is `codegen/backend_patcher.py` (the validation and annotation of `_api.py`) plus `codegen/dawn_patcher.py` (which writes `_mappings.py`), `hparser.get_h_parser()` parses `wgpudawn/_lib/webgpu_cdef.h`, and only `backends/dawn` is patched |
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

Then the test suite of pygfx on top of wgpudawn. CI does the same, with the
commit of pygfx that `upstream.json` pins, so test that one (moving the pin is
the job of the `update-website` skill):

```sh
pin=$(python -c "import json; print(json.load(open('upstream.json'))['pygfx']['commit'])")
[ -d ../pygfx-src ] || git clone https://github.com/pygfx/pygfx ../pygfx-src
git -C ../pygfx-src fetch -q origin $pin && git -C ../pygfx-src checkout -q $pin
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
watch CI: all jobs of the `CI` workflow must pass, on all six platforms.

```sh
run=$(gh run list --commit $(git rev-parse HEAD) --workflow CI --json databaseId --jq '.[0].databaseId')
gh run watch $run --exit-status --interval 60      # in the background: it takes 30 to 90 minutes
gh run view $run --json jobs --jq '.jobs[] | select(.conclusion != "success") | [.name, .status, .conclusion] | @tsv'
```

Fix what fails and push again (the `ci-doctor` skill has the failure classes
that this project has seen); a platform-specific failure is not a reason to
drop the platform. A push to `main` cancels the run of the previous push, so
do not push something unrelated while a run that you need is going.

The version is the git tag (no `v`); there is no version number in the source.
It has four numbers, `X.Y.Z.N`: `X.Y.Z` is the wgpu-py version that wgpudawn
mirrors, and `N` counts the wgpudawn releases for it (Dawn updates, fixes),
starting at 0.

* Synced to a wgpu-py release `vX.Y.Z` -> tag `X.Y.Z.0`.
* A wgpudawn-only fix or a Dawn update on top of that -> the next `N`
  (`git tag --list "X.Y.Z.*"` shows the last one).
* Synced to wgpu-py `main` between releases -> also the next `N` of the last
  wgpu-py release, when it is worth releasing; otherwise no tag.

With the `release` argument, once CI is green for the commit, read
`.claude/skills/release/SKILL.md` and follow it with that version (it tags,
watches the publish job, and verifies what PyPI has). The tag build publishes
to PyPI, which cannot be undone. Without `release`, do not tag: print
`claude "/release X.Y.Z.N"` as the step that is left for the user.

## 8. Report

End with: the wgpu-py range that was ported, the Dawn release, what was ported
by hand in the backend, tests that were adapted or not ported and why, API that
is not implemented, the CI run, and the tag (pushed or to push).


Finally, add the entry for this session to `WORKLOG.md` (its header comes from
`python tools/session_stats.py --markdown`; see the instructions at the top of
that file), and commit it.
