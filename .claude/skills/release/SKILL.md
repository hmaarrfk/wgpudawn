---
name: release
description: Release wgpudawn to PyPI. Picks the next version (X.Y.Z.N, or a release candidate), checks the preconditions, pushes the tag, watches the publish job, verifies what PyPI has (files, hashes, a clean install), and writes the GitHub release notes. Use for "make a release", "release wgpudawn", "tag a release", "publish to PyPI", "cut an rc", "is it ready to release", "yank a release".
argument-hint: "[X.Y.Z.N | rc | check] (default: the next X.Y.Z.N; 'check' never tags)"
---

# Release

The version of wgpudawn is the git tag: there is no version number in the
source (miniver, `wgpudawn/_version.py`). Pushing a tag that starts with a
digit runs the `CI` workflow on it, and its last job, `Publish to PyPI`
(`.github/workflows/wheels.yml`, environment `pypi`, trusted publishing: no token),
uploads the sdist and the seven wheels. That upload cannot be undone and a
version can never be uploaded twice. Everything before the tag is cheap to
redo; the tag is not. Your job is to make sure that the tag is pushed only on
a commit that deserves it, and that what ends up on PyPI is what was tested.

Arguments (optional): `$ARGUMENTS`

* a version: release exactly that.
* `rc`: release a candidate of the next version (`X.Y.Z.NrcM`).
* `check`: do steps 1 to 3, print the version and the command, tag nothing.

**Who may tag.** Only tag when the user asked for a release in this session:
they invoked this skill themselves, or they passed `release` to the skill
that sent you here (`maintain`, `update-dawn`, `sync-upstream`). An agent
that decided on its own that a release is due runs this as `check` and
reports. When in doubt, it is `check`.

## 1. The version

`X.Y.Z.N`: `X.Y.Z` is the wgpu-py version that the code mirrors, `N` counts the
releases of wgpudawn for it, from 0. Tags have no `v`.

```sh
git fetch -q --tags origin
mirrored=$(python -c "import json; print(json.load(open('upstream.json'))['wgpu-py']['version'])")
git tag --list "$mirrored.*" --sort=-version:refname | head -5      # the releases of this wgpu-py version
git tag --list --sort=-creatordate | head -5                        # the last releases of any kind
python tools/maintenance_status.py --only release
```

* No tag `X.Y.Z.*` yet: the next version is `X.Y.Z.0`.
* Otherwise the next `N` after the highest final (not `rc`) one.
* Tags `0.0.x` are the first releases, from before this scheme. They are not
  part of the counting; do not make new ones unless the user gives that
  version.
* A release candidate is `X.Y.Z.NrcM` (`0.32.0.1rc1`), in exactly this spelling:
  the publish job compares file names with the tag, and `-rc1` or `.rc1` are
  normalized to something else. `pip install wgpudawn` does not pick
  candidates, so they are safe to publish.

Make it a candidate first, without being asked, when a mistake would be in
the packaging rather than in the code: there is no release on PyPI yet, or
since the last release something changed in how the files are made:

```sh
git diff --stat <last tag>..HEAD -- .github pyproject.toml setup.py MANIFEST.in build_cffi.py \
  tools/build_dawn.py tools/build_dawn_manylinux.sh wgpudawn/_version.py LICENSES
```

A Dawn update or a backend fix with none of those changed is released
directly. After a candidate was verified (step 5), the final version is
tagged on the same commit.

If nothing that is shipped changed since the last tag
(`git log --oneline <last tag>..HEAD -- wgpudawn build_cffi.py pyproject.toml setup.py upstream.json`
is empty), there is nothing to release: say so and stop.

## 2. Preconditions

All of these, or stop and report which one failed:

```sh
git status --short                                   # empty
git fetch -q origin && git rev-parse HEAD origin/main   # the same commit
run=$(gh run list --commit $(git rev-parse HEAD) --workflow CI --event push --json databaseId,conclusion --jq '.[0] | [.databaseId, .conclusion] | @tsv')
echo "$run"                                          # <id> success
git ls-remote --tags origin "refs/tags/<version>"    # empty: the tag does not exist
curl -s -o /dev/null -w "%{http_code}\n" https://pypi.org/pypi/wgpudawn/<version>/json   # 404: PyPI does not have it
```

* The run of exactly this commit is `success`: every job, including `Website`.
  Not "the last run was green", not "it was green before the last small
  commit". If it is red: the `ci-doctor` skill, then come back.
* The tests really ran. Every test job ends with about 209 passed and 3
  skipped; a job that is green with dozens of skips had no GPU adapter and
  tested nothing:
  `gh run view <run id> --log | grep -E "=+ [0-9]+ passed" | cut -f1,3 | cut -c1-120`
  (one line per job that runs pytest: the 12 `Test ...` jobs with about 209,
  and lint, Pyodide and pygfx with their own counts).
* `pytest tests/test_meta.py` passes locally: `upstream.json`,
  `wgpudawn.wgpu_py_version`, the Dawn tag in `build_cffi.py` and the shim
  version agree.
* The "Differences with wgpu-py" list and the Platforms section of `README.md`
  are true for this commit (the README is the page on PyPI, and it is frozen
  into the release).

## 3. Look at what would be uploaded

The tag run builds everything again from the same commit, but the artifacts
of the green run show what it will make:

```sh
rm -rf ../release-check && gh run download <run id> -p "dist-*" -D ../release-check
ls -l ../release-check/*
for w in ../release-check/*/*.whl; do python -m zipfile -l $w | awk 'NR>1 {print $1}' | cut -d/ -f1 | sort -u | tr '\n' ' '; echo "<- $(basename $w)"; done
```

* Eight files: the sdist, and one wheel each for
  `manylinux_2_27_x86_64.manylinux_2_28_x86_64`, `manylinux_2_27_aarch64.manylinux_2_28_aarch64`,
  `macosx_11_0_arm64`, `macosx_11_0_x86_64`, `win_amd64`, `win_arm64` (all
  `cp311-abi3`) and `pyemscripten_2026_0_wasm32` (`cp314`). A missing platform,
  or a platform tag that became more restrictive (a newer macOS or glibc), is
  a regression of the README's promise: stop.
* Every wheel contains only `wgpudawn` and `wgpudawn-<version>.dist-info`. A
  top-level `wgpu` must never be there (that would shadow wgpu-py for every
  user), and neither may `tests` or `tools`.
* The license files are in `dist-info/licenses/` (`LICENSE`, `LICENSES/...`).
* Sizes are of the order of the previous release (native wheels 3 to 6 MB,
  Pyodide 0.2 MB). A wheel that doubled linked something new: find out what
  before releasing, and whether `LICENSES/README.md` still covers it.

With `check`, stop here: print the version, what would be released
(`git log --oneline <last tag>..HEAD`), and `claude "/release <version>"`.

## 4. Tag, and watch

```sh
git tag <version> && git push origin <version>
sleep 20; run=$(gh run list --branch <version> --workflow CI --limit 1 --json databaseId --jq '.[0].databaseId')
gh run watch $run --exit-status --interval 60        # in the background; tag runs are never cancelled
gh run view $run --json jobs --jq '.jobs[] | select(.name == "Publish to PyPI") | [.status, .conclusion] | @tsv'
```

* The publish job `waiting`: the `pypi` environment has a required reviewer.
  That is the owner's click; tell them, and wait.
* The tag run fails **before** the publish job (which needs all the others):
  nothing was uploaded. If it is infrastructure, `gh run rerun $run --failed`.
  If the commit has to change: fix it on `main`, get that green, then move the
  tag (`git tag -d <version> && git push origin :refs/tags/<version>`, and
  tag the new commit). Moving a tag is only allowed in this case, where PyPI
  never saw the version; check with the `curl` of step 2.
* The publish job itself fails. `invalid-publisher` or a 403: PyPI does not
  trust this workflow (the trusted publisher of the project `wgpudawn` must be
  owner `hmaarrfk`, repository `wgpudawn`, workflow `wheels.yml`, environment
  `pypi`); only the owner can set that on pypi.org; nothing was uploaded, and
  the job can be re-run afterwards. `<file> is not version <tag>`: the tag
  spelling, see step 1; delete the tag and use the right one. `File already
  exists`: part of the upload happened; that version is used up: never try
  to replace files, release the next `N`.

## 5. Verify what PyPI has

The CDN of PyPI can lag a few minutes; retry before concluding anything.

```sh
curl -s https://pypi.org/pypi/wgpudawn/<version>/json | python -c "
import json, sys
for f in json.load(sys.stdin)['urls']: print(f['digests']['sha256'], f['filename'])" | sort > ../release-pypi.txt
rm -rf ../release-dist && gh run download $run -p "dist-*" -D ../release-dist
(cd ../release-dist && sha256sum */* | sed 's# .*/#  #' | sed 's/  */ /' | sort) > ../release-ci.txt
diff ../release-pypi.txt ../release-ci.txt && wc -l < ../release-pypi.txt      # no difference, 8 files
```

Then install it the way a user does, in a new environment, not from the
repository (run this outside the checkout, so that the source tree cannot be
imported by accident):

```sh
cd "$(mktemp -d)" && python -m venv venv && venv/bin/pip install --no-cache-dir "wgpudawn==<version>"
venv/bin/python -c "
import wgpudawn
assert wgpudawn.__version__ == '<version>', wgpudawn.__version__
import wgpudawn.backends.dawn as dawn
print('wgpu-py', wgpudawn.wgpu_py_version, 'Dawn', dawn.__version__)
adapters = wgpudawn.gpu.enumerate_adapters_sync(); assert adapters
[print(a.summary) for a in adapters]
device = wgpudawn.gpu.request_adapter_sync().request_device_sync(); print(device)"
```

(With `uv`, when it is installed: `uv run --no-project --with "wgpudawn==<version>" python -c "import wgpudawn; print(wgpudawn.__version__)"`.)

And that pip resolves a wheel, not the sdist, for each platform (this machine
can only run one of them; the wheels themselves were tested by the tag run):

```sh
for p in manylinux_2_28_x86_64 manylinux_2_28_aarch64 macosx_11_0_arm64 macosx_11_0_x86_64 win_amd64 win_arm64; do
  venv/bin/pip download -q "wgpudawn==<version>" --no-deps --only-binary=:all: --platform $p --python-version 3.13 -d dl || echo "NO WHEEL for $p"
done; ls dl
```

For a final release also: `pip index versions wgpudawn` shows it as the latest,
and https://pypi.org/project/wgpudawn/ renders the README.

If any of this fails, the release is bad. Do not delete anything. Report it
at the top of your answer, with the evidence, and prepare the fix as the next
`N`. Yanking the bad version is the owner's decision and is done by them on
pypi.org (Manage project, Releases, Options, Yank); give them the sentence to
put as the reason. A yanked version stays installable by exact pin, which is
what one wants: nobody's lock file breaks.

## 6. Release notes

The publish job of the workflow creates the release on GitHub after the
upload (a tag alone does not show under "Releases"), with generated notes, as
a prerelease for a candidate. For a final release, replace those notes (for a
candidate, one line is enough):

```sh
git log --format="* %s (%h)" <previous final tag>..<version> > ../release-notes.md    # raw material: rewrite it
gh release edit <version> --notes-file ../release-notes.md
```

(If the release is not there, the job failed after the upload: `gh release
create <version> --verify-tag --title "<version>" --notes-file ...`.)

Write the notes for a user of wgpu-py, short: the wgpu-py version that it
mirrors and the Dawn release that it contains (old -> new when it changed, with
the link `https://github.com/google/dawn/releases/tag/<tag>`), what changed
in behavior, what was fixed, anything that is not implemented, and
`pip install wgpudawn==<version>`. No commit list, nothing about CI.

## 7. Report

End with: the version and the commit, the tag run, the eight files and that
their hashes match, the output of the clean install (adapter line), the URL
of the GitHub release, and anything that was noticed and not fixed.

Finally, add the entry for this session to `WORKLOG.md` (its header comes from
`python tools/session_stats.py --markdown`; see the instructions at the top of
that file), and commit and push it (a commit after the tag: it does not belong
to the release, and that is fine).
