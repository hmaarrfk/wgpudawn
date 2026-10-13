# wgpudawn

The wgpu-py API with a Dawn backend, as a standalone package that is
co-installable with wgpu-py. The goal is to be a drop-in replacement for
wgpu-py, version for version. Read `README.md` first.

* `wgpudawn/`: derived from wgpu-py's `wgpu/`. Keep the diff with wgpu-py small
  (no reformatting or renaming of ported code); `upstream.json` records the
  wgpu-py commit and the Dawn release that the code corresponds to.
* `wgpudawn/enums.py`, `flags.py`, `structs.py`, `backends/dawn/_mappings.py`
  and the `# H:` / `# IDL:` comments are written by `python codegen`.
* `wgpudawn/_lib/`: the cffi extension (`build_cffi.py`), Dawn statically linked.
* `wgpudawn.install_as_wgpu()` (`_as_wgpu.py`) is the opt-in way to make
  `import wgpu` resolve to wgpudawn at runtime. `tests/wgpu_shim/` is a test-only
  stand-in for wgpu-py that calls it. Never ship that, and never add a `wgpu`
  module to the wgpudawn package.
* The version is the git tag (miniver); tags have no `v` prefix. Pushing a tag
  publishes to PyPI. Scheme: `X.Y.Z.N` = mirrored wgpu-py version + wgpudawn
  release counter (see README).

Dev loop:

```sh
python tools/build_dawn.py --prefix ../dawn-prefix
DAWN_PREFIX=$PWD/../dawn-prefix pip install --no-build-isolation -e .
pip install --no-deps ./tests/wgpu_shim
ruff format . && ruff check . && pytest tests codegen
```

On the owner's machine the environment that has all of this is
`conda activate ../.env` (with `../dawn-prefix`, `../pygfx-src`).

## Maintenance: use the skills

Each task has a procedure in `.claude/skills/<name>/SKILL.md`. Read it and
follow it, also when you were not started through it.

* `maintain`: the periodic run. Surveys what is due, does it by the skills
  below, summarizes what waits for the owner. `/maintain dry-run` only plans.
* `ci-doctor`: CI is red, or "why did this run fail".
* `update-dawn`: move to a newer Dawn release (they are almost daily).
* `sync-upstream`: port a new wgpu-py release or its main.
* `update-website`: newer pygfx or Pyodide on the website (`website/`), or an
  example that broke.
* `refresh-infra`: actions, runner images, cibuildwheel, Python versions, npm
  and other pins.
* `triage`: open issues and pull requests; replies are drafts unless `post`.
* `upstream-report`: findings for pygfx, wgpu-py, rendercanvas, Dawn, as
  drafts; files only with `file=`.
* `release`: tag and publish to PyPI, and verify it. Only when the owner asked
  for a release (`/release`, or `release` passed to another skill).

`python tools/maintenance_status.py` says which of these are due (read-only).
Yours without asking: commits and pushes to `main`. The owner's: tags (PyPI),
anything written on other repositories, merging and closing.

## Work log

`WORKLOG.md` is the public log of how this project is made, and you maintain
it: before you finish a session that changed the repository, add an entry (its
header comes from `python tools/session_stats.py --markdown`), and update its
Practices section when the session taught something. Read the Practices
section before starting substantial work.
