---
name: ci-doctor
description: Find out why CI of wgpudawn failed (on main, on a tag, or a given run), classify it (runner or network trouble, a changed dependency, a real regression, which platform), and fix it or re-run it until main is green. Use for "CI is red", "main is red", "why did CI fail", "fix CI", "the build is broken", "the website job failed", "the publish job failed", or a link to a GitHub Actions run.
argument-hint: "[run id or URL, default: the last run on main] [diagnose]"
---

# CI doctor

Everything this project claims is checked by one workflow, `CI`
(`.github/workflows/wheels.yml`): lint and codegen, the sdist, six wheels with Dawn
linked in, the tests of each wheel, the test suite of pygfx on wgpudawn, the
Pyodide wheel, the website (every pygfx example in headless Chrome), the
deployment of the website (pushes to `main`) and the publication to PyPI
(tags). A red `main` blocks every other maintenance task and every release,
so it is fixed first. Your job is to get from "a run failed" to a green run of
the same or a fixed commit, and to say what it was. Do not ask the user
anything that the logs can tell you.

Arguments (optional): `$ARGUMENTS`

* a run id or URL. Default: the newest run on `main` that is not cancelled.
* `diagnose`: stop after step 3 (report the cause and the proposed fix; change
  and re-run nothing).

## 1. Find the run and what failed

```sh
python tools/maintenance_status.py --only ci
gh run list --branch main --workflow CI --limit 8 --json databaseId,headSha,status,conclusion,createdAt \
  --jq '.[] | [.databaseId, .headSha[0:7], .status, .conclusion, .createdAt] | @tsv'
gh run view <run> --json jobs --jq '.jobs[] | select(.conclusion != "success") | [.databaseId, .name, .status, .conclusion] | @tsv'
```

* `cancelled` is not a failure: a push to `main` cancels the run of the
  previous push (the `concurrency` group). Look at the run that replaced it.
* A run that is `in_progress`: wait for it, do not push (that would cancel it).
  `gh run watch <run> --exit-status --interval 60` in the background.
* `skipped` jobs are the ones that `needs:` a failed job, plus `Publish to PyPI`
  on anything that is not a tag. Look at the first failure, not at those.

## 2. Read the logs

```sh
gh run view --job <job id> --log-failed | cut -f3- | cut -c30- \
  | grep -E "FAILED|ERROR|^E  |Error|error:|##\[error\]|Traceback" | head -60
gh run view --job <job id> --log-failed | cut -f3- | cut -c30- | grep -E "^E  " | sort | uniq -c | sort -rn | head
```

The second form matters when one cause fails eighty tests: the most frequent
`E` line is the cause. Read around it in the full log (`--log` instead of
`--log-failed`) before deciding anything. The annotations of a job
(`gh api repos/hmaarrfk/wgpudawn/check-runs/<job id>/annotations --jq '.[].message'`)
have the deprecation notices of GitHub; those are for the `refresh-infra`
skill, not failures.

For the website job, the result of every example is in the artifact, also
when the job failed:
`gh run download <run> -n website -D <dir>` and read `<dir>/results.json`.

## 3. Classify

Ask first: **did the code change, or did the world?** `git log -3 --stat` for
what the failing commit touched, and
`gh run list --branch main --workflow CI --status success --limit 1` for the
last green commit. The versions of what a job installed are in its log
("Successfully installed ..." of pip, `pip list` in the pygfx job, the
`Show adapters` step for the GPU and driver); compare them between the green
run and the red one. Many inputs are not pinned (ruff, pytest, numpy,
rendercanvas, the runner images, the manylinux image, the packages that the
website installs from PyPI at run time), so "nothing changed here and it
broke" usually means one of those moved.

| Class | How it looks | What to do |
|---|---|---|
| Infrastructure | a download or `apt-get` that fails, HTTP 5xx, "The runner has received a shutdown signal", "lost communication", a timeout in a step that normally takes seconds, a failure while Dawn fetches its dependencies | `gh run rerun <run> --failed`, once. If the same step fails again it is not infrastructure. |
| A tool moved | the lint job fails on code that did not change (a new ruff), a pytest or numpy deprecation that became an error, pip refusing something | fix the code for the new version (`pip install -U ruff && ruff format . && ruff check .`); pin only when the new version is itself broken, with a comment that says until when |
| A dependency moved | the tests of a wheel or of pygfx fail in rendercanvas, numpy, pylinalg, ...; a website example fails in a package that it loads from PyPI | adapt if the new behavior is intended upstream; if it is a bug there, pin the previous version where it is installed, with a comment, and put it in the report as something to tell upstream |
| The runner image moved | a compiler error in Dawn on one platform, a missing SDK, a Python that `setup-python` no longer has, the GPU or driver in `Show adapters` changed | the `refresh-infra` skill; change the image for the job, do not drop the platform |
| A platform difference | passes on Linux (and locally), fails on macOS or Windows, or only on one architecture | a real bug or a real difference: see "What this project has seen" below, then fix the backend or make the test honest about what the adapter supports |
| A regression | a test of something that the failing commit changed | fix it, add a test when the existing ones missed it locally |
| The checker | an example that "fails" by timeout on SwiftShader but works on a GPU; a test that is skipped everywhere | fix the check (`--timeout`, a lighter example setup), never the baseline |

A test failure is re-run at most once, and only to learn whether it is
deterministic. One that passes the second time is flaky: write the test name
and the error in the `WORKLOG.md` entry, and when the work log already has the
same one, find the cause instead of re-running again.

What this project has seen (`git log` and `WORKLOG.md` have the details):

* Windows, every test that creates a device fails with
  `DynamicLib.Open: d3dcompiler_47.dll Windows Error: 87`: Dawn looked for its
  DLLs next to the executable. Fixed with `-DDAWN_FORCE_SYSTEM_COMPONENT_LOAD=ON`
  in `tools/build_dawn.py`. A Dawn update that renames this option brings it
  back.
* macOS runners are virtual machines without some GPU features:
  `Requested feature FeatureName::TimestampQuery is not supported`. A test that
  needs an optional feature must skip when the adapter lacks it, with the
  adapter in the reason; it must not be skipped by platform.
* `macos-14` (Xcode 15) cannot compile Dawn ("CTAD for aggregates"); the macOS
  wheels are built on `macos-15` with `MACOSX_DEPLOYMENT_TARGET=11.0`, and
  `macos-14` only tests.
* The pygfx job: `ValueError: option names {'--regenerate-screenshots'} already
  added`: pytest loaded our `conftest.py` and the one of pygfx (its checkout is
  inside ours). That is what `--confcutdir=$PWD` is for.
* A change to the CMake arguments of one platform rebuilds Dawn for that
  platform only (the cache key has a hash of `tools/build_dawn.py --print-config`);
  a new Dawn tag rebuilds all six, up to an hour on Windows.
* The publish job, `<file> is not version <tag>`: the tag is not a version that
  the wheels can have (a `v` prefix, or a spelling that packaging normalizes,
  such as `-rc1` instead of `rc1`). See the `release` skill.

Two things that make a green run mean less than it says; check them when a
failure does not add up, and before a release:

* The tests need a GPU adapter (`can_use_wgpu_lib` in `tests/testutils.py`);
  without one most of them are skipped and the job is green. A healthy test
  job ends with about 209 passed and 3 skipped
  (`gh run view --job <job id> --log | grep -E "passed|skipped" | tail -3`).
  If a job passes with dozens of skips, the adapter is gone (lavapipe not
  installed, a runner image change): that is a failure.
* The website job only fails for examples in `website/expected.json`.

## 4. Fix

Reproduce locally when the failure is not specific to a platform that you do
not have (the dev loop is in `CLAUDE.md`): `pytest tests codegen`, the pygfx
tests as in step 5 of `sync-upstream`, the website as in `update-website`.
The Linux wheel build itself: `tools/build_dawn_manylinux.sh <prefix>` (needs
docker).

For macOS, Windows and arm64 there is no local machine. Iterate on a branch,
so that `main` is not used as the scratchpad and its runs are not cancelled:

```sh
git switch -c ci/<what> && git push -u origin ci/<what>
gh workflow run CI --ref ci/<what>          # pushes to branches do not start CI; this does
gh run list --branch ci/<what> --workflow CI --limit 1
```

Such a run can read the Dawn cache of `main`, and does not deploy or publish.
Make the change that tells you the most per run (print the adapter, the
versions, the failing value), not one guess per run: a run costs 30 to 90
minutes. When it is green, put the fix on `main` as one commit and delete the
branch (`git push origin --delete ci/<what>`).

Rules:

* Never get to green by skipping a test, removing a platform, removing an
  entry of `website/expected.json`, or adding `continue-on-error`. If a check
  is wrong, fix the check and say why in the commit.
* A fix in `.github/workflows/wheels.yml` is still a fix of the cause: do not
  restructure the workflow while you are there.
* The same wheel is tested on several Pythons and images; a failure on one
  entry of the matrix only is information about that image, not noise.

## 5. Confirm

Commit on `main` (follow the user's commit message conventions), push, and
watch the run of that commit to the end:

```sh
run=$(gh run list --commit $(git rev-parse HEAD) --workflow CI --json databaseId --jq '.[0].databaseId')
gh run watch $run --exit-status --interval 60
```

Done is: the run of the head of `main` is green in all jobs, including
`Website` and `Deploy the website`. If you were asked about a tag run, see
the `release` skill for what can be done after a failed publication.

Stop and report, instead of continuing, when: the fix needs something only
the owner can do (a setting of the repository, of PyPI or of GitHub Pages; a
secret; a paid runner), or three attempts on the same failure have not
changed the error.

## 6. Report

End with: the run, the jobs that failed, the class and the cause in one
sentence each, what you changed (commits) or re-ran, the green run, and what
is left (a flaky test that was seen, something to tell an upstream project,
something for the owner).

Finally, if the session changed the repository, add the entry for this session
to `WORKLOG.md` (its header comes from `python tools/session_stats.py --markdown`;
see the instructions at the top of that file), with a line in its Practices
section if this was a new class of failure, and add that class to the list in
step 3 of this file. Commit it.
