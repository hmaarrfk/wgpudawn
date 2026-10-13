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

To update Dawn: `/update-dawn`. To port a new wgpu-py release: `/sync-upstream`.
Both release with the `release` argument. To update the website (the pygfx
examples running in the browser, `website/`): `/update-website`.
