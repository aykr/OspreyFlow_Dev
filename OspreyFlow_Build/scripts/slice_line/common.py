"""What the slice line's scripts share: where things live, the backlog file, the dial, the accounts.

Run with OspreyFlow_Core's venv python (PyYAML). The hooks (guard.py, stop_check.py, usage_hook.py) do not
import this: they run from the fixed place with the system python.
"""
from __future__ import annotations

import contextlib
import csv
import fcntl
import io
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BIN = Path.home() / ".ospreyflow" / "slice-line"
DATA = Path(os.environ.get("OSPREY_SLICE_HOME") or str(BIN))
RECORDS = DATA / "records"


def git(args: list[str], cwd: Path | str, check: bool = True) -> str:
    p = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {cwd}: {p.stderr.strip()}")
    return p.stdout.rstrip()


def main_checkout() -> Path:
    """The main checkout of the repository these scripts belong to (not a worktree)."""
    common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], HERE)
    return Path(common).parent


REPO = main_checkout()
V062_REL = "OspreyFlow_Build/process/lanes/v062"
SLICES_REL = f"{V062_REL}/slices.tsv"
DIAL_FILE = REPO / V062_REL / "dial.yaml"
ACCOUNTS_FILE = REPO / V062_REL / "accounts.yaml"
PLAN_HTML = REPO / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/index.html"
STATUS_FILE = Path(os.environ.get("OSPREY_STATUS_FILE") or REPO / "Claude outputs/ospreyflow_build_plan_2026-11-17/dashboard/status.js")
WT_ROOT = Path(os.environ.get("OSPREY_SLICE_WT_ROOT") or Path.home() / "dev" / "osprey-wt")

COLUMNS = ["id", "build", "what", "after", "track", "branch", "env", "acceptance_files", "acceptance", "checks"]
FROZEN_KEYS = ("acceptance_files", "acceptance", "checks")
NEAR_LIMIT = 0.95  # an account at or above this share of a window starts no new slice (README.md, "Accounts";
#                   the owner, 22 November 2026, his file 010: 95%, from 90%)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_slices(text: str) -> list[dict]:
    rows = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    out = []
    for r in csv.reader(io.StringIO("\n".join(rows)), delimiter="\t"):
        if r and r[0] == "id":
            continue
        r = r + [""] * (len(COLUMNS) - len(r))
        out.append({k: (v.strip() if v.strip() != "-" else "") for k, v in zip(COLUMNS, r)})
    return out


def load_slices(ref: str | None = "main") -> list[dict]:
    """The backlog file as committed on main (what the line acts on), or the working copy with ref=None."""
    if ref is None:
        return parse_slices((REPO / SLICES_REL).read_text())
    return parse_slices(git(["show", f"{ref}:{SLICES_REL}"], REPO))


def slice_row(slice_id: str, ref: str | None = "main") -> dict:
    for row in load_slices(ref):
        if row["id"] == slice_id:
            return row
    raise SystemExit(f"Slice {slice_id} is not in {SLICES_REL} on {ref or 'the working copy'}.")


def plan_ids() -> set[str]:
    """The build ids in the owner's plan page (index.html's N list): BL1, CO1, IS2 ..."""
    return set(re.findall(r'\[\s*"([A-Z]{2,4}\d+)"\s*,\s*\d+\s*,', PLAN_HTML.read_text()))


def load_dial() -> dict:
    return yaml.safe_load(DIAL_FILE.read_text())


def current_setting(dial: dict | None = None, at: datetime | None = None) -> str:
    dial = dial or load_dial()
    cur = str(dial.get("current", "auto")).lower()
    if cur in dial["settings"]:
        return cur
    start, end = dial.get("day_hours", [7, 22])
    hour = (at or datetime.now()).hour
    return dial.get("day", "balanced") if start <= hour < end else dial.get("night", "thrift")


def seat_settings(seat: str, setting: str | None = None) -> dict:
    dial = load_dial()
    s = setting or current_setting(dial)
    conf = dial["settings"][s]
    return {"setting": s, "builders": conf["builders"], "rounds": conf["rounds"], **conf["seats"][seat]}


def load_accounts() -> dict:
    return yaml.safe_load(ACCOUNTS_FILE.read_text())


def account_for(seat: str, track: str | None = None) -> str:
    acc = load_accounts()
    if seat == "builder":
        return acc["tracks"][str(track)]
    return acc["seats"][seat]


def config_dir(account: str) -> Path:
    """An account's Claude Code config folder, as the owner's shell defines it (claude-sol: ~/.claude-sol)."""
    if not re.fullmatch(r"[a-z][a-z0-9-]*", account):
        raise SystemExit(f"Not an account name: {account!r}")
    return Path.home() / (".claude" if account == "default" else f".claude-{account}")


def claude_env(account: str) -> dict:
    env = dict(os.environ)
    env.pop("CLAUDE_CONFIG_DIR", None)
    if account != "default":
        env["CLAUDE_CONFIG_DIR"] = str(config_dir(account))
    return env


CLAUDE = os.environ.get("OSPREY_CLAUDE_BIN") or str(Path.home() / ".local/bin/claude")


def signed_in(account: str) -> bool:
    p = subprocess.run([CLAUDE, "auth", "status"], env=claude_env(account), capture_output=True, text=True)
    try:
        return bool(json.loads(p.stdout).get("loggedIn"))
    except ValueError:
        return False


def account_state(account: str) -> dict:
    f = DATA / "accounts" / f"{account}.json"
    with file_lock(f"account-{account}", shared=True):
        return json.loads(f.read_text()) if f.exists() else {}


def account_stop(account: str) -> dict | None:
    f = DATA / "accounts" / f"{account}.stopped.json"
    return json.loads(f.read_text()) if f.exists() else None


def known_accounts() -> set[str]:
    """Every account name the owner's accounts.yaml gives a seat or a track."""
    acc = load_accounts() or {}
    return {str(v) for part in ("seats", "tracks") for v in (acc.get(part) or {}).values() if v}


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def running_seats(slice_id: str) -> list[dict]:
    """The seats of a slice whose run_seat.py is running now (its running-<seat>.json, for a process that is alive). A
    record left by a process that has ended holds nothing."""
    out = []
    for f in sorted(rec_dir(slice_id).glob("running-*.json")):
        r = read_json(f) or {}
        if isinstance(r.get("pid"), int) and pid_alive(r["pid"]):
            out.append(r)
    return out


def near_limit(account: str) -> str | None:
    st = account_state(account)
    for window, info in (st.get("windows") or {}).items():
        reset = info.get("resetsAt") or 0
        if (info.get("utilization") or 0) >= NEAR_LIMIT and reset > time.time():
            when = datetime.fromtimestamp(reset).strftime("%a %d %b %H:%M")
            return f"{account} is at {info['utilization']:.0%} of its {window.replace('_', '-')} limit (resets {when})"
    return None


def rec_dir(slice_id: str) -> Path:
    return RECORDS / slice_id


def read_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def write_json(p: Path, data: dict) -> None:
    """Written whole, then renamed into place, through a temporary name of this writer's own: two writers never share
    one (two seats of one account did, and renamed each other's half-written file: LINE_FIXES_5_BRIEF.md, 6)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{os.urandom(4).hex()}.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=1))
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)


@contextlib.contextmanager
def file_lock(name: str, shared: bool = False):
    """A lock in the data folder's locks/, held for a read (shared) or a read-and-write (exclusive); a second holder
    waits for it, never fails (6)."""
    d = DATA / "locks"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{name}.lock").open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield


def state(slice_id: str) -> dict:
    return read_json(rec_dir(slice_id) / "state.json") or {}


def set_state(slice_id: str, **kw) -> dict:
    st = state(slice_id)
    st.update(kw)
    st["updated"] = now()
    write_json(rec_dir(slice_id) / "state.json", st)
    return st


def frozen_matches(frozen: dict, row: dict) -> bool:
    return all((frozen.get(k) or "") == (row.get(k) or "") for k in FROZEN_KEYS)


#: A test-only part's planted fault (the owner, 24 November 2026, "cut my paperwork", item 2, with his answers): a
#: patch the conductor writes as a record, plants/<ID>.patch, committed on main. Its hash is frozen with the acceptance
#: when the part starts (frozen.json "plant"), so a change to it is a refreeze, the owner's word. The line applies it to
#: the base with the acceptance files (the merge's red before; the dry run): green without it, red with it on an
#: assertion. It never reaches the merge result.
PLANTS_REL = f"{V062_REL}/plants"


def plant_text(slice_id: str, ref: str = "main") -> str:
    """The part's planted fault as `ref` holds it, or '' when it has none."""
    p = subprocess.run(["git", "show", f"{ref}:{PLANTS_REL}/{slice_id}.patch"], cwd=REPO, capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def plant_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest() if text else ""


def plant_matches(slice_id: str, frozen: dict) -> bool:
    """Main's planted fault for the part is the one frozen (none, when none was)."""
    return (frozen.get("plant") or "") == plant_hash(plant_text(slice_id))


def refreeze(slice_id: str, by: str) -> dict:
    """Take the slice's frozen columns from main's backlog file, keeping the previous ones in the record's history."""
    f = rec_dir(slice_id) / "frozen.json"
    frozen = read_json(f) or {}
    if not frozen:
        raise SystemExit(f"{slice_id} has not started.")
    row = slice_row(slice_id)
    frozen.setdefault("history", []).append({k: frozen.get(k) for k in (*FROZEN_KEYS, "plant", "frozen_at")})
    frozen.update({k: row[k] for k in FROZEN_KEYS})
    frozen["plant"] = plant_hash(plant_text(slice_id))
    frozen["frozen_at"] = now()
    frozen["refrozen_by"] = by
    write_json(f, frozen)
    return frozen


#: The owner's rulings reach a slice's worktree, which is a snapshot from the slice's start, as a copy of main's
#: RULINGS.md, never as a commit on the slice's branch: a copy committed there conflicts with main the next time main's
#: rulings change (BL6, 18 November 2026). run_seat.py writes it before every builder and verifier session and names it
#: in the prompt. The copy lives in the worktree's own git folder (`git rev-parse --git-path`), which is no entry of the
#: tree: at the tree's root (`Claude outputs/slice-line/`, until 21 November 2026) it failed test_layout's "no product
#: folder is left at the root" in every builder's worktree (PL4d3c; LINE_FIXES_5_BRIEF.md, 5). A copy left at the old
#: place is removed when the new one is written.
RULINGS_REL = f"{V062_REL}/RULINGS.md"
RULINGS_COPY_REL = "slice-line/RULINGS.md"
OLD_RULINGS_COPY_REL = "Claude outputs/slice-line/RULINGS.md"


def rulings_copy(tree: Path) -> Path | None:
    """Where the rulings copy of `tree` goes: inside its own git folder, never among its files."""
    p = subprocess.run(["git", "-C", str(tree), "rev-parse", "--path-format=absolute", "--git-path", RULINGS_COPY_REL],
                       capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        return None
    dest = Path(p.stdout.strip())
    top = subprocess.run(["git", "-C", str(tree), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if top.returncode != 0 or str(dest).startswith(top.stdout.strip().rstrip("/") + "/") and ".git/" not in str(dest):
        return None  # never a path among the tree's own files
    return dest


def deliver_rulings(tree: Path) -> str | None:
    """Main's RULINGS.md, copied into `tree`'s own git folder; the copy's path, or None when it cannot be."""
    try:
        text = git(["show", f"main:{RULINGS_REL}"], REPO)
    except RuntimeError:
        return None
    dest = rulings_copy(tree)
    if dest is None:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text + "\n")
    old = Path(tree) / OLD_RULINGS_COPY_REL
    if old.is_file():  # the copy the line used to leave at the root (5): removed, with the folders it alone kept
        old.unlink()
        for d in (old.parent, old.parent.parent):
            try:
                d.rmdir()
            except OSError:
                break
    return str(dest)


#: The scout's table of every open case, before a slice's fifth round (the owner, 21 November 2026: after round 4 a
#: read-only scout lists every open case as a table, and rounds 5 to 8 are judged against it; no fifth round without
#: it): slices/<ID>_ROUND<N>_TABLE.md beside the slice's brief, N 5 or more, in the main checkout (committed or not).
TABLE_ROUND = 5


def round_table(slice_id: str) -> Path | None:
    """The slice's open-case table for rounds 5 on, or None when there is none."""
    folder = REPO / V062_REL / "slices"
    for f in sorted(folder.glob(f"{slice_id}_ROUND*_TABLE.md")) if folder.is_dir() else []:
        m = re.fullmatch(rf"{re.escape(slice_id)}_ROUND(\d+)_TABLE\.md", f.name)
        if m and int(m.group(1)) >= TABLE_ROUND and f.read_text().strip():
            return f
    return None


#: The owner's written word for resume.py (README, "Resuming a slice"): lines `<slice> <action> <YYYY-MM-DD>`, one use
#: each. Only the owner writes it (the guard's OWNER_ONLY); every use is logged in the data folder.
RESUME_FILE = REPO / V062_REL / "resume.tsv"
OWNER_CHANGES = DATA / "owner-changes.tsv"


#: The owner's standing accept (ACCEPT_STEP_BRIEF.md, "The standing mode"; RULINGS.md, 19 November 2026, ruling 5): one
#: line in standing.tsv, beside resume.tsv and like it the owner's alone (the guard's OWNER_ONLY), never committed.
STANDING_FILE = REPO / V062_REL / "standing.tsv"
STANDING_RULE = "accept-test-gaps"
#: The floor the owner's ruling names ("from a slice's third round on"): a line naming a lower round is not taken.
STANDING_FLOOR = 3


#: The owner's standing permissions (his file 012, 23 November 2026), each one more line in standing.tsv, each with a
#: daily budget: `<name> per-day <N> <YYYY-MM-DD>`, N from 1 to STANDING_BUDGET_MOST (his "ten a day"; more is a change
#: to this file, never a line). Each use is logged in owner-changes.tsv ("standing.tsv <name>: ...") and in
#: self-clears.tsv, which the board prints. round-after-refusal: one more round after a merge refusal past the rounds
#: limit, without the add-round line (resume.py send-back). clear-line-stops: a stop whose cause is the line's cleared
#: without the clear-stop line (resume.py self-clear).
STANDING_PERMISSIONS = ("round-after-refusal", "clear-line-stops")
STANDING_BUDGET_MOST = 10


def standing_lines() -> tuple[list[list[str]] | None, str]:
    """The owner's lines in standing.tsv, each split into its words, or None with why not: a line that names no rule or
    permission of the line's turns every one of them off (a misspelt line is never guessed at)."""
    try:
        text = STANDING_FILE.read_text()
    except OSError:
        return None, f"{STANDING_FILE.name} is not there (the standing accept and permissions are off)"
    lines = [ln.split() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    stray = [ln for ln in lines if ln[0] not in (STANDING_RULE, *STANDING_PERMISSIONS)]
    if stray:
        return None, (f"{STANDING_FILE.name} says {' '.join(stray[0])!r}, which names no standing rule or permission "
                      f"({', '.join((STANDING_RULE, *STANDING_PERMISSIONS))}): all of them are off until it is put right")
    return lines, "on"


def a_date(word: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", word):
        return False
    try:
        datetime.strptime(word, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def standing_permission(name: str) -> tuple[dict | None, str]:
    """The owner's standing permission `name` (one line `<name> per-day <N> <YYYY-MM-DD>`), or None with why not."""
    lines, why = standing_lines()
    if lines is None:
        return None, why
    mine = [ln for ln in lines if ln[0] == name]
    want = f"one line '{name} per-day <1 to {STANDING_BUDGET_MOST}> <YYYY-MM-DD>'"
    if len(mine) != 1:
        return None, f"{STANDING_FILE.name} holds {len(mine)} '{name}' lines, not {want} (the permission is off)"
    p = mine[0]
    if not (len(p) == 4 and p[1] == "per-day" and p[2].isdigit() and 1 <= int(p[2]) <= STANDING_BUDGET_MOST
            and a_date(p[3])):
        return None, f"{STANDING_FILE.name} says {' '.join(p)!r}, not {want} (the permission is off)"
    return {"name": name, "per_day": int(p[2]), "given": p[3], "line": " ".join(p)}, "on"


def standing_uses_today(name: str) -> int:
    """How many times the permission was used today (UTC), by its rows in owner-changes.tsv."""
    day = now()[:10]
    return sum(1 for r in owner_changes() if r["at"].startswith(day) and r["detail"].startswith(f"standing.tsv {name}:"))


def standing_grant(name: str) -> tuple[dict | None, str]:
    """The permission, when it is on and today's budget is not spent; None with why not."""
    rule, why = standing_permission(name)
    if not rule:
        return None, why
    used = standing_uses_today(name)
    if used >= rule["per_day"]:
        return None, (f"the standing permission {name} has given its {rule['per_day']} for today ({now()[:10]}, UTC): at "
                      "its budget the line gives no more today, and the owner's own line is needed")
    return {**rule, "used": used}, "on"


def standing_today() -> list[dict]:
    """Each standing permission today, for the board: on or off (and why), its uses and its budget."""
    out = []
    for name in STANDING_PERMISSIONS:
        rule, why = standing_permission(name)
        used = standing_uses_today(name)
        out.append({"name": name, "on": bool(rule), "why": why, "used": used, "per_day": (rule or {}).get("per_day", 0),
                    "at_budget": bool(rule) and used >= rule["per_day"]})
    return out


def log_standing_use(slice_id: str, name: str, action: str, stop: str, cause: str, what: str,
                     extra: dict | None = None) -> dict:
    """One use of a standing permission: its row in owner-changes.tsv (what the budget counts) and in self-clears.tsv
    (what the board prints, in one sentence: what the line did and why)."""
    log_owner_change(slice_id, action, f"standing.tsv {name}: {what}")
    return log_self_clear(slice_id, stop, cause, what, extra)


def standing_rule() -> tuple[dict | None, str]:
    """The owner's standing line, `accept-test-gaps from-round <N> <YYYY-MM-DD>` (N at least 3), or None with why
    not. Missing, unreadable, more than one such line, or anything else: no standing accept, never guessed."""
    lines, why = standing_lines()
    if lines is None:
        return None, why
    lines = [ln for ln in lines if ln[0] == STANDING_RULE]
    want = f"one line '{STANDING_RULE} from-round <{STANDING_FLOOR} or more> <YYYY-MM-DD>'"
    if len(lines) != 1:
        return None, f"{STANDING_FILE.name} holds {len(lines)} lines, not {want}"
    parts = lines[0]
    ok = (len(parts) == 4 and parts[0] == STANDING_RULE and parts[1] == "from-round" and parts[2].isdigit()
          and int(parts[2]) >= STANDING_FLOOR and re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[3]))
    if ok:
        try:
            datetime.strptime(parts[3], "%Y-%m-%d")
        except ValueError:
            ok = False
    if not ok:
        return None, f"{STANDING_FILE.name} says {' '.join(parts)!r}, not {want}"
    return {"from_round": int(parts[2]), "given": parts[3], "line": " ".join(parts)}, "on"


def log_owner_change(slice_id: str, action: str, detail: str) -> None:
    OWNER_CHANGES.parent.mkdir(parents=True, exist_ok=True)
    if not OWNER_CHANGES.exists():
        OWNER_CHANGES.write_text("at\tslice\taction\tdetail\n")
    with OWNER_CHANGES.open("a") as fh:
        fh.write("\t".join([now(), slice_id, action, detail.replace("\t", " ").replace("\n", " ")]) + "\n")


#: The line's own clearances of a stop (LINE_FIXES_5_BRIEF.md, A): one row each (time, slice, the stop, the cause a or
#: b, what the line did), beside owner-changes.tsv; board.py prints them for the conductor's morning report and
#: status.js carries them (`self_clears`). Each also has its record in the slice's folder (self-clear-<time>.json).
SELF_CLEARS = DATA / "self-clears.tsv"
SELF_CLEAR_COLUMNS = ("at", "slice", "stop", "cause", "what")


def log_self_clear(slice_id: str, stop: str, cause: str, what: str, extra: dict | None = None) -> dict:
    row = {"at": now(), "slice": slice_id, "stop": stop, "cause": cause, "what": what}
    SELF_CLEARS.parent.mkdir(parents=True, exist_ok=True)
    if not SELF_CLEARS.exists():
        SELF_CLEARS.write_text("\t".join(SELF_CLEAR_COLUMNS) + "\n")
    with SELF_CLEARS.open("a") as fh:
        fh.write("\t".join(str(row[k]).replace("\t", " ").replace("\n", " ") for k in SELF_CLEAR_COLUMNS) + "\n")
    write_json(rec_dir(slice_id) / f"self-clear-{row['at'].replace(':', '')}-{os.urandom(3).hex()}.json", {**row, **(extra or {})})
    return row


def self_clears() -> list[dict]:
    if not SELF_CLEARS.exists():
        return []
    rows = [ln.split("\t") for ln in SELF_CLEARS.read_text().splitlines()[1:] if ln.strip()]
    return [dict(zip(SELF_CLEAR_COLUMNS, r + [""] * (len(SELF_CLEAR_COLUMNS) - len(r)))) for r in rows]


#: The owner's park line in resume.tsv, `<slice> park <YYYY-MM-DD>` (his file 012): a parked slice is his, and no standing
#: permission acts on it. It is never used up; he lifts it by deleting the line.
PARK = "park"


def parked(slice_id: str) -> str:
    """The owner's park line for the slice (of any day), or ''."""
    if not RESUME_FILE.is_file():
        return ""
    for ln in RESUME_FILE.read_text().splitlines():
        parts = ln.split()
        if not ln.strip().startswith("#") and len(parts) == 3 and parts[:2] == [slice_id, PARK]:
            return "\t".join(parts)
    return ""


def unapplied_lines() -> list[dict]:
    """The owner's lines in resume.tsv for a slice not yet used (no use logged in owner-changes.tsv): each its slice,
    action, arguments (move-seat's seat and account), date and text. The k-th of k identical lines is unapplied until it
    has k uses. Lines that are not a slice's (clear-account) are left out."""
    if not RESUME_FILE.is_file():
        return []
    lines = [ln.split() for ln in RESUME_FILE.read_text().splitlines() if ln.strip() and not ln.strip().startswith("#")]
    changes = owner_changes()
    out, seen = [], {}
    for parts in lines:
        if len(parts) < 3 or parts[0] == "clear-account" or parts[1] == PARK:
            continue
        sid, action, args, date = parts[0], parts[1], parts[2:-1], parts[-1]
        key = tuple(parts)
        seen[key] = seen.get(key, 0) + 1
        tag = f"resume.tsv {date} {' '.join([action, *args])}:"
        used = sum(1 for r in changes if r["slice"] == sid and r["detail"].startswith(tag))
        if used < seen[key]:
            out.append({"slice": sid, "action": action, "args": args, "date": date, "text": "\t".join(parts)})
    return out


def owner_changes() -> list[dict]:
    if not OWNER_CHANGES.exists():
        return []
    rows = [ln.split("\t") for ln in OWNER_CHANGES.read_text().splitlines()[1:] if ln.strip()]
    return [dict(zip(("at", "slice", "action", "detail"), r + [""] * (4 - len(r)))) for r in rows]


#: A slice's Playwright port slot (F8): its own, from SLOT_FIRST up, clear of every lane's in scripts/lane_ports.tsv, of
#: every unmerged slice's (its recorded slot, or one its frozen commands export), and with every port it moves
#: (OspreyFlow_Core/apps' lanePort(<base>) + 100 x slot) clear of the test stacks' ports (scripts/lane_stacks.tsv), the
#: owner's deployment's and every other slot's: the rules tests/test_lane_ports.py holds the lanes' table to.
SLOT_FIRST = 16
SLOT_STEP = 100
OWNER_PORTS = {2480, 5432, 80, 8000, 8080, 8081, 5173}


def _tsv_rows(path: Path) -> list[list[str]]:
    if not path.is_file():
        return []
    return [ln.split("\t") for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]


def taken_slots(but: str = "") -> set[int]:
    taken = {int(r[1]) for r in _tsv_rows(REPO / "OspreyFlow_Build/scripts/lane_ports.tsv")
             if len(r) >= 2 and r[1].strip().isdigit()}
    if RECORDS.exists():
        for d in RECORDS.iterdir():
            if d.name == but or (d / "merged.json").exists():
                continue
            st = read_json(d / "state.json") or {}
            if isinstance(st.get("slot"), int):
                taken.add(st["slot"])
            fz = read_json(d / "frozen.json") or {}
            for k in FROZEN_KEYS:
                taken |= {int(n) for n in re.findall(r"OSPREY_PORTS_SLOT=(\d+)", fz.get(k) or "")}
    return taken


def allocate_slot(slice_id: str) -> int:
    bases: set[int] = set()
    apps = REPO / "OspreyFlow_Core/apps"
    if apps.is_dir():
        for p in apps.rglob("*.ts"):
            if "node_modules" not in p.parts:
                bases |= {int(n) for n in re.findall(r"lanePort\((\d+)\)", p.read_text(errors="replace"))}
    stacks = {int(r[3]) for r in _tsv_rows(REPO / "OspreyFlow_Build/scripts/lane_stacks.tsv")
              if len(r) >= 4 and r[3].strip().isdigit()}
    taken = taken_slots(but=slice_id)
    spoken = stacks | OWNER_PORTS | {b + SLOT_STEP * s for s in taken | {0} for b in bases}
    for slot in range(SLOT_FIRST, 600):
        ports = {b + SLOT_STEP * slot for b in bases}
        if slot not in taken and all(p < 65536 for p in ports) and not ports & spoken:
            return slot
    raise SystemExit("No Playwright port slot is free for a new slice: the owner frees one (a merged or removed slice).")


#: main's GitHub run (F2): the latest completed run on main, read with gh. Never taken as green unless it says success;
#: recorded at each merge, never a reason to refuse one (LINE_FIXES_4_BRIEF.md, 1a).
GH_FIELDS = "databaseId,conclusion,status,url"


def _gh_runs(*args: str) -> list[dict]:
    p = subprocess.run(["gh", "run", "list", "--branch", "main", *args, "--limit", "1", "--json", GH_FIELDS],
                       cwd=str(REPO), capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise ValueError(f"gh exit {p.returncode}: {(p.stderr or p.stdout).strip()[:200]}")
    runs = json.loads(p.stdout)
    if not isinstance(runs, list):
        raise ValueError("gh's answer is not a list of runs")
    return runs


#: A test of ours failing twice on GitHub (1c): the stop that holds every merge until the owner clears it
#: (clear_github_stop.py), each run's failing tests as watch-github read them, and the owner's clears, for audit
#: (owner-changes.tsv's sibling). All in the data folder, which the guard keeps every agent from writing.
GITHUB_STOP = DATA / "github.stopped.json"
GITHUB_RECORDS = RECORDS / "github"
GITHUB_CLEARS = DATA / "github-stop-clears.tsv"


def github_stop_words(stop: dict | None) -> str:
    """The stop, in the words a refused merge and the board give: the test, the job, the commit, both runs."""
    if not stop:
        return (f"{GITHUB_STOP} is there but cannot be read: merging stays stopped until the owner looks at it and "
                "clears it (clear_github_stop.py).")
    runs = " and ".join(f"run {r.get('run')} attempt {r.get('attempt')}" for r in stop.get("runs", []))
    more = f" (and {len(stop['tests']) - 1} more)" if len(stop.get("tests") or []) > 1 else ""
    return (f"a test of ours failed twice on GitHub on one commit: {stop.get('test')}{more}, in job {stop.get('job')}, "
            f"at commit {str(stop.get('commit'))[:10]} ({runs}). Merging is stopped until the owner clears it "
            "(clear_github_stop.py) once it is dealt with.")


def main_runs_going() -> str:
    """'in progress' or 'queued' when a run on main is, as the push script asks gh (`gh run list --branch main --status
    in_progress|queued --json databaseId`); '' when none is. gh that cannot be read is no run going, as for the push
    script: a push is held back only by a run a new push would cancel."""
    for status, said in (("in_progress", "in progress"), ("queued", "queued")):
        try:
            p = subprocess.run(["gh", "run", "list", "--branch", "main", "--status", status, "--json", "databaseId"],
                               cwd=str(REPO), capture_output=True, text=True, timeout=60)
            if p.returncode == 0 and json.loads(p.stdout):
                return said
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return ""


def main_ci() -> dict:
    """{state: green | red | unknown, run, url, why}: red for a failed run, or a cancelled one with nothing newer;
    unknown when gh cannot be read or no run has completed (never taken as green). A record and a note on the board,
    never a merge's gate (the owner, 20 November 2026)."""
    try:
        done = _gh_runs("--status", "completed")
        if not done:
            return {"state": "unknown", "run": None, "url": "", "why": "no run on main has completed"}
        last = done[0]
        run, url, concl = last.get("databaseId"), last.get("url", ""), last.get("conclusion")
        if concl == "success":
            return {"state": "green", "run": run, "url": url, "why": "success"}
        if concl == "cancelled":
            newest = _gh_runs()
            if newest and newest[0].get("databaseId") != run:
                return {"state": "green", "run": run, "url": url,
                        "why": f"cancelled, with a newer run {newest[0].get('databaseId')} ({newest[0].get('status')})"}
            return {"state": "red", "run": run, "url": url, "why": "cancelled, with nothing newer"}
        return {"state": "red", "run": run, "url": url, "why": str(concl)}
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return {"state": "unknown", "run": None, "url": "", "why": f"gh could not be read ({e})"}
