#!/usr/bin/python3
"""A stand-in for gh (2.101), for the line's suite: `gh run list` only, answering as the real one does (rule 15: it
refuses what the real one refuses, not only what the line's own calls happen to send).

The runs on GitHub, newest first, come from the environment:
  FAKE_GH_RUNS       a JSON list of runs (databaseId, attempt, conclusion, status, url, headSha, headBranch,
                     workflowName); headBranch defaults to main, workflowName to ci, attempt to 1.
  FAKE_GH_COMPLETED  (older tests) the latest completed run, as a JSON list; FAKE_GH_LATEST: the newest run of any
                     status, when it is not that one. Text that is not JSON is answered as it is, as a broken gh would.
  FAKE_GH_EXIT       gh fails (signed out, offline) with that exit code.
  FAKE_GH_VIEW_EXIT  `gh run view` alone fails (GitHub's 502 for a log), with that exit code.
  FAKE_GH_CALLS      a file each call is appended to, one line each.

  FAKE_GH_LOGS       a JSON object, "<run>/<attempt>" -> a file holding `gh run view <run> --attempt <attempt>
                     --log-failed`'s text as GitHub prints it (job, step, then the timestamped line, tab-separated);
                     an attempt with no file prints nothing, as the real gh does for an attempt that passed.

`run list`: --branch/-b, --status/-s, --commit/-c, --workflow/-w, --limit/-L (default 20), --json, -q/--jq (only
`length`, the one the push script uses). The real gh refuses an unknown flag, an unknown --json field, a --jq
without --json and a --status that is not one of its own; so does this. `run view <run> [--attempt N] --log-failed`: a run not on the list or an attempt it never had is
HTTP 404, as the real gh says; the run's current attempt while it is not completed is "still in progress". A call to
rerun or cancel a run is refused
and logged: the line never changes anything on GitHub.
"""
from __future__ import annotations

import json
import os
import sys

FIELDS = {"attempt", "conclusion", "createdAt", "databaseId", "displayTitle", "event", "headBranch", "headSha", "name",
          "number", "startedAt", "status", "updatedAt", "url", "workflowDatabaseId", "workflowName"}
STATUSES = {"queued", "completed", "in_progress", "requested", "waiting", "pending", "action_required", "cancelled",
            "failure", "neutral", "skipped", "stale", "startup_failure", "success", "timed_out"}
STATES = {"queued", "completed", "in_progress", "requested", "waiting", "pending"}


def fail(msg: str, code: int = 1) -> None:
    sys.stderr.write(msg + "\n")
    sys.exit(code)


def runs() -> tuple[list | None, str | None]:
    """The runs, newest first, or (None, raw text) when the environment holds text that is not JSON."""
    if "FAKE_GH_RUNS" in os.environ:
        raw = os.environ["FAKE_GH_RUNS"]
        try:
            return json.loads(raw), None
        except ValueError:
            return None, raw
    green = '[{"databaseId": 44000000001, "conclusion": "success", "status": "completed", "url": "https://github.invalid/r/1"}]'
    completed = os.environ.get("FAKE_GH_COMPLETED", green)
    latest = os.environ.get("FAKE_GH_LATEST", completed)
    try:
        done = json.loads(completed)
    except ValueError:
        return None, completed
    newest = json.loads(latest)
    return ([r for r in newest if r not in done] + done), None


def norm(r: dict) -> dict:
    return {"headBranch": "main", "workflowName": "ci", "attempt": 1, "headSha": "", "event": "push", **r}


def options(args: list[str], takes: dict[str, str], flags: set[str] = frozenset()) -> tuple[dict, list[str]]:
    out, rest, i = {}, [], 0
    while i < len(args):
        a = args[i]
        name, _, val = a.partition("=")
        if name in takes:
            if not val:
                i += 1
                if i >= len(args):
                    fail(f"flag needs an argument: {name}")
                val = args[i]
            out[takes[name]] = val
        elif a in flags:
            out[a.lstrip("-")] = True
        elif a.startswith("-"):
            fail(f"unknown flag: {name}\n\nUsage:  gh run list [flags]")
        else:
            rest.append(a)
        i += 1
    return out, rest


def run_list(args: list[str]) -> None:
    o, rest = options(args, {"--branch": "branch", "-b": "branch", "--status": "status", "-s": "status",
                             "--commit": "commit", "-c": "commit", "--workflow": "workflow", "-w": "workflow",
                             "--limit": "limit", "-L": "limit", "--json": "json", "-q": "jq", "--jq": "jq",
                             "--event": "event", "-e": "event", "--user": "user", "-u": "user"})
    if rest:
        fail(f'unknown arguments {rest!r}; please quote all values that have spaces')
    if "jq" in o and "json" not in o:
        fail("cannot use `--jq` without specifying `--json`")
    if "status" in o and o["status"] not in STATUSES:
        fail(f"invalid argument \"{o['status']}\" for \"-s, --status\" flag: valid values are "
             "{" + "|".join(sorted(STATUSES)) + "}")
    have, raw = runs()
    if have is None:
        print(raw)
        return
    out = []
    for r in map(norm, have):
        if "branch" in o and r["headBranch"] != o["branch"]:
            continue
        if "commit" in o and r["headSha"] != o["commit"]:
            continue
        if "workflow" in o and o["workflow"] not in (r["workflowName"], r.get("path", "ci.yml")):
            continue
        if "status" in o:
            key = "status" if o["status"] in STATES else "conclusion"
            if r.get(key) != o["status"]:
                continue
        out.append(r)
    out = out[:int(o.get("limit", "20"))]
    if "json" not in o:
        for r in out:
            print("\t".join(str(r.get(k, "")) for k in ("status", "conclusion", "databaseId")))
        return
    fields = o["json"].split(",")
    bad = [f for f in fields if f not in FIELDS]
    if bad:
        fail(f"Unknown JSON field: {bad[0]!r}\nAvailable fields:\n  " + "\n  ".join(sorted(FIELDS)))
    shaped = [{f: r.get(f, "") for f in fields} for r in out]
    if "jq" in o:
        if o["jq"] != "length":
            fail(f"this stand-in answers only --jq length, not {o['jq']!r}")
        print(len(shaped))
        return
    print(json.dumps(shaped))


def run_view(args: list[str]) -> None:
    o, rest = options(args, {"--attempt": "attempt", "-a": "attempt", "--job": "job", "-j": "job", "--json": "json",
                             "-q": "jq", "--jq": "jq"}, {"--log-failed", "--log", "--verbose", "-v", "--exit-status"})
    if len(rest) != 1 or not rest[0].isdigit():
        fail("this stand-in answers only `gh run view <run id> [--attempt N] --log-failed`")
    if not o.get("log-failed"):
        fail("this stand-in answers only --log-failed")
    run = int(rest[0])
    if os.environ.get("FAKE_GH_VIEW_EXIT"):
        fail("HTTP 502: Bad Gateway (https://api.github.com/repos/o/r/actions/runs/%d/logs)" % run,
             int(os.environ["FAKE_GH_VIEW_EXIT"]))
    have, _ = runs()
    found = next((norm(r) for r in (have or []) if r.get("databaseId") == run), None)
    if not found:
        fail(f"HTTP 404: Not Found (https://api.github.com/repos/o/r/actions/runs/{run})")
    latest = int(found["attempt"])
    attempt = int(o.get("attempt", latest))
    if attempt < 1 or attempt > latest:
        fail(f"HTTP 404: Not Found (https://api.github.com/repos/o/r/actions/runs/{run}/attempts/{attempt})")
    if attempt == latest and found.get("status") != "completed":
        fail(f"run {run} is still in progress; logs will be available when it is complete")
    logs = json.loads(os.environ.get("FAKE_GH_LOGS") or "{}")
    path = logs.get(f"{run}/{attempt}")
    if path:
        sys.stdout.write(open(path).read())


def main(argv: list[str]) -> None:
    if os.environ.get("FAKE_GH_CALLS"):
        with open(os.environ["FAKE_GH_CALLS"], "a") as fh:
            fh.write(" ".join(argv) + "\n")
    if os.environ.get("FAKE_GH_EXIT"):
        fail("error connecting to api.github.com", int(os.environ["FAKE_GH_EXIT"]))
    if argv[:2] == ["run", "list"]:
        return run_list(argv[2:])
    if argv[:2] == ["run", "view"]:
        return run_view(argv[2:])
    if argv[:2] in (["run", "rerun"], ["run", "cancel"], ["run", "delete"], ["workflow", "run"]):
        fail("the line never changes anything on GitHub: this stand-in refuses " + " ".join(argv[:2]))
    fail(f'unknown command "{" ".join(argv[:2])}" for gh')


if __name__ == "__main__":
    main(sys.argv[1:])
