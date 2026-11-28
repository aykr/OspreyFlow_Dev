"""WS4a round 1: `WS4a_diffs/COMPARE_CI_REFERENCES.diff`'s run steps, taken from the diff's own text and run on the
builder's Mac with CI=true, then the committed references restored byte for byte. Nothing in CI was run.

    OSPREY_PORTS_SLOT=<slot> OspreyFlow_Core/.venv/bin/python <this file>   (from the repository root)

Left out: the first step's `git config user.name` line (it would write the repository's shared config) and the
upload step (an action, not a script). The set it makes is this Mac's, and is thrown away: its figures say that the
steps work, not what GitHub's runner draws.
"""
import hashlib, os, pathlib, re, subprocess, yaml
root = pathlib.Path.cwd()
refs = root / "OspreyFlow_Core/apps/workspace/keyboard/canvas-compare"
saved = {p.name: p.read_bytes() for p in refs.iterdir() if p.is_file()}
digest = lambda d: hashlib.sha256(b"".join(n.encode() + d[n] for n in sorted(d))).hexdigest()
lines = (root / "OspreyFlow_Build/process/lanes/v062/away/WS4a_diffs/COMPARE_CI_REFERENCES.diff").read_text().splitlines()
steps = yaml.safe_load("steps:\n" + "\n".join(l[1:] for l in lines if l.startswith("+") and not l.startswith("+++")) + "\n")["steps"]
env = {**os.environ, "CI": "true", "GITHUB_SHA": "rehearsal", "GITHUB_RUN_ID": "none"}
def bash(script):
    return subprocess.run(["bash", "-e", "-c", script], cwd=root / "OspreyFlow_Core", env=env, capture_output=True, text=True)
KEEP = re.compile(r"refused|made \d+ references|self-comparison|canvas-compare [a-z-]+:|\d+ (passed|failed)")
def show(label, p):
    out = [l.strip() for l in (p.stdout + p.stderr).splitlines() if KEEP.search(l)]
    print(f"--- {label}: exit {p.returncode}")
    print("\n".join(out))
try:
    show("without env -u: the command under CI=true", bash('npm run canvas-compare:references --workspace apps/workspace -- --reason "rehearsal"'))
    # The step's first line sets git's user name on the runner; here the name is already set, and the line would write
    # the repository's shared config, so it alone is left out.
    make = "\n".join(l for l in steps[0]["run"].splitlines() if not l.startswith("git config"))
    made = bash(make)
    show("step 1 as the diff writes it (but the git config line)", made)
    if made.returncode == 0:
        import json
        record = json.loads((refs / "REFERENCES.json").read_text())
        print("record: webgl:", record["machine"]["webgl"], "| scenes:", len(record["scenes"]), "| reason:", record["reason"])
        same = [n for n in saved if n.endswith(".png") and (refs / n).read_bytes() == saved[n]]
        print("byte-identical to the server's committed pictures:", len(same), same)
        show("step 3 as the diff writes it", bash(steps[2]["run"]))
finally:
    for p in refs.iterdir():
        if p.is_file() and p.name not in saved:
            p.unlink()
    for name, data in saved.items():
        (refs / name).write_bytes(data)
    now = {p.name: p.read_bytes() for p in refs.iterdir() if p.is_file()}
    print("restored byte for byte:", digest(now) == digest(saved))
