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

**Limits and irreversible steps**

* Publishing (a tag, hence PyPI) only from a commit whose CI run was seen
  green, and only when the human has said to. Everything before that is
  cheap to redo; that step is not. (2026-10-12)
* Outward actions on other people's projects (issues, pull requests upstream)
  are proposed to the human with the text ready, not done. (2026-10-12)

## Sessions

<!-- Newest first. `python tools/session_stats.py --markdown` makes the header. -->
