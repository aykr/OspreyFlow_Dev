"""Rule 15's red-then-green record for the slice line: one planted fault per gate, each shown turning its test red.

Usage: plant_faults.py <scratch dir> <a checkout of this branch> <a python with pytest and PyYAML>
The scratch dir must hold OspreyFlow_Build/process/lanes/v062 (dial.yaml, accounts.yaml). Expected: 0 not caught.
"""
import shutil, subprocess, sys
from pathlib import Path
S = Path(sys.argv[1]); W = Path(sys.argv[2]); PY = sys.argv[3]
M = [
 ("guard.py", 'if re.search(r"\\bgit\\b[^;&|\\n]*\\bpush\\b", cmd)', 'if False', "push_new_remotes"),
 ("guard.py", 'PROTECTED = ("OspreyFlow_Core/Makefile", ".github/workflows/ci.yml")', 'PROTECTED = ()', "core_makefile"),
 ("guard.py", 'if wide and risky:', 'if False:', "staging_osprey"),
 ("guard.py", 'if not wt or not (under(full, wt) or is_temp(full)):', 'if False:', "builder_cannot_edit"),
 ("guard.py", '        if writes_main:\n', '        if False:\n', "nothing_writes_main"),
 ("guard.py", 'def scan_secrets(text: str) -> Optional[str]:\n', 'def scan_secrets(text: str) -> Optional[str]:\n    return None\n', "credential_or_the_owners"),
 ("guard.py", '    for pat, what in DEMO_PATTERNS:\n        if re.search(pat, cmd):', '    for pat, what in ():\n        if re.search(pat, cmd):', "govuk_demo"),
 ("guard.py", 'if re.search(r"\\bOSPREY_(SLICE', 'if False and re.search(r"\\bOSPREY_(SLICE', "line_its_records"),
 ("guard.py", '    if seat in ("verifier", "scout"):\n        check_readonly_bash(raw)', '    pass', "read_only_seats"),
 ("guard.py", '    except Exception as e:  # fail closed\n        if mode == "pre":', '    except Exception as e:  # fail closed\n        if False:', "fails_closed"),
 ("stop_check.py", '    if not problems:\n', '    if True:\n', "red_builder_cannot_stop"),
 ("stop_check.py", 'if reds >= MAX_RED:', 'if False:', "red_six_times"),
 ("merge_slice.py", '    rec = c.read_json(c.rec_dir(slice_id) / f"verify-{tip}.json")\n    if not rec:\n        raise', '    rec = c.read_json(c.rec_dir(slice_id) / f"verify-{tip}.json")\n    return rec or {}\n    if not rec:\n        raise', "no_verifier_record"),
 ("merge_slice.py", 'if not tp.is_file() or tip not in tp.read_text(errors="ignore"):', 'if False:', "never_saw_the_commit"),
 ("merge_slice.py", 'if run(frozen["acceptance"], before, log, shell=True) == 0:', 'if False:', "never_red"),
 ("merge_slice.py", 'if frozen.get(name) and run(frozen[name], after, log, shell=True) != 0:', 'if False:', "refuses_a_red_branch"),
 ("merge_slice.py", 'if FULL_GATE(after, base, log) != 0:', 'if False:', "full_gate_is_red"),
 ("merge_slice.py", '        if bad:\n', '        if False:\n', "protected_path"),
 ("merge_slice.py", 'if not c.frozen_matches(frozen, row):', 'if False:', "changed_frozen_command"),
 ("merge_slice.py", 'fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)', 'pass', "one_merge_at_a_time"),
 ("merge_slice.py", 'if not rel.startswith(c.V062_REL + "/") or ".." in rel:', 'if False:', "records_mode"),
 ("push_main.sh", "if ! printf '%s' \"$trailers\" | grep -qE '^(Slice-Merge|Slice-Records):'; then", "if false; then", "push_script_refuses"),
 ("board.py", '        if not (verify and verify.get("verdict") == "pass" and verify.get("commit") == merged.get("tip")):', '        if False:', "refuses_done_without"),
 ("board.py", '    if state == "done":\n', '    if False:\n', "forged_done"),
 ("slice_start.py", 'if row["build"] not in c.plan_ids():', 'if False:', "not_in_the_plan"),
 ("slice_start.py", '        near = c.near_limit(acct)\n', '        near = None\n', "near_its_limit"),
 ("slice_start.py", '        if not c.signed_in(acct):', '        if False:', "signed_out"),
 ("run_seat.py", 'if not p.is_file() or sha(p) != manifest.get(h):', 'if False:', "seat_refuses_to_start"),
]
bad = 0
for f, old, new, test in M:
    d = S / "OspreyFlow_Build/scripts/slice_line"
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(W / "OspreyFlow_Build/scripts/slice_line", d, ignore=shutil.ignore_patterns("__pycache__"))
    t = (d / f).read_text()
    if old not in t:
        print("NOT FOUND", f, test); bad += 1; continue
    (d / f).write_text(t.replace(old, new, 1))
    p = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-c", str(d / "tests/pytest.ini"), str(d / "tests"), "-k", test],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"})
    red = p.returncode != 0 and "failed" in p.stdout and "no tests ran" not in p.stdout
    print(("RED  " if red else "STILL GREEN ") + f"{f:16} -> {test}")
    bad += 0 if red else 1
print("planted faults not caught:", bad)
