---
name: upstream-report
description: Turn what wgpudawn found in other projects (pygfx shaders that Dawn rejects per the WGSL spec, wgpu-py behavior, rendercanvas, Dawn) into issue or pull request text that is ready to file - one per root cause, reproduced on their current main, checked against what is already reported or fixed. Saves drafts for the owner; files only with an explicit "file=" argument. Use for "report this upstream", "write the pygfx issues", "upstream the shader fixes", "what should we report to pygfx / wgpu-py", "prepare the upstream reports".
argument-hint: "[pygfx | wgpu-py | rendercanvas | dawn] [file=<draft name>]"
---

# Upstream reports

Dawn's shader compiler (Tint, the one in Chrome) follows the WGSL
specification more strictly than naga, so running wgpu-py's and pygfx's code
on Dawn finds real defects in them: shaders that no browser will accept,
reliance on limits above what WebGPU guarantees. Those are worth more fixed
upstream than documented here. This skill produces the reports. It does not
send them: writing on other people's repositories is the owner's decision,
every time.

The projects owe this one nothing (a Dawn backend was offered to wgpu-py as
pull request 840 and was not merged), and their maintainers do not use Dawn.
A report is useful to them only if it stands on its own: their code, the rule
in the specification, the effect in a browser, a fix that does not hurt the
wgpu-native path. It must not read as an advertisement for wgpudawn, and it
must be right. One wrong or duplicate report costs the trust that the next
ten need.

Arguments (optional): `$ARGUMENTS`

* a project name: only reports for that project.
* `file=<draft name>`: file that one draft (step 5). Without it, nothing is
  written outside this repository.

## 1. Collect the findings

```sh
python tools/maintenance_status.py --only upstream-reports
python -c "import json; [print(k, '|', v) for k, v in json.load(open('website/notes.json')).items() if not k.startswith('_')]"
grep -n -i "upstream\|pygfx\|wgpu-py\|rendercanvas" WORKLOG.md | grep -i "report\|bug\|fix\|wrong"
git log --format="%h %s%n%b" | grep -i -B2 -A2 "upstream\|to fix in pygfx\|send the fix"
ls nogit/upstream-reports 2>/dev/null
```

The sources: `website/notes.json` (why an example fails on the website; the
entries that name pygfx's shaders or limits), the reports at the end of
earlier sessions (`WORKLOG.md`), comments in `tests/` where a wgpu-py test or
shader was adapted because it was wrong, and drafts that already exist in
`nogit/upstream-reports/`.

Group them by root cause, not by symptom. Seven failing examples of
`notes.json` are one defect in three shader files (`textureSample` outside
uniform control flow), three more are one (five bind groups). One report per
root cause and per project.

Not everything in `notes.json` is a defect of somebody else: an example that
needs PyAV, a data set that the site does not ship, or a blocking call in a
draw callback is a limit of the browser or of the site. Leave those out.

## 2. Reproduce on their main

A report against an old commit is noise. Use their current `main`, and the
loud environment: natively, where the error has the message and the line.

```sh
git -C ../pygfx-src fetch -q origin main && git -C ../pygfx-src checkout -q FETCH_HEAD
RENDERCANVAS_FORCE_OFFSCREEN=1 python -c "
import runpy, sys
m = runpy.run_path(sys.argv[1], run_name='example')      # not __main__: the example does not enter its event loop
m['canvas'].request_draw(m.get('animate') or (lambda: m['renderer'].render(m['scene'], m['camera'])))
print('drew', m['canvas'].draw().shape)" ../pygfx-src/examples/feature_demo/volume_render1.py 2>&1 | grep -v "^Warning"
```

(`../pygfx-src` is installed editable in the development environment, with
the test shim that makes `import wgpu` wgpudawn; adapt the names `canvas`,
`renderer`, `scene`, `camera` to the example. Put the checkout back on the
pinned commit afterwards: step 5 of `sync-upstream`.)

For each root cause, get:

* The file and line in their repository on `main` (the error gives the line
  of the generated shader; find the source with
  `grep -rn "<the offending line>" ../pygfx-src/pygfx/renderers/wgpu/wgsl/`), as a
  permalink with the commit hash.
* The exact error of Tint.
* The rule: the section of https://www.w3.org/TR/WGSL/ or
  https://www.w3.org/TR/webgpu/ that says so, quoted in one sentence (for
  example "Uniformity analysis" for `textureSample`; `maxBindGroups` has a
  guaranteed default of 4 in "Limits").
* The smallest reproduction that does not need wgpudawn. For a shader: a
  WGSL snippet of a few lines with the same construct, which anyone can paste
  into a `createShaderModule` call in Chrome. For a limit: the number and
  where it is requested. If a reproduction needs wgpudawn, say so plainly.
* Whether it is gone: if `main` no longer fails, there is nothing to report.
  Note that the pin of pygfx can move (`update-website`) and that the note in
  `website/notes.json` can go.

For wgpu-py, the same with `python tools/upstream_diff.py main` (it fetches
wgpu-py into `build/upstream/wgpu-py`) and the file on `origin/main` there.

## 3. Check that it is not known

```sh
gh search issues --repo pygfx/pygfx "textureSample uniform control flow" --json number,title,state,url
gh search prs --repo pygfx/pygfx "textureSampleLevel" --json number,title,state,url
gh issue list -R pygfx/pygfx --state all --search "<two or three distinctive words>" --json number,title,state,url
```

Search with several wordings (the function name, the error text, the example
name, "Dawn", "Chrome", "browser", "Tint"), in issues and pull requests, open
and closed. Also look at what the project itself is doing about browsers
(wgpu-py has work on a backend for Pyodide): the same defect is often already
discussed there under another name, and then the useful contribution is a
comment with the precise rule and fix on that thread, not a new issue.

Found and open: the draft becomes a short comment for that thread, only if it
adds something (the rule, a fix). Found and fixed: nothing to do; record the
link. Found and declined: do not reopen it; tell the owner.

## 4. Write the draft

One file per report, `nogit/upstream-reports/<project>-<slug>.md` (`nogit/` is
not committed), in this form:

```
<!-- to: pygfx/pygfx | kind: issue | checked against main <hash> on <date> | duplicates searched: <the queries> -->
# <title: their code and the rule, e.g. "Volume shaders call textureSample in non-uniform control flow">

<body>
```

The body, in their terms, short:

1. What is wrong, in one sentence, with the permalink.
2. The rule, quoted, with the link to the specification.
3. What happens: accepted by naga, rejected by Tint, hence it fails in
   Chrome and Edge (the browsers that ship WebGPU on Dawn) and on any Dawn
   backend. The exact error.
4. The minimal reproduction.
5. The fix, concretely (for example: `textureSampleLevel` with an explicit
   level inside the loop, or sampling before the branch), and what it changes
   for the wgpu-native path (nothing, or what).
6. One line at the end: how it was found (running the pygfx examples on a
   Dawn backend, wgpudawn, with the link to its gallery) and that the report
   was prepared by an AI agent and checked by the person who files it.

If the fix is small and you can verify it, prepare it as well: make the change
in `../pygfx-src` on a branch from their `main`, run their tests on wgpudawn
(`pytest tests` there) and on wgpu-py (the separate environment of step 2 of
the `triage` skill, with pygfx installed in it), and save
`git -C ../pygfx-src diff > nogit/upstream-reports/<project>-<slug>.patch`.
A patch that was only run on Dawn is not verified: their path is wgpu-native.
Follow their contribution conventions (read `CONTRIBUTING` or the last merged
pull requests for the title style, formatting and whether a changelog entry
is expected). Then reset `../pygfx-src` to the pinned commit.

## 5. Filing (only with `file=<draft name>`)

Without the argument, stop after step 4: list the drafts and say, for each,
the one command that would file it.

With it, for that draft only: read it once more against their `main` as it is
now (step 2 and 3 again if the draft is older than a week), then

```sh
gh issue create -R <owner>/<repo> --title "<title>" --body-file <the body, without the first comment line and the title>
```

A pull request is opened from the owner's fork, as a draft, and only when the
argument names a `.patch`; follow the owner's conventions for pull requests.
Never file more than what was named, never file the same finding in two
projects, and never comment on a filed report again without being asked.

Afterwards record the link where the finding is recorded: in the note of
`website/notes.json` for each example that it explains ("Reported: pygfx/pygfx
issue N"), and commit that.

## 6. Report

End with a table: finding, project, state on their `main` (still there or
gone), what exists upstream already (links), the draft file, and the command
that files it. Then what is not worth reporting, and why.

Finally, if the session changed the repository, add the entry for this session
to `WORKLOG.md` (its header comes from `python tools/session_stats.py --markdown`;
see the instructions at the top of that file), and commit it.
