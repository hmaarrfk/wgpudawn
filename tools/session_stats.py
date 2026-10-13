"""Statistics of a Claude Code session: for the work log (WORKLOG.md).

    python tools/session_stats.py                 # the most recent session of this project
    python tools/session_stats.py <session-id | path/to/session.jsonl>
    python tools/session_stats.py --markdown      # an entry header for WORKLOG.md

Claude Code keeps a transcript of every session in
``~/.claude/projects/<cwd with / replaced by ->/<session-id>.jsonl``, and those
of the subagents that the session started in ``<session-id>/subagents/``. This
script reads them and reports: when the session ran, how long the agent was
working, how many prompts the human wrote, and per model the number of requests
and tokens, with what those tokens would cost at the list prices of the API
(``tools/model_prices.json``).

The cost is an estimate of the API-equivalent value, not a bill: a session on a
subscription is not billed per token.
"""

import argparse
import datetime
import glob
import itertools
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# A gap between two transcript entries longer than this is the human being away
IDLE_SECONDS = 300


def find_transcript(arg):
    if arg and os.path.isfile(arg):
        return arg
    projects = os.path.expanduser("~/.claude/projects")
    if arg:
        matches = glob.glob(os.path.join(projects, "*", arg + ".jsonl"))
    else:
        # The sessions started from this repository or from its parent directory
        cwd = os.path.dirname(HERE)
        dirs = [d.replace("/", "-") for d in (cwd, os.path.dirname(cwd))]
        matches = [
            f for d in dirs for f in glob.glob(os.path.join(projects, d, "*.jsonl"))
        ]
    if not matches:
        sys.exit("No session transcript found; pass a session id or a path.")
    return max(matches, key=os.path.getmtime)


def read_entries(path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def human_text(entry):
    """The text that the human typed in this entry, or None."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return None
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    if not isinstance(content, str):
        return None
    # Drop what the harness wraps around or sends instead of a prompt
    text = re.sub(
        r"<(system-reminder|local-command-\w+|command-\w+|task-notification)\b.*?</\1>",
        "",
        content,
        flags=re.S,
    )
    text = re.sub(r"</?pasted_content[^>]*>", "", text).strip()
    if not text or text.startswith(
        ("[SYSTEM NOTIFICATION", "<agent-message", "Another Claude session")
    ):
        return None
    return text


def collect(path, stats, is_main):
    for entry in read_entries(path):
        ts = entry.get("timestamp")
        if ts:
            stats["timestamps"].append(
                datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
            )
        if is_main:
            text = human_text(entry)
            if text:
                stats["prompts"].append(text)
            # A prompt that was typed while the agent was working
            if (
                entry.get("type") == "queue-operation"
                and entry.get("operation") == "enqueue"
            ):
                queued = entry.get("content")
                if (
                    isinstance(queued, str)
                    and queued.strip()
                    and not queued.lstrip().startswith("<")
                ):
                    stats["prompts"].append(queued.strip())
        message = entry.get("message") or {}
        usage = message.get("usage")
        if entry.get("type") != "assistant" or not usage:
            continue
        # A response is written once per content block: count it once
        key = message.get("id") or entry.get("uuid")
        if key in stats["seen"]:
            continue
        stats["seen"].add(key)
        model = stats["models"].setdefault(
            message.get("model") or "unknown",
            {
                "requests": 0,
                "input": 0,
                "output": 0,
                "cache_read": 0,
                "cache_write_5m": 0,
                "cache_write_1h": 0,
            },
        )
        model["requests"] += 1
        model["input"] += usage.get("input_tokens") or 0
        model["output"] += usage.get("output_tokens") or 0
        model["cache_read"] += usage.get("cache_read_input_tokens") or 0
        creation = usage.get("cache_creation") or {}
        one_hour = creation.get("ephemeral_1h_input_tokens") or 0
        model["cache_write_1h"] += one_hour
        model["cache_write_5m"] += (
            usage.get("cache_creation_input_tokens") or 0
        ) - one_hour


def cost(tokens, price):
    if not price:
        return None
    return (
        tokens["input"] * price["input"]
        + tokens["output"] * price["output"]
        + tokens["cache_read"] * price["cache_read"]
        + tokens["cache_write_5m"] * price["input"] * 1.25
        + tokens["cache_write_1h"] * price["input"] * 2
    ) / 1e6


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("session", nargs="?", help="Session id or transcript path")
    parser.add_argument(
        "--markdown", action="store_true", help="Print a WORKLOG.md entry header"
    )
    parser.add_argument(
        "--prompts", action="store_true", help="Also print the human prompts"
    )
    args = parser.parse_args()

    path = find_transcript(args.session)
    session_id = os.path.basename(path)[: -len(".jsonl")]
    stats = {"timestamps": [], "prompts": [], "models": {}, "seen": set()}
    collect(path, stats, True)
    subagents = sorted(
        glob.glob(os.path.join(path[: -len(".jsonl")], "subagents", "*.jsonl"))
    )
    for sub in subagents:
        collect(sub, stats, False)

    times = sorted(stats["timestamps"])
    gaps = [(b - a).total_seconds() for a, b in itertools.pairwise(times)]
    active = sum(g for g in gaps if g < IDLE_SECONDS)
    wall = (times[-1] - times[0]).total_seconds() if times else 0
    with open(os.path.join(HERE, "model_prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    # The same prompt can be in the transcript as typed and as delivered
    prompts = list(dict.fromkeys(stats["prompts"]))

    result = {
        "session": session_id,
        "start": times[0].isoformat(timespec="seconds") if times else None,
        "end": times[-1].isoformat(timespec="seconds") if times else None,
        "wall_hours": round(wall / 3600, 2),
        "active_hours": round(active / 3600, 2),
        "human_prompts": len(prompts),
        "human_prompt_words": sum(len(p.split()) for p in prompts),
        "subagents": len(subagents),
        "models": {},
        "api_list_price_usd": 0.0,
    }
    for name, tokens in sorted(stats["models"].items()):
        usd = cost(tokens, prices.get(name))
        result["models"][name] = {**tokens, "api_list_price_usd": usd and round(usd, 2)}
        result["api_list_price_usd"] += usd or 0
    result["api_list_price_usd"] = round(result["api_list_price_usd"], 2)

    if not args.markdown:
        print(json.dumps(result, indent=2))
    else:
        print(f"## {result['start'][:10]} - <what the session was for>\n")
        print("| | |\n|---|---|")
        print(f"| Session | `{session_id}` |")
        print(f"| When (UTC) | {result['start']} to {result['end']} |")
        print(
            f"| Duration | {result['wall_hours']} h wall clock, {result['active_hours']} h agent working |"
        )
        print(
            f"| Human prompts | {result['human_prompts']} ({result['human_prompt_words']} words) |"
        )
        print(f"| Subagents | {result['subagents']} |")
        for name, m in result["models"].items():
            usd = m["api_list_price_usd"]
            print(
                f"| Model | `{name}` (Anthropic): {m['requests']} requests; tokens: "
                f"{m['input']:,} input, {m['output']:,} output, {m['cache_read']:,} cache read, "
                f"{m['cache_write_5m'] + m['cache_write_1h']:,} cache write"
                + (
                    f"; ${usd:,.2f} at API list prices |"
                    if usd is not None
                    else "; price unknown |"
                )
            )
        print(
            f"| API-equivalent cost | ${result['api_list_price_usd']:,.2f} (estimate; see tools/session_stats.py) |"
        )
    if args.prompts:
        for i, p in enumerate(prompts, 1):
            print(f"\n--- prompt {i} ---\n{p}")


if __name__ == "__main__":
    main()
