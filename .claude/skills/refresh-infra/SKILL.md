---
name: refresh-infra
description: Keep the build and test infrastructure of wgpudawn current - GitHub Actions versions, runner images, cibuildwheel and the manylinux image, the Python versions that are tested, npm packages, the pinned wheels of the website, and other pins that rot. Finds what is outdated or announced as deprecated, changes it safely (on a branch run first), and pushes. Use for "update the CI", "update the actions", "refresh the infrastructure", "a runner image is deprecated", "Node deprecation warning in CI", "add Python 3.x", "update cibuildwheel", "update dependencies", "what is outdated".
argument-hint: "[actions | runners | python | cibuildwheel | npm | pins | all] (default: all that is due)"
---

# Refresh the infrastructure

Nothing in this project changes when the world around it does: an action is
deprecated, a runner image is removed, a new Python comes out, a package that
is installed without a pin releases something incompatible. This skill is the
periodic pass that moves the infrastructure before it breaks, in small
commits that can be bisected. It does not change what wgpudawn is: not the
Dawn release (`update-dawn`), not the wgpu-py version (`sync-upstream`), not
pygfx or Pyodide on the website (`update-website`). Do not ask the user
anything that you can find out by reading or running code.

Arguments (optional): `$ARGUMENTS`: one of the groups below, or `all`.

## 1. What is due

```sh
python tools/maintenance_status.py --only ci,ci-warnings,actions,python,runners,pins,pyodide
(cd tests/pyodide && npm outdated); (cd website && npm outdated)       # exit code 1 only means "something is outdated"
```

`ci-warnings` are the notices that GitHub attaches to the jobs of the last
run (an action on a deprecated Node.js, an image label that will move, an
image that will be removed, with the date). Those have deadlines; do them
first. If `ci` is red, fix that first with the `ci-doctor` skill: an
infrastructure change on top of a red build cannot be verified.

## 2. How to change each thing

**Actions** (`uses:` in `.github/workflows/ci.yml`). For each one that is
behind, read what the new majors break before changing the number:
`gh release view <tag> -R <owner>/<action> --json body --jq .body` for each
major in between. What matters here:

* `actions/upload-artifact` and `actions/download-artifact` are moved
  together; the publish job relies on `pattern: dist-*` with
  `merge-multiple: true`, and the website job on downloading two artifacts
  into one directory.
* `actions/cache/restore` and `actions/cache/save` are the same action; a
  new major can mean a new cache format, i.e. one run that rebuilds Dawn on
  all platforms. Expected, not a failure.
* `actions/upload-pages-artifact` and `actions/deploy-pages` are moved
  together, and only run on pushes to `main`: a branch run does not test them.
* `pypa/gh-action-pypi-publish@release/v1` only runs on tags: it is tested by
  the next release, which is then a release candidate (the `release` skill
  decides that from the diff of `.github`).
* `ilammy/msvc-dev-cmd`, `pypa/cibuildwheel` and `pypa/gh-action-pypi-publish`
  are third-party code that runs in the jobs that make and publish the
  wheels. Look at what changed between the old and the new tag
  (`gh api repos/<owner>/<action>/compare/<old>...<new> --jq '.commits[].commit.message'`)
  instead of trusting the number.

**Runner images** (`os:` and `runs-on:`). The rule for which image does what:

* Wheels are built on the oldest image whose compiler can build Dawn
  (macOS: `macos-15`, because Xcode 15 on `macos-14` cannot; the deployment
  target stays `MACOSX_DEPLOYMENT_TARGET=11.0`, which is what the README
  promises). Tests run on the oldest and the newest image of each platform.
* When GitHub announces the removal of an image, move its matrix entries to
  the next one and keep the number of entries. When a new image appears, add
  it as the "newest" test entry and move the previous newest out if the
  matrix already has three for that platform.
* `ubuntu-latest` (lint, sdist, Pyodide, deploy, publish) moves by itself;
  when a notice says it will, run the branch test of step 3 against the new
  label explicitly (`ubuntu-26.04`) before the date.
* The platform tags of the wheels must not become more restrictive: after a
  change of image, compare the wheel file names with step 3 of the `release`
  skill.

**cibuildwheel and manylinux** (`pypa/cibuildwheel@...` in `ci.yml`,
`[tool.cibuildwheel]` in `pyproject.toml`, the image in
`tools/build_dawn_manylinux.sh`). Dawn is built in the manylinux image by our
script, and the wheel is built and repaired by cibuildwheel in its default
image: they must be the same manylinux (`manylinux_2_28` now; the README says
glibc >= 2.28). If a new cibuildwheel changes its default image, set the image
in `[tool.cibuildwheel]` rather than raising the glibc floor silently. A new
major also changes defaults of the repair step (4.0: `delvewheel` on Windows,
`abi3audit` on abi3 wheels): after the bump, list the contents of every wheel
(the loop in step 3 of the `release` skill) and compare with before; a new DLL
in a wheel, or a wheel that is no longer `cp311-abi3`, is a regression. (The
Windows wheels have `msvcp140*.dll` in `wgpudawn.libs/` since cibuildwheel 4:
intended, and listed in `LICENSES/README.md`.)

**Python versions.** The wheels are abi3 (`cp311-abi3`: `build = "cp311-*"`
in `pyproject.toml`, `py_limited_api` in `setup.py`), so a new Python needs
no new wheel, only a test: add it to the `test` matrix of `ci.yml` as soon as
`setup-python` has a stable build (the `python` line of the status tool), on
`linux-x86_64` and as the Python of the "newest image" entry of each other
platform. If a test dependency has no wheel for it yet, say so and try again
next time; do not add `allow-prereleases`. The floor (`requires-python`) is
that of wgpu-py, of which this is a drop-in replacement: it only changes in a
`sync-upstream`, and then all of `requires-python`, `build = "cpXY-*"`,
`py_limited_api`, the oldest entries of the matrix and the README change
together.

**npm** (`website/package.json`, `tests/pyodide/package.json`; the lock files
are not committed, so `^` ranges move by themselves). `puppeteer-core` drives
the Chrome that is installed (`/usr/bin/google-chrome`, also on the runners):
a new major is verified by running the checker. `webgpu` is Dawn for Node,
used by the Pyodide tests: any version that runs them is fine. `pyodide`
there is the Pyodide version: not here, see `update-website`, step 5. Verify
locally with the Pyodide wheel of the last green run:

```sh
run=$(gh run list --branch main --workflow CI --status success --limit 1 --json databaseId --jq '.[0].databaseId')
rm -rf ../pyodide-dist && gh run download $run -n dist-wheel-pyodide -D ../pyodide-dist
(cd tests/pyodide && npm install --no-audit --no-fund && node run_node.mjs $(ls $PWD/../../../pyodide-dist/*.whl | tr '\n' ',') compute_sync.py)
```

and, for `website/`, the checker as in `update-website`, step 2.

**Pins of the website** (`website/pyodide.json`: `imgui-bundle==...`;
`website/build_freetype.sh`: `FREETYPE_PY_VERSION`, `FREETYPE_VERSION`). A
pinned package with a compiled wheel must have one for the platform tag of
the pinned Pyodide (`PLATFORM_TAG` in `build_freetype.sh`):

```sh
curl -s https://pypi.org/pypi/imgui-bundle/<version>/json | python -c "
import json, sys; print([f['filename'] for f in json.load(sys.stdin)['urls'] if 'emscripten' in f['filename']])"
```

No such wheel for the newer version: keep the pin, it is not due. After a
change, the examples that use it must still work (`update-website`, step 2;
`--only bloom` runs two that use imgui).

**Other pins.** `rev:` in `.pre-commit-config.yaml` is the ruff that the
owner's commits are formatted with; CI installs the newest ruff. Keep the
`rev` at the current ruff, and when a new ruff reformats or flags existing
code, fix the code in the same commit. `PYODIDE_BUILD_VERSION` goes with
Pyodide (`update-website`). `node-version` of `setup-node` in `ci.yml`: an
active LTS or current release. The minimum versions in `[build-system]` and
`dependencies` of `pyproject.toml` only go up when something needs it.

## 3. Verify on a branch, then land

Changes to the workflow can only be tested by running it, and a push to
`main` cancels the run before it. So:

```sh
git switch -c ci/refresh && git commit ... && git push -u origin ci/refresh
gh workflow run CI --ref ci/refresh         # pushes to branches do not start CI; this does
sleep 10; run=$(gh run list --branch ci/refresh --workflow CI --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch $run --exit-status --interval 60
```

One commit per group (actions; images; cibuildwheel; Python; npm; pins), so
that a failure points at one of them. The branch run can read the Dawn cache
of `main`, and does not deploy the site or publish. When it is green, check
that the notices are gone
(`gh api repos/hmaarrfk/wgpudawn/check-runs/<job id>/annotations --jq '.[].message'`
for one job of each kind), then fast-forward `main`
(`git switch main && git merge --ff-only ci/refresh && git push`), delete the
branch (`git push origin --delete ci/refresh`), and watch the run on `main`
too: it is the one that deploys the website.

Something that is due and cannot be done yet (a dependency without a wheel
for the new Python, an action whose new major needs a runner that the images
do not have) is left as it is, and reported with the reason and the deadline.

## 4. Integrity of what is downloaded

While you are in these files, know which inputs are verified, because a
change here can silently remove a check:

* Checked: the Emdawnwebgpu package (`EMDAWN_ZIP_SHA256` in `build_cffi.py`,
  set by `tools/update_dawn.py` when the release is adopted). If a build ever
  fails with `Unexpected sha256 ... for https://github.com/google/dawn/releases/...`,
  an artifact changed after it was released: do not update the hash. Stop and
  tell the owner.
* Not checked, only named by a tag or a version: the Dawn source (a git tag
  cloned by `tools/build_dawn.py`) and what Dawn fetches for itself, FreeType
  and freetype-py in `website/build_freetype.sh`, the manylinux image, every
  action (tags, not commit hashes), everything that pip and npm install in
  CI, and what the pages load at run time (Pyodide from the CDN in
  `website/pyodide.json`, packages from PyPI).

Do not add downloads without a checksum to what goes into the wheels. Adding
checks to the list above is welcome, as its own commit.

## 5. Report

End with: what was outdated, what you changed (commits) and what each change
was verified with, what is still due and why, deadlines announced by GitHub,
and the branch and `main` runs.

Finally, add the entry for this session to `WORKLOG.md` (its header comes from
`python tools/session_stats.py --markdown`; see the instructions at the top of
that file), and commit it.
