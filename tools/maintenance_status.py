"""Say which maintenance tasks of wgpudawn are due. Read-only.

    python tools/maintenance_status.py            # a table: task, state, detail, skill
    python tools/maintenance_status.py --json     # the same, for a program
    python tools/maintenance_status.py --only dawn,ci

It compares what the repository pins (``upstream.json``, the CI workflow, the
website and test configuration) with what exists upstream (GitHub, PyPI, npm),
and looks at the state of this project on GitHub (CI on main, issues, pull
requests, the last release). It changes nothing, here or anywhere: it only
reads files and does GET requests. GitHub is queried with the ``gh`` CLI (so
that it is authenticated); a check that cannot be done is reported as
``unknown``, not as ``ok``.

States: ``DUE`` (there is work), ``ok``, ``info`` (for the human or for a
judgment call), ``unknown`` (the check failed; the detail says why).

The ``maintain`` skill (.claude/skills/maintain/SKILL.md) starts with this,
and each line names the skill that does the task.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REPO = "hmaarrfk/wgpudawn"


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def gh(path, jq=None):
    cmd = ["gh", "api", path]
    if jq:
        cmd += ["--jq", jq]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError(out.stderr.strip().splitlines()[-1][:100])
    return out.stdout.strip()


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "wgpudawn"})
    with urllib.request.urlopen(request, timeout=30) as f:
        return json.load(f)


def git(*args):
    cmd = ["git", "-C", ROOT, *args]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


def vtuple(version):
    return tuple(int(n) for n in re.findall(r"\d+", version))


def days_since(iso):
    then = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (datetime.datetime.now(datetime.timezone.utc) - then).days


def check_tree():
    dirty = git("status", "--short").splitlines()
    ahead = git("rev-list", "--count", "origin/main..HEAD")
    detail = f"{len(dirty)} modified files, {ahead} commits not pushed"
    return ("info" if dirty or ahead != "0" else "ok"), detail


def check_ci():
    runs = json.loads(
        gh(f"repos/{REPO}/actions/runs?branch=main&event=push&per_page=10")
    )["workflow_runs"]
    if not runs:
        return "unknown", "no runs on main"
    parts = [
        f"{r['head_sha'][:7]} {r['conclusion'] or r['status']} (run {r['id']})"
        for r in runs[:3]
    ]
    # A cancelled run was superseded by a push; it says nothing
    done = [r for r in runs if r["status"] == "completed"]
    done = [r for r in done if r["conclusion"] != "cancelled"]
    detail = "newest first: " + "; ".join(parts)
    if runs[0]["status"] != "completed":
        return "info", "a run is in progress, wait for it; " + detail
    red = done and done[0]["conclusion"] != "success"
    return ("DUE" if red else "ok"), detail


def check_ci_warnings():
    """The annotations of the last completed run: deprecations announced by GitHub."""
    q = f"repos/{REPO}/actions/runs?branch=main&status=completed&per_page=1"
    runs = json.loads(gh(q))["workflow_runs"]
    if not runs:
        return "unknown", "no completed run"
    jobs = gh(
        f"repos/{REPO}/actions/runs/{runs[0]['id']}/jobs?per_page=100", ".jobs[].id"
    )
    messages, node = set(), set()
    for job in jobs.split():
        text = gh(f"repos/{REPO}/check-runs/{job}/annotations", ".[].message")
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line.split(" For more info")[0]).strip('" ')
            if "target Node.js" in line:
                node.update(re.findall(r"[\w.-]+/[\w./-]+@\S+?(?=[,.]|$)", line))
            elif re.search(r"deprecat|migrate|will be removed|no longer", line, re.I):
                messages.add(line[:230])
    if node:
        messages.add("actions on a deprecated Node.js: " + " ".join(sorted(node)))
    if not messages:
        return "ok", f"no deprecation notices in run {runs[0]['id']}"
    return "DUE", " | ".join(sorted(messages))


def check_wgpu_py():
    pin = json.loads(read("upstream.json"))["wgpu-py"]
    tags = gh("repos/pygfx/wgpu-py/tags?per_page=30", ".[].name").split()
    latest = max((t for t in tags if re.fullmatch(r"v[\d.]+", t)), key=vtuple)
    ahead = gh(f"repos/pygfx/wgpu-py/compare/{pin['commit']}...main", ".ahead_by")
    detail = f"mirrors {pin['version']} ({pin['commit'][:7]}); latest release {latest}; main is {ahead} commits ahead"
    if vtuple(latest) > vtuple(pin["version"]):
        return "DUE", detail
    return ("info" if ahead != "0" else "ok"), detail


def check_dawn():
    pin = json.loads(read("upstream.json"))["dawn"]["tag"]
    tags = gh("repos/google/dawn/releases?per_page=100", ".[].tag_name").split()
    latest = gh("repos/google/dawn/releases/latest", ".tag_name")
    behind = tags.index(pin) if pin in tags else f"more than {len(tags)}"
    detail = f"pinned {pin}; latest {latest}; {behind} releases behind"
    return ("DUE" if latest != pin else "ok"), detail


def check_pygfx():
    pin = json.loads(read("upstream.json"))["pygfx"]["commit"]
    ahead = gh(f"repos/pygfx/pygfx/compare/{pin}...main", ".ahead_by")
    detail = f"pinned {pin[:7]}; pygfx main is {ahead} commits ahead"
    return ("DUE" if ahead != "0" else "ok"), detail


def check_pyodide():
    site = json.loads(read("website", "pyodide.json"))
    ci = read(".github", "workflows", "ci.yml")
    places = {
        "website/pyodide.json version": site["version"],
        "website/pyodide.json url": re.search(r"/v([\d.]+)/", site["url"]).group(1),
        "ci.yml PYODIDE_VERSION": re.search(r'PYODIDE_VERSION: "(.+?)"', ci).group(1),
        "tests/pyodide/package.json": json.loads(
            read("tests", "pyodide", "package.json")
        )["dependencies"]["pyodide"],
    }
    if len(set(places.values())) != 1:
        return "DUE", f"the pins disagree: {places}"
    pin = site["version"]
    latest = get_json("https://registry.npmjs.org/pyodide/latest")["version"]
    build_pin = re.search(r'PYODIDE_BUILD_VERSION: "(.+?)"', ci).group(1)
    build = get_json("https://pypi.org/pypi/pyodide-build/json")["info"]["version"]
    detail = (
        f"Pyodide {pin} (latest {latest}); pyodide-build {build_pin} (latest {build})"
    )
    return ("DUE" if (latest, build) != (pin, build_pin) else "ok"), detail


def check_actions():
    ci = read(".github", "workflows", "ci.yml")
    uses = sorted(set(re.findall(r"uses: ([\w.-]+/[\w.-]+)[\w./-]*@(\S+)", ci)))
    old = []
    for repo in sorted({r for r, _ in uses}):
        latest = gh(f"repos/{repo}/releases/latest", ".tag_name")
        for ref in (ref for r, ref in uses if r == repo):
            # "v4" is up to date with v4.x; "v3.2.1" only with v3.2.1 or newer
            if re.match(r"v?\d", ref) and vtuple(latest)[: len(vtuple(ref))] > vtuple(
                ref
            ):
                old.append(f"{repo}@{ref} (latest {latest})")
    if old:
        return "DUE", "; ".join(old)
    return "ok", f"{len(uses)} action references are current"


def check_python():
    ci = read(".github", "workflows", "ci.yml")
    tested = sorted({vtuple(v) for v in re.findall(r'python: "(3\.\d+)"', ci)})
    url = "https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json"
    stable = max(vtuple(v["version"])[:2] for v in get_json(url) if v["stable"])
    floor = re.search(
        r'requires-python = ">= ?([\d.]+)"', read("pyproject.toml")
    ).group(1)
    detail = f"requires >= {floor}; CI tests {tested[0][1]}..{tested[-1][1]} of 3.x; newest stable on the runners: 3.{stable[1]}"
    return ("DUE" if stable > tested[-1] else "ok"), detail


def check_runners():
    ci = read(".github", "workflows", "ci.yml")
    labels = sorted(
        set(
            re.findall(r"\bos: ([\w.-]+)", ci)
            + re.findall(r"runs-on: ([a-z][\w.-]+)", ci)
        )
    )
    image = re.search(
        r"quay\.io/pypa/(\w+?)_\$", read("tools", "build_dawn_manylinux.sh")
    )
    return "info", f"runner images: {' '.join(labels)}; Linux wheels: {image.group(1)}"


def check_pins():
    """The other pinned versions: npm packages, and the wheels of the website."""
    out = []
    for path in ("website", os.path.join("tests", "pyodide")):
        deps = json.loads(read(path, "package.json"))["dependencies"]
        for name, spec in deps.items():
            if name == "pyodide":
                continue
            latest = get_json(f"https://registry.npmjs.org/{name}/latest")["version"]
            pinned = vtuple(spec)
            if (
                vtuple(latest)[: 1 if spec.startswith("^") else 3]
                > pinned[: len(vtuple(latest))]
            ):
                out.append(f"npm {name} {spec} in {path} (latest {latest})")
    site = json.loads(read("website", "pyodide.json"))
    sh = read("website", "build_freetype.sh")
    pins = [*site.get("pypi_always", []), *site["pypi_by_import"].values()]
    pypi = [s.split("==") for s in pins if "==" in s]
    pypi.append(["freetype-py", re.search(r"FREETYPE_PY_VERSION=(\S+)", sh).group(1)])
    for name, pinned in pypi:
        latest = get_json(f"https://pypi.org/pypi/{name}/json")["info"]["version"]
        if vtuple(latest) > vtuple(pinned):
            out.append(f"PyPI {name}=={pinned} (latest {latest})")
    return ("DUE" if out else "ok"), "; ".join(
        out
    ) or "npm and website pins are current"


def check_release():
    tags = [t for t in git("tag", "--sort=-creatordate").split() if re.match(r"\d", t)]
    try:
        pypi = get_json("https://pypi.org/pypi/wgpudawn/json")["info"]["version"]
    except Exception:
        pypi = None
    if not tags:
        return "info", f"no release tag yet; on PyPI: {pypi or 'no project'}"
    last = tags[0]
    count = git("rev-list", "--count", f"{last}..HEAD")
    days = days_since(git("log", "-1", "--format=%cI", last))
    code = git(
        "log",
        "--oneline",
        f"{last}..HEAD",
        "--",
        "wgpudawn",
        "build_cffi.py",
        "pyproject.toml",
        "setup.py",
        "upstream.json",
    )
    n_code = len(code.splitlines())
    detail = f"last tag {last}, {days} days ago; {count} commits since, {n_code} of them change what is shipped; PyPI has {pypi}"
    if pypi != last:
        return "DUE", detail + " (the tag is not what PyPI has: check the publish job)"
    return ("DUE" if n_code else "ok"), detail


def check_issues():
    q = f"repos/{REPO}/issues?state=open&per_page=100"
    items = json.loads(gh(q))
    prs = [i for i in items if "pull_request" in i]
    issues = [i for i in items if "pull_request" not in i]
    quiet = [f"#{i['number']}" for i in items if i["comments"] == 0]
    detail = f"{len(issues)} open issues, {len(prs)} open pull requests; without any reply: {' '.join(quiet) or 'none'}"
    return ("DUE" if items else "ok"), detail


def check_upstream_reports():
    notes = json.loads(read("website", "notes.json"))
    upstream = [k for k, v in notes.items() if re.search(r"pygfx's|in pygfx", v)]
    drafts = os.path.join(ROOT, "nogit", "upstream-reports")
    n = len(os.listdir(drafts)) if os.path.isdir(drafts) else 0
    detail = f"{len(upstream)} examples fail for a reason in pygfx (website/notes.json); {n} drafts in nogit/upstream-reports"
    return ("info" if upstream else "ok"), detail


def check_skills():
    """Paths that the skills and CLAUDE.md mention, and that do not exist."""
    files = [os.path.join(ROOT, "CLAUDE.md")]
    skills = os.path.join(ROOT, ".claude", "skills")
    files += [os.path.join(skills, d, "SKILL.md") for d in sorted(os.listdir(skills))]
    top = "tools|website|tests|wgpudawn|codegen|examples|LICENSES|\\.github|\\.claude"
    missing = []
    for path in files:
        text = open(path, encoding="utf-8").read()
        refs = re.findall(rf"(?<![\w./-])((?:{top})/[\w./-]*\w)", text)
        for ref in sorted(set(refs)):
            if not os.path.exists(os.path.join(ROOT, ref)):
                missing.append(f"{os.path.relpath(path, ROOT)}: {ref}")
    return ("DUE" if missing else "ok"), "; ".join(
        missing
    ) or f"{len(files)} files checked"


def check_worklog():
    dates = re.findall(r"^## (\d{4}-\d\d-\d\d)", read("WORKLOG.md"), re.M)
    last_commit = git("log", "-1", "--format=%cs")
    detail = f"{len(dates)} session entries, newest {max(dates, default='none')}; last commit {last_commit}"
    return ("DUE" if not dates or max(dates) < last_commit else "ok"), detail


CHECKS = {
    # name: (function, the skill that does the task)
    "tree": (check_tree, "-"),
    "ci": (check_ci, "ci-doctor"),
    "ci-warnings": (check_ci_warnings, "refresh-infra"),
    "issues": (check_issues, "triage"),
    "dawn": (check_dawn, "update-dawn"),
    "wgpu-py": (check_wgpu_py, "sync-upstream"),
    "pygfx": (check_pygfx, "update-website"),
    "pyodide": (check_pyodide, "update-website"),
    "actions": (check_actions, "refresh-infra"),
    "python": (check_python, "refresh-infra"),
    "runners": (check_runners, "refresh-infra"),
    "pins": (check_pins, "refresh-infra"),
    "upstream-reports": (check_upstream_reports, "upstream-report"),
    "skills": (check_skills, "maintain"),
    "worklog": (check_worklog, "maintain"),
    "release": (check_release, "release"),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--only", default="", help="Comma-separated names of checks")
    args = parser.parse_args()
    names = [n for n in CHECKS if not args.only or n in args.only.split(",")]

    def run(name):
        try:
            state, detail = CHECKS[name][0]()
        except Exception as err:
            state, detail = "unknown", f"{type(err).__name__}: {err}"[:200]
        return {
            "task": name,
            "state": state,
            "detail": detail,
            "skill": CHECKS[name][1],
        }

    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(run, names))
    if args.json:
        print(json.dumps(results, indent=2))
        return
    for r in results:
        print(f"{r['task']:<17}{r['state']:<8}{r['skill']:<16}{r['detail']}")


if __name__ == "__main__":
    main()
