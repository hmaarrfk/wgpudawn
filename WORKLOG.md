# Work log

wgpudawn is maintained by AI agents (see the README). This is the log of that
work: one entry per working session, newest first, with what was asked, what
was done, what it took, and what was learned about working this way. It is
part of the repository so that anybody can see how the project is made, and so
that the next agent starts from what the previous ones learned.

**Agents: you maintain this file.** At the end of every session that changes
the repository (a skill run or anything else), add an entry at the top of
[Sessions](#sessions):

1. `python tools/session_stats.py --markdown` prints the header of the entry
   with the facts (duration, human prompts, model, tokens, API-equivalent
   cost), from the transcript of the session. Do not estimate these by hand.
2. Fill in: what the human asked for (paraphrased, one line per request, in
   order; never paste prompts verbatim or anything private), what was
   delivered (with commit hashes, CI runs, releases), what went wrong and how
   it was found, and what is left open.
3. If the session taught something that the next agent should do differently,
   add or sharpen a line in [Practices](#practices), and, when it is a rule
   for a specific task, in the skill for that task (`.claude/skills/`). A
   practice that turned out wrong is removed, not kept with a caveat.

Keep entries factual and short. The numbers are the transcript's; the cost is
what the tokens would cost at the list prices of the API
(`tools/model_prices.json`), not a bill.

## Practices

What has worked, and what has not, in running this project with agents. Each
line is here because of something that happened; the session that taught it is
in parentheses.

**Giving the work**

* State the goal and the constraints, not the steps: "standalone, co-installable,
  version from tags, wheels for these platforms, test by running pygfx's test
  suite" was enough to build the project. The constraints ("never ship a `wgpu`
  module") are what the agent cannot guess. (2026-10-12)
* Say what you will not decide ("you may push directly to main") and what
  stays yours (tags publish to PyPI). An agent that knows where the line is
  does not stop to ask on the near side of it. (2026-10-12)
* Steer while it works. Short messages mid-session ("also upload the Pyodide
  wheel", "explain why each one cannot run") were cheaper than a longer brief
  up front, because they were written after seeing results. (2026-10-12)

**Doing the work**

* Make the truth mechanical. Every claim the project makes is produced by a
  command: the version by the git tag, the bindings by `tools/update_dawn.py`,
  "this example works" by `website/check.mjs`, the numbers in this file by
  `tools/session_stats.py`. Then a later agent can re-derive instead of
  trusting. (2026-10-12)
* Check the checker. The first version of the example checker reported 193
  working examples; 7 of them drew nothing, because the browser reports GPU
  validation errors asynchronously and the checker did not listen. A native
  run of the same examples showed it. A pass that cannot fail is not a
  result. (2026-10-12)
* Reproduce where the error is loud. The same failure was an anonymous
  "invalid pipeline" in the browser and a precise WGSL error with a line
  number natively. Debug in the environment that tells you the most, then
  confirm in the one that matters. (2026-10-12)
* Run the real thing early, on every platform. Local Linux was green for an
  hour while the first CI run found: a compiler too old on one macOS runner,
  a Windows DLL search rule, and GPU features missing on virtual machines.
  None were visible from one machine. (2026-10-12)
* Slow steps go first and in the background (Dawn builds, CI); do not wait on
  them, and do not cancel them with an unrelated push. Scope caches so that a
  change for one platform does not rebuild five others. (2026-10-12)
* When a difference is the other implementation being wrong per the spec
  (pygfx shaders that Dawn rejects), do not paper over it: record it with the
  rule and the fix, and show it as a known failure. (2026-10-12)

* Never cut the output of the command that decides whether to push. A check
  whose last two lines were all that was read had crashed at start. Read the
  exit code and the summary line, or do not push. (2026-10-12)
* Look at the product, not only at its tests. The first deployment had black
  thumbnails while every job was green, because nothing asserted that a
  picture shows something. Add the assertion when you find such a gap (the
  checker now refuses a mostly black gallery). (2026-10-12)
* When a fix for an environment you cannot see fails twice, change the
  approach instead of guessing a third time: pictures that need a GPU are
  taken where there is one, and kept in the repository. (2026-10-12)
* Measure before and after, with a harness that stays: "fast" became
  `check.mjs --warm`, which reports click-to-first-frame for every example and
  fails when warm and cold disagree. (2026-10-12)

**Using several agents**

* Parallelize by ownership of files, not by topic: one agent owned three
  website files, one the backend, one read-only research; the main session
  kept CI and the build tooling. Nothing collided. State in each brief which
  files are off limits. (2026-10-12)
* Research agents before building: "is there an imgui wheel for this exact
  Pyodide?" (yes, on PyPI) and "can PyTorch run here?" (yes, and it would not
  help) each took a few minutes and saved a build that was not needed and a
  feature that was not worth it. Ask for evidence and for what was verified
  versus inferred. (2026-10-12)
* An agent's report is a claim, not a result: the main session re-ran what
  mattered (the examples that were said to be broken) before acting on it.
  (2026-10-12)

* A page that diagnoses must itself be run after every change of what it
  tests: the wgpudawn step of `diagnose.html` broke when the site moved from
  wheels to a bundle, and nobody saw, because the page was only read. (2026-10-13)
* `can_run_sync()` being true does not mean `run_sync` works (Safari 27). Do
  the waiting with `await` wherever the code is ours, and keep blocking for
  what an example itself asks. (2026-10-13)

* When a browser on a device you do not have fails, show the message of the
  error before anything else (not only its stack), and find a way to
  reproduce it locally: here the same engine with the device's user agent
  did, after five rounds without. (2026-10-13)
* A web server of a check must serve what the site serves: `check.mjs` had
  no type for `.wasm`, which only mattered once the site hosted Pyodide
  itself, and looked like a hang. (2026-10-13)

**Limits and irreversible steps**

* Publishing (a tag, hence PyPI) only from a commit whose CI run was seen
  green, and only when the human has said to. Everything before that is
  cheap to redo; that step is not. (2026-10-12)
* Outward actions on other people's projects (issues, pull requests upstream)
  are proposed to the human with the text ready, not done. (2026-10-12)

* A fix removes the first error, not the last. After fixing what an example
  reported, run it again in the browser before saying that it works: the
  limits of a browser are lower than those of a native device. (2026-10-13)

* A picture that "looks plausible" is not checked. Compare the picture from
  the browser with the same example rendered natively before it becomes the
  reference; a grid with holes looks like a design. (2026-10-13)
* When the calls and the data on the GPU are right and the picture is wrong,
  the data was wrong before it got there: check the values, not the
  plumbing. And a browser is a different machine: its clock is coarse on
  purpose. (2026-10-13)

## Sessions

<!-- Newest first. `python tools/session_stats.py --markdown` makes the header. -->

## 2026-10-13 - Python starts with the gallery; the first release

Same session, continued.

* The gallery starts the interpreter by itself after it has loaded, so that
  the first example opens as the later ones do (0.1 s instead of 1.1 s
  locally).
* PyPI refused both release candidates: the publisher registered there named
  the workflow `wheels.yml`, the repository had `ci.yml`. The error message
  of PyPI lists what the run claimed, not what PyPI expects, so only the
  human could see the difference. The workflow file is renamed.
* 0.0.1 is on PyPI, with a release on GitHub; the publish job makes the
  release from now on.
* Objects were missing in the browser (most spheres of pbr2 in Safari, a
  seventh of the images of labelled_image_grid in Chrome). The reference
  picture in this repository had the holes too, and had passed as "looks
  plausible". Every WebGPU call was right and so were the buffers on the
  GPU; the positions in them were not. pygfx uses `perf_counter_ns()` as the
  version of a transform, browsers limit the resolution of that clock, and
  the second of two changes in one tick was lost. Fixed on the pygfx branch;
  all pictures of the gallery were made again, on a GPU, and looked at.

## 2026-10-13 - The website on a branch of pygfx with the fixes it needs

Same session, continued (15.4 h wall clock, 48 human prompts by now). The
human opened an example in Safari on a Mac and pasted the error; then asked
for a branch of pygfx with what needs fixing there, an issue that lists such
branches, and whether the site had them.

* Safari rejects `let tex: texture_2d<f32> = colorTex;` in pygfx's
  anti-aliasing shaders. The specification agrees with Safari; Tint and naga
  let it pass. Found by dumping the shaders natively and reading line 114.
* `hmaarrfk/pygfx@webgpu-portability`: four commits (textureSample in uniform
  control flow, the physical material within 4 bind groups, the texture view
  of ComputeShader, the `let`). Checked on wgpudawn and on wgpu-native, where
  the pictures are the same before and after. Not offered upstream: issue 2
  lists the branches of other projects and why each matters.
* The site and the pygfx job of CI now build from that branch
  (`upstream.json` has the repository too). Nine more examples work; the
  site says that pygfx has fixes on top, and no longer says "unmodified".
* Two examples got past their first error and met the next limit: 13 uniform
  buffers per stage (12 guaranteed), 1024 invocations per workgroup (256).
  The notes say that now.

## 2026-10-13 - Safari on iOS: the cause, and a Pyodide that the site patches

Same session, continued. The human ran `diagnose.html` on an iPhone five more
times, the last three from a server on the local network, which made each
round a minute instead of a deployment.

* The reports had the stack of the fatal error and never its message: an
  Error's `stack` has the message in Chrome, not in Safari. With the message
  shown it was `SuspendError: JavaScript frames found between
  WebAssembly.Suspending and WebAssembly.promising`.
* The frame numbers of the stack were mapped to names with the export table
  of `pyodide.asm.wasm` (`JsvPromise_Syncify` called by `run_sync`).
* Cause: CPython's call trampoline. Pyodide's runtime uses a JavaScript one
  when the user agent is iOS (a workaround for a WebKit bug of iOS 18.3.1),
  and JSPI cannot suspend through a JavaScript frame. Reproduced here in
  Playwright's WebKit by giving it the iPhone's user agent; gone when the
  check is removed, here and on the iPhone.
* `website/build.py` now serves the core of Pyodide itself with that check
  limited to browsers without JSPI (`IOS_TRAMPOLINE`), and the WebKit
  exception of `runner.canBlock()` is gone. All 186 examples still work in
  Chrome; the human saw the gallery work on the iPhone from the local server.
* 0.0.1rc1 did not publish (a test failed on `version_info` of a
  pre-release: fixed). 0.0.1rc2 built and tested everywhere and was refused
  by PyPI: no trusted publisher matches (owner's to configure).

## 2026-10-13 - Everything that was due: Dawn, the CI, the first release candidate

Same session, continued: the human asked for an issue to track the Safari
crash (#1), for everything out of date to be updated, and said to push the
release candidate. Totals of the whole session at this point: see the header
that `python tools/session_stats.py --markdown` prints (about 11 h wall
clock, 31 human prompts, `claude-opus-5-5` (Anthropic)).

* **Dawn** v20260929.200159 -> v20261009.190412 (`update-dawn`): one added
  feature enum in the header, nothing to adapt. Tests, pygfx's tests and the
  benchmark verified locally before the push.
* **CI** (`refresh-infra`), verified by a run on a branch (38387421642)
  before `main`: the actions at their current majors, cibuildwheel 4.3.1,
  Python 3.15 in the test matrix, puppeteer-core 25, webgpu 0.6.2, ruff
  0.17.0. cibuildwheel 4 repairs Windows wheels with delvewheel, so they now
  carry `msvcp140*.dll`; found by comparing the contents of the wheels of the
  two runs, kept, and noted in `LICENSES/README.md`.
* **0.0.1rc1** tagged on a3097e6, the newest commit whose CI was green at
  that moment (not on the commits above, which were not yet tested on `main`).
* Left as it is: `ilammy/msvc-dev-cmd@v1` (runs on a deprecated Node.js; no
  newer release exists), `ubuntu-latest` (moves to Ubuntu 26 from 2026-10-19;
  not tried ahead), FreeType 2.13.3 for the website (2.15.0 exists; the
  pictures cannot be compared on this machine right now).

## 2026-10-13 - Safari: examples without stack switching

Same session as the entry below, continued after the human ran
`diagnose.html` on an iPhone (Safari 27.0.1) and pasted the report. Totals of
the whole session at this point: 9.56 h wall clock, 4.14 h agent working, 28
human prompts, `claude-opus-5-5` (Anthropic), $60.14 at API list prices.

**What the report said.** WebGPU works, JSPI exists and works in a bare
WebAssembly module, `pyodide.ffi.can_run_sync()` is true, and the first
`pyodide.ffi.run_sync` is a fatal error of the interpreter. Every example
used it at least once: to get the GPU device.

**What changed**

* `webhost.warm()` awaits the adapter and the device before an example runs,
  so an example that only draws needs no stack switch, in any browser.
* Where blocking cannot work (`runner.canBlock()`: no JSPI, or WebKit;
  `?jspi=0` / `?jspi=1` override it), `can_run_sync` says no, so that the
  blocking API raises an exception instead of crashing the interpreter.
* `check.mjs --no-blocking` checks the site as such a browser runs it: 182 of
  the 186 working examples start without an error in Chrome that way. The
  four that need blocking read back from the GPU (`offscreen`,
  `hirez_screenshot`) or configure the device themselves (`gpu_selection`,
  `reactive_rendering`).
* `diagnose.html`: the tests that do not block run first, so that a report
  from Safari says whether the rest works; its wgpudawn step asked for a wheel
  that the site no longer has (it failed everywhere) and now uses the bundle.

**Not verified.** No Safari here: that the examples now run on the iPhone is
expected from the report, not seen. And the pictures of this check were
blank, with the previous build too (headless Chrome did not show the canvas
on this machine at the time), so "works" here is "started without an error".

## 2026-10-13 - Creating the project: package, wheels, website, maintenance

| | |
|---|---|
| Session | `7a75407f-39ea-41af-b578-d4d4c430723c` |
| When (UTC) | 2026-10-13T00:51:56+00:00 to 2026-10-13T05:17:59+00:00 |
| Duration | 4.43 h wall clock, 3.59 h agent working |
| Human prompts | 26 (1288 words) |
| Subagents | 6 |
| Model | `claude-opus-5-5` (Anthropic): 506 requests; tokens: 1,088 input, 310,952 output, 148,252,520 cache read, 3,536,259 cache write; $55.55 at API list prices |
| API-equivalent cost | $55.55 (estimate; see tools/session_stats.py) |

**What the human asked for** (paraphrased, in order)

1. Turn the declined pull request pygfx/wgpu-py#840 into a standalone, co-installable
   package `wgpudawn`: version from git tags, wheels for Windows, macOS and Linux on
   x86-64 and arm64, tested by running pygfx's test suite through a test-only `wgpu` shim.
2. Mirror wgpu-py's versions so that it is a drop-in replacement, and write skills so that
   one command keeps the project up to date.
3. Say in the README what the project is: a Dawn reference implementation after wgpu-py's
   design, maintained by AI agents.
4. Publish the Pyodide wheel too. (PyPI was pre-registered by the human.)
5. How to get around rendercanvas and pygfx importing `wgpu` by name?
6. A dedicated skill for following Dawn aggressively; versions as X.Y.Z.N.
7. A github.io site with pygfx's examples running in the browser; a skill for it; make it
   sleek and visual; find out whether imgui-bundle and PyTorch can run there.
8. Explain, per example, why it cannot run.
9. A work log with practices, in the repository, maintained by the agents.
10. Review the maintenance tasks, write a skill for each and one that runs them all.
11. Feedback on the first deployment: highlighting, aspect ratios, full screen; make the
    sun the logo.
12. Help diagnose an iPhone on which the examples spin forever.
13. Make navigating between examples fast; the pages need not be real pages.

**What was delivered**

* The package: wgpu-py 0.32.0 (+6 commits) with the Dawn backend of #840, Dawn
  v20260929.200159 linked statically, one abi3 wheel per platform (6) plus a Pyodide
  wheel; `wgpudawn.install_as_wgpu()`; 226 tests; pygfx's 354 unit tests pass on it.
  First fully green CI on all platforms: run 38335939446; with the website as it is now: run 38349679065.
* The website, https://www.markharfouche.com/wgpudawn/ : 186 of 214 pygfx examples run in
  the browser (imgui included); 14 do not work yet and 14 cannot run in a browser, each
  with its reason. One interpreter for the whole visit: 108 ms median from click to first
  frame (was 2.3 to 4.6 s). `diagnose.html` tests a browser step by step.
* Nine skills (`maintain`, `update-dawn`, `sync-upstream`, `update-website`, `ci-doctor`,
  `release`, `refresh-infra`, `triage`, `upstream-report`), `tools/maintenance_status.py`,
  `tools/update_dawn.py`, `tools/upstream_diff.py`, and this log with
  `tools/session_stats.py`.
* Commits beef83d to 8327285 on `main`. Six subagents: two research (imgui-bundle: a
  wheel for our Pyodide exists on PyPI; PyTorch: possible but not useful here), the site's
  design, native debugging of failing examples, the maintenance review, and the fast
  navigation.

**What went wrong, and how it was found**

* CI, first runs: Xcode 15 cannot compile Dawn (moved the build to macos-15); Windows could
  not load `d3dcompiler_47.dll` (`DAWN_FORCE_SYSTEM_COMPONENT_LOAD`); macOS runners lack
  timestamp queries; pytest picked up two conftests in the pygfx job. All only visible on
  the runners.
* The example checker reported 193 working examples when 186 were: GPU validation errors
  arrive asynchronously in a browser and nothing listened. Found by running the same
  examples natively. The seven are pygfx shaders and layouts that Dawn rejects per the
  WGSL and WebGPU specs.
* A push without having seen the check pass: I had cut the checker's output to two lines,
  which hid a crash at start-up that I had just introduced (binding its server to
  127.0.0.1). The website job failed; fixed in the next commit.
* The first deployment had black thumbnails, and nobody had looked: without a GPU, Chrome
  leaves a WebGPU canvas black. Two attempts to fix it on the runner failed (software
  compositing flags; reading the canvas back in the page). The pictures are now taken on a
  GPU and kept in the repository; the checker refuses a mostly black gallery.

**Open**

* No release yet: the first tag (a release candidate) is the human's to push, or to ask
  for (`/release`).
* iPhone/Safari: Pyodide reports a fatal error at the first JSPI stack switch. The site now
  avoids that switch on import and shows the error; a report from `diagnose.html` on the
  phone is needed to say more.
* Reports for pygfx (in `website/notes.json`): `textureSample` in non-uniform control flow
  in three shaders; five bind groups for some materials; a NaN constant in an example. To
  be filed upstream, with the human's go-ahead (`/upstream-report`).
* Dawn is six releases behind (`/update-dawn`); action versions and Python 3.15
  (`/refresh-infra`). See `python tools/maintenance_status.py`.
