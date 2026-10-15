---
name: update-website
description: Update the wgpudawn website (the gallery of pygfx examples running in the browser) to a newer pygfx, Pyodide or wgpudawn, check every example in headless Chrome, fix or classify what breaks, and deploy by pushing to main. Use for "update the website", "update the gallery", "bump pygfx", "an example is broken on the site".
argument-hint: "[pygfx ref, default: main] [pyodide=<version>]"
---

# Update the website

The website (GitHub Pages, deployed by the `CI` workflow on every push to
`main`) runs the examples of pygfx in the browser: Pyodide + the Pyodide wheel
of wgpudawn (Dawn's Emdawnwebgpu, i.e. the browser's WebGPU) + pygfx. It is the
most demanding test this project has, and the most visible. Your job is to move
it to newer inputs, to keep every example that worked working, and to leave it
deployed. Do not ask the user anything that you can find out by running code.

Arguments (optional): `$ARGUMENTS`

* a pygfx ref (branch, tag or sha). Default: `main`.
* `pyodide=<version>`: also move to that Pyodide release (see step 5).

Whether this is due: `python tools/maintenance_status.py --only pygfx,pyodide`.
The site is also rebuilt, with the pinned inputs, by every push to `main`.

## How it fits together

* `website/build.py` assembles the site from a pygfx checkout and a directory
  of wheels. It writes `examples.json` (the examples, with what the pages need
  for each), one content-named `base.<hash>.zip` with everything that every
  example needs (wgpudawn, pygfx, the pinned wheels from PyPI, the examples),
  compiled to bytecode when `python3.14` is on the PATH, and per-example extras
  (`wheels/`, `data/`, `imageio/`). Nothing is fetched from PyPI at run time:
  every package is pinned in `website/pyodide.json` (`pypi_always`,
  `pypi_by_import`, with their own requirements in `requires`) and downloaded
  by the build with a checksum. Examples that cannot run in any browser (Qt,
  PyTorch, ...) get a `skip` reason from `UNAVAILABLE` / `SKIP_REASONS` in
  `build.py`; `website/notes.json` explains each known failure.
* The site is one page (`index.html` + `app.js`; `run.html` is written by the
  build as a copy, so that `run.html?ex=<category>/<name>` keeps working). It
  keeps **one Python interpreter for the whole visit**: `runner.js` (browser
  side) and `webhost.py` (Python side) run each example in a fresh `__main__`
  on a fresh canvas and tear the previous one down. An example that fails
  after another one ran is retried in a new interpreter before it is shown as
  failed; examples that configure the GPU device get their own (`ISOLATE` in
  `build.py`).
* `website/check.mjs` runs every example in headless Chrome, **each in a fresh
  page and interpreter**, and writes `results.json` and `shots/`. That is the
  only source of the gallery's "works" claims and pictures.
  `website/expected.json` is the list of examples known to work; CI fails when
  one of them does not. `check.mjs --warm` walks through all examples in one
  page, the way a visitor does: it must agree with the cold results (an
  example must never work, or fail, because of what ran before it), and it
  reports the time from click to first frame.
* `website/diagnose.html`: a page that tests a browser step by step (WebGPU,
  JSPI, Pyodide, wgpudawn), for bug reports. It does not use the site's code.
* `upstream.json` `pygfx.commit`: the pinned pygfx, used for the website and
  for the CI job that runs pygfx's test suite on wgpudawn.

## 1. Build locally

```sh
[ -d ../pygfx-src ] || git clone https://github.com/pygfx/pygfx ../pygfx-src
git -C ../pygfx-src fetch -q origin <ref> && git -C ../pygfx-src checkout -q FETCH_HEAD
rm -rf ../web-wheels && mkdir -p ../web-wheels      # empty: build.py takes one wheel per package, whichever sorts last
pip wheel --no-deps -w ../web-wheels ../pygfx-src
# wgpudawn and freetype-py for Pyodide, from the last green CI run on main
run=$(gh run list --branch main --workflow CI --status success --limit 1 --json databaseId --jq '.[0].databaseId')
gh run download $run -n dist-wheel-pyodide -D ../web-wheels
gh run download $run -n web-wheels -D ../web-wheels
python website/build.py --pygfx ../pygfx-src --wheels ../web-wheels --out ../site
```

(No green run yet, or its artifacts expired after 90 days: take the newest run
whose `Pyodide` job succeeded, `gh run list --branch main --workflow CI`.)

Use the wgpudawn wheel of the commit you are on: if you changed `wgpudawn/` or
the bindings, build it instead (`pyodide build --exports pyinit`, see the
`pyodide` job in `.github/workflows/wheels.yml` for the environment; the same job
shows how `website/build_freetype.sh` is run).

## 2. Check every example

```sh
(cd website && npm install --no-audit --no-fund)
CHROME_FLAGS="--use-angle=vulkan --ignore-gpu-blocklist" \
  node website/check.mjs ../site --jobs 6 --expect website/expected.json
```

Then walk through them warm, on the GPU: `node website/check.mjs ../site --warm`
(same `CHROME_FLAGS`). It must exit 0 and agree with the cold run.

`node website/check.mjs ../site --no-blocking` runs the examples as Safari
does, where Python cannot block (Pyodide's `run_sync` crashes there): all but
the few that read back from the GPU or configure the device must still start.
It overwrites `results.json`, so run the normal check last. After a change to
`website/diagnose.html`, open it with `?auto=1` and see every step pass.

(`CHROME_FLAGS="--disable-gpu"` with `--keep-shots` is what CI sees: software
WebGPU, where Chrome loses the device about a second after an example starts
drawing and the canvas stays black. "ok" there means "started and reported no
error until then"; the run on a GPU is the stronger statement. Run it that
way too before pushing.) `--failed` re-runs only what failed; `--only <text>` one
example. To watch one: `python -m http.server -d ../site 8765` and open
`http://localhost:8765/run.html?ex=<category>/<name>`.

## 3. Deal with every failure

For each example that fails, find out why, in this order:

1. **It cannot work in a browser** (needs a native window, a package without
   a Pyodide build, a device): add the module to `UNAVAILABLE` in `build.py`
   with a short reason. It is then shown as such, not as broken.
2. **The site does not provide something** (a package, a data file, a sample
   image): fix `build.py` / `pyodide.json` / `runner.js`. A package from PyPI
   goes in `pypi_by_import`, pinned, with its requirements in `requires`; a
   module that an example imports indirectly in `IMPLIED_IMPORTS` in
   `build.py`, so that it is loaded before the example runs. A glTF scene
   that an example expects in a checkout next to it (glTF-Sample-Assets) goes
   in `GLTF_SCENES`, pinned to a commit: the site serves only that scene.
3. **wgpudawn is wrong**: reproduce it natively first, where validation errors
   are raised at the failing call (in the browser they arrive later and
   anonymous: "[Invalid RenderPipeline] is invalid due to a previous error"
   means exactly that). Draw one frame of the example on wgpudawn, offscreen
   (below), fix the backend, add a test in `tests/`. A difference with what
   wgpu-py does that a user would notice is a wgpudawn bug.
4. **pygfx or the example is wrong** per the WebGPU/WGSL spec (Tint is
   strict): do not work around it here. Leave it failing, say why in
   `website/notes.json`, and put the precise report (file, error, spec rule,
   suggested fix) in your final report; the `upstream-report` skill turns
   those into issues for pygfx.

Keep `website/notes.json` true in both directions: add a note for an example
that newly fails for reason 2 (not provided yet) or 4, and remove the note of
an example that works now.

One frame of an example, natively (the development environment has pygfx
editable and the shim that makes `import wgpu` wgpudawn; adapt the names
`canvas`, `renderer`, `scene`, `camera` to the example):

```sh
RENDERCANVAS_FORCE_OFFSCREEN=1 python -c "
import runpy, sys
m = runpy.run_path(sys.argv[1], run_name='example')      # not __main__: the example does not enter its event loop
m['canvas'].request_draw(m.get('animate') or (lambda: m['renderer'].render(m['scene'], m['camera'])))
print('drew', m['canvas'].draw().shape)" ../pygfx-src/examples/feature_demo/volume_render1.py 2>&1 | grep -v "^Warning"
```

An example in `expected.json` that fails is a regression: it must be fixed
(1-3) or, only for 4 or for an input that genuinely disappeared, removed from
`expected.json` with the reason in the commit message. Never remove an entry
just to get CI green.

Then refresh the baseline with what works now:
`node website/check.mjs ../site --failed --write-expected website/expected.json`
(review the diff: it should only grow, apart from the cases above).

The pictures of the gallery are the ones this run took (`../site/shots`), and
they are kept in the repository, because CI has no GPU: there Chrome runs the
examples in software but leaves a WebGPU canvas black, so CI only records what
works (`--keep-shots`). After a check on a machine with a GPU, on its GPU
(`CHROME_FLAGS` as above, never the software mode), update them:

```sh
rsync -a --delete ../site/shots/ website/shots/
```

## 4. Look at it

Open the gallery and a few example pages in a browser, or take screenshots
with headless Chrome (puppeteer-core is in `website/node_modules`) and look at
them: the thumbnails are what people see first. A thumbnail that is blank,
mostly one color, or shows an error overlay means the example "passed" without
drawing: treat it as a failure (and consider making `check.mjs` detect it).

## 5. Pyodide update (only when asked or needed)

The Pyodide version is in four places that must agree: `website/pyodide.json`
(`version`, and inside `url`), `PYODIDE_VERSION` in `.github/workflows/wheels.yml`,
and `tests/pyodide/package.json`; `python tools/maintenance_status.py --only pyodide`
checks that. With them go `PYODIDE_BUILD_VERSION` (the pyodide-build that
supports that Pyodide) and the `python-version` of the `pyodide` job in
`wheels.yml` (the Python of that Pyodide), and the sentence about Pyodide in the
Platforms section of `README.md`.
A new Pyodide can mean a new Emscripten and platform tag
(`pyemscripten_<year>_<n>_wasm32`): then also `PLATFORM_TAG` in
`website/build_freetype.sh` (and its compiler flags: compare with
`pyodide config list`), and the pinned wheels in `pyodide.json`
(imgui-bundle and uharfbuzz must have a wheel for that tag on PyPI; if they do
not, stay on the old Pyodide and report it). `tools/gen_emdawn_glue.py` must
be run with the Emscripten of the target Pyodide, which the build does.

## 6. Record, commit, deploy

* `upstream.json`: `pygfx.commit` = the full sha that you built with.
* Commit on `main` (follow the user's commit message conventions) and push.
  CI builds the site, checks every example on SwiftShader against
  `expected.json`, and deploys. Watch it
  (`gh run watch <run-id> --exit-status`, with the id from
  `gh run list --branch main --workflow CI --limit 1`); the `Website` job
  uploads the built site as the `website` artifact also when it fails, with
  its `results.json` (`gh run download <run-id> -n website -D <dir>`). An example that works on a GPU but not on SwiftShader
  (usually a timeout) should get a more generous `--timeout` or be made
  lighter in the checker, not be dropped.
* Open the deployed site (https://www.markharfouche.com/wgpudawn/; it is what
  `gh api repos/hmaarrfk/wgpudawn/pages --jq .html_url` prints) and confirm
  that it loads and that one example runs.

## 7. Report

End with: the pygfx range (old sha -> new sha) and other inputs that changed,
the counts (work / fail / cannot run) before and after, every example whose
status changed and why, fixes made in wgpudawn, reports for pygfx, the CI run,
and the URL.


Finally, add the entry for this session to `WORKLOG.md` (its header comes from
`python tools/session_stats.py --markdown`; see the instructions at the top of
that file), and commit it.
