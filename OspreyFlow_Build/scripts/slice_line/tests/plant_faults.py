"""Rule 15's red-then-green record for the slice line: one planted fault per gate, each shown turning its test red.

Usage: plant_faults.py <scratch dir> <a checkout of this branch> <a python with pytest and PyYAML> [<only tests naming this>]
The scratch dir must hold OspreyFlow_Build/process/lanes/v062 (dial.yaml, accounts.yaml, live_step.yaml). Expected: 0 not caught.
"""
import shutil, subprocess, sys
from pathlib import Path
S = Path(sys.argv[1]); W = Path(sys.argv[2]); PY = sys.argv[3]; ONLY = sys.argv[4] if len(sys.argv) > 4 else ""
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
 ("merge_slice.py", 'if run(frozen["acceptance"], before, log, shell=True, env=env_before) == 0:', 'if False:', "never_red"),
 ("merge_slice.py", 'if frozen.get(name) and run(frozen[name], after, log, shell=True, env=env_after) != 0:', 'if False:', "refuses_a_red_branch"),
 ("merge_slice.py", 'if FULL_GATE(after, base, log) != 0:', 'if False:', "full_gate_is_red"),
 ("merge_slice.py", '        if bad:\n', '        if False:\n', "protected_path"),
 ("merge_slice.py", 'FULL_GATE_TARGETS = (("make", "-k", "ci"), ("make", "test"))', 'FULL_GATE_TARGETS = (("make", "-k", "ci"),)', "runs_make_ci_and_make_test"),
 ("merge_slice.py", '    if any(codes):\n', '    if codes[0]:\n', "only_one_of_make_ci_and_make_test_is_red"),
 ("merge_slice.py", 'sel = subprocess.run([str(tree / "OspreyFlow_Core/.venv/bin/python")', 'sel = subprocess.run([str(c.REPO / "OspreyFlow_Core/.venv/bin/python")', "never_the_main_checkouts"),
 ("merge_slice.py", 'env = {k: v for k, v in os.environ.items() if k not in SCRUBBED and not k.startswith("npm_config_")}', 'env = dict(os.environ)', "never_the_main_checkouts"),
 ("merge_slice.py", ' and not p.rstrip("/").endswith("/.venv/bin")]', ']', "never_the_main_checkouts"),
 ("merge_slice.py", 'for cmd in ([uv, "sync", "--frozen"], [str(nd / "npm")', 'for cmd in ([str(nd / "npm")', "never_the_main_checkouts"),
 ("merge_slice.py", 'if v.startswith(f"v{major}."):', 'if True:', "node_other_than_cis"),
 ("merge_slice.py", ', OSPREY_PORTS_SLOT=lane_slot(tree, GATE_LANE), UV_PYTHON=py)', ', OSPREY_PORTS_SLOT=lane_slot(tree, GATE_LANE))', "never_the_main_checkouts"),
 ("merge_slice.py", 'if not (said.stdout + said.stderr).strip().startswith(f"Python {py}."):', 'if False:', "another_python_than_cis"),
 ("merge_slice.py", 'if (core / ".venv").exists() or (core / "node_modules").exists():', 'if False:', "already_has_an_environment"),
 ("merge_slice.py", 'if not c.frozen_matches(frozen, row):', 'if False:', "changed_frozen_command"),
 ("merge_slice.py", 'fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)', 'pass', "one_merge_at_a_time"),
 ("merge_slice.py", 'if not rel.startswith(c.V062_REL + "/") or ".." in rel:', 'if False:', "records_mode"),
 ("push_main.sh", "if ! printf '%s' \"$trailers\" | grep -qE '^(Slice-Merge|Slice-Records):'; then", "if false; then", "push_script_refuses"),
 ("board.py", '        if not (verify and verify.get("verdict") == "pass" and verify.get("commit") == merged.get("tip")):', '        if False:', "refuses_done_without"),
 ("board.py", '    if state == "done":\n', '    if False:\n', "forged_done"),
 ("board.py", '    if not isinstance(data, dict):\n', '    if False:\n', "bad_or_incomplete_record"),
 ("board.py", "test run {merged.get('acceptance_run', '')}", "test run {merged['acceptance_run']}", "bad_or_incomplete_record"),
 ("board.py", '        except Exception as e:  # noqa: BLE001 -- anything else', '        except ZeroDivisionError as e:  # noqa: BLE001 -- anything else', "bad_or_incomplete_record"),
 ("board.py", '        problems.append(f"{sid}: record {path.name} is unreadable ({e}); skipped")\n', '        pass\n', "bad_or_incomplete_record"),
 ("board.py", '    if state == "done":\n        pass  # the merge record', '    if state == "done" or merged:\n        pass  # the merge record', "bad_or_incomplete_record"),
 ("slice_start.py", 'if row["build"] not in c.plan_ids():', 'if False:', "not_in_the_plan"),
 ("slice_start.py", '        near = c.near_limit(acct)\n', '        near = None\n', "near_its_limit"),
 ("slice_start.py", '        if not c.signed_in(acct):', '        if False:', "signed_out"),
 ("run_seat.py", 'if not p.is_file() or sha(p) != manifest.get(h):', 'if False:', "seat_refuses_to_start"),
 ("merge_slice.py", '"--base", base,\n                          "--reached"],', '"--base", base],', "reaches_no_live_file"),
 ("merge_slice.py", '    if not on:\n', '    if False:\n', "live_step_off_runs_nothing"),
 ("merge_slice.py", 'done["live_step"] = live', 'pass', "live_step_off_records"),
 ("merge_slice.py", 'if first not in ("", GATE_LANE):', 'if False:', "queue_does_not_clear"),
 ("merge_slice.py", 'if makes.strip():', 'if False:', "queue_does_not_clear"),
 ("merge_slice.py", 'if p.returncode != 0 or "<<end>>" not in p.stdout:', 'if False:', "queue_does_not_clear"),
 ("merge_slice.py", 'blocked = wait_for_queue(tree, wait, log)', 'blocked = None', "queue_does_not_clear"),
 ("merge_slice.py", '        time.sleep(QUEUE_POLL_SECONDS)', '        return None', "waits_for_the_queue"),
 ("merge_slice.py", '    if not isinstance(on, bool) or not isinstance(wait, int) or isinstance(wait, bool) or wait < 0:', '    if False:', "unclear_live_step_setting"),
 ("merge_slice.py", 'except (OSError, yaml.YAMLError) as e:', 'except ZeroDivisionError as e:', "unclear_live_step_setting"),
 ("merge_slice.py", ', f"{c.V062_REL}/live_step.yaml")', ')', "protected_path"),
 ("guard.py", ',\n              "OspreyFlow_Build/process/lanes/v062/live_step.yaml")', ')', "owner_files"),
 ("owed.py", '        if owed:\n            print(f"Refused: {len(owed)}', '        if False:\n            print(f"Refused: {len(owed)}', "is_owed_and_a_release_check"),
 ("owed.py", '        if problems:\n            print("Refused: the slice', '        if False:\n            print("Refused: the slice', "unreadable_merge_record_refuses"),
 ("owed.py", 'str(paid[t].get("at", "")) > o["at"]', 'True', "owed_again_after_it_was_paid"),
 ("owed.py", '            problems.append(str(e))\n    paid', '            pass\n    paid', "unreadable_merge_record_refuses"),
 ("board.py", '    owed = owed_list(problems)\n', '    owed = []\n', "board_shows_what_is_owed"),
 ("merge_slice.py", '*(["--", *(f"../OspreyFlow_Build/{t}" for t in owed_paths)] if owed_paths else [])', '', "runs_what_is_owed"),
 ("merge_slice.py", '    if code == 0 and (owed_paths or reached):', '    if owed_paths or reached:', "runs_what_is_owed"),
 ("merge_slice.py", '    if not reached and not owed_paths:', '    if not reached:', "runs_what_is_owed"),
 ("merge_slice.py", '        bring_client_hashes(tree)\n', '', "hashed_list"),
 ("merge_slice.py", 'if not src.is_file() or not src.read_text().strip():', 'if not src.is_file():', "hashed_list_is_missing"),
 ("merge_slice.py", '"check-ignore", "-q", CLIENT_HASHES_REL]).returncode != 0:', '"check-ignore", "-q", CLIENT_HASHES_REL]).returncode == 99:', "where_git_would_take_it"),
 ("tests/run.sh", 'elif [ -x "$TOP/OspreyFlow_Core/.venv/bin/python" ]; then', 'elif false; then', "own_checkouts_venv"),
 (".claude/agents/slice-verifier.md", 'tools: Read, Grep, Glob, Bash, StructuredOutput\n', 'tools: Read, Grep, Glob, Bash\n', "offered_structured_output"),
 ("resume.py", '    if not have:\n', '    if False:\n', "refuses_without_the_owners_line"),
 ("resume.py", '    if used >= have:\n', '    if False:\n', "line_is_used_once"),
 ("guard.py", ', "OspreyFlow_Build/process/lanes/v062/resume.tsv")', ')', "resume_tsv_is_refused"),
 ("resume.py", 'if phase != "stopped" or (rec / "red_stop.json").exists() or rnd < limit:', 'if False:', "add_round_refuses_a_slice_not_stopped"),
 ("resume.py", '    beyond = [k for k in c.COLUMNS if k not in allowed and old[k] != new[k]]', '    beyond = []', "beyond_that_slices_frozen"),
 ("resume.py", '    if dirty:\n        raise Refused(f"the worktree', '    if False:\n        raise Refused(f"the worktree', "refuses_while_a_merge_runs"),
 ("resume.py", '    fh = ms.lock()\n', '    fh = open("/dev/null")\n', "refuses_while_a_merge_runs"),
 ("resume.py", '    files = conflicts_with_main(wt)\n', '    files = []\n', "merges_main_into_a_branch"),
 ("resume.py", '        why = dry_run.malformed(problem)\n        if not why or dry_run.genuine(problem) or not problem.startswith(("RED: checks", "RED: acceptance")):', '        why = "any"\n        if False:', "genuine_failing_assertion"),
 ("resume.py", '        if a != b:\n', '        if False:\n', "changes_what_is_tested"),
 ("resume.py", '            if (new.get(k) or "").count(marker) > (old.get(k) or "").count(marker):', '            if False:', "changes_what_is_tested and dash"),
 ("resume.py", '            if problems:\n', '            if False:\n', "not_proved_on_main"),
 ("dry_run.py", '            if code != 0:\n', '            if False:\n', "not_proved_on_main"),
 ("resume.py", '    copy = c.deliver_rulings(wt)\n', '    copy = None\n', "brings_the_rulings"),
 ("merge_slice.py", '            refuse_to_builder(slice_id, tip, "today\'s full gate was red on the merge result", findings, len(names), "gate")\n', '', "red_full_gate_records"),
 ("merge_slice.py", '                    why.append(ln.strip())\n', '                    pass\n', "red_full_gate_records"),
 ("board.py", '    elif st.get("phase") == "refused":', '    elif False:', "red_full_gate_records"),
 ("resume.py", '            if rnd < limit:\n', '            if True:\n', "past_the_rounds_limit"),
 ("merge_slice.py", '    return files if files and all(f.startswith(c.V062_REL + "/") for f in files) else []', '    return []', "records_only_conflict"),
 ("resume.py", '            if st.get("refused_for") == "records":', '            if False:', "records_only_conflict"),
 ("run_seat.py", '        if v.get("verdict") != "pass":\n            return', '        if False:\n            return', "builders_prompt_carries"),
 ("scan_select.py", '    return sorted({t for t, prefixes, _ in table if any(p.startswith(prefixes) for p in touched)} if touched else set())', '    return []', "stop_hook_runs_the_scan_mapped"),
 ("stop_check.py", '    if scans:\n', '    if False:\n', "stop_hook_runs_the_scan_mapped"),
 ("stop_check.py", '        problems.append("RED: the line\'s scan map could not be read', '        (lambda *a: None)("RED: the line\'s scan map could not be read', "scan_map_cannot_be_read"),
 ("scan_select.py", '    hit = bool(WALK.search(text))\n', '    hit = False\n', "pure_test_that_walks"),
 ("scan_select.py", '            if f.is_file() and walks(build, f, seen, depth + 1):', '            if False:', "pure_test_that_walks"),
 ("scan_select.py", '            if not (root / p).exists():', '            if False:', "finds_a_stale_row"),
 ("slice_start.py", '    if problems:\n        raise SystemExit(f"NOT STARTED', '    if False:\n        raise SystemExit(f"NOT STARTED', "slice_start_refuses"),
 ("dry_run.py", '            if code == 0:\n                problems.append("the acceptance command passes on main', '            if False:\n                problems.append("the acceptance command passes on main', "acceptance_that_is_never_red"),
 ("dry_run.py", '            elif malformed(out):\n', '            elif False:\n', "red_only_for_a_malformed"),
 ("dry_run.py", '        out.append(cmd[last:p] + f\'&& {{ echo {n} >> "{marks}"; }} &&\')', '        out.append(cmd[last:p] + "&&")', "which_step_of_the_chain"),
 ("dry_run.py", '                if body is not None:\n', '                if False:\n', "stands_in_the_slices_own"),
 ("common.py", '        if slot not in taken and all(p < 65536 for p in ports) and not ports & spoken:', '        if True:', "slot_clear_of_the_lanes"),
 ("stop_check.py", '        env["OSPREY_PORTS_SLOT"] = str(slot)  # the slice', '        pass  # the slice', "give_a_playwright_command"),
 ("slice_start.py", '    problems = dry_run.prove(row, slot=slot, log=log)', '    problems = dry_run.prove(row, slot=None, log=log)', "give_a_playwright_command"),
 ("merge_slice.py", '    if slot not in (None, ""):\n        env["OSPREY_PORTS_SLOT"] = str(slot)', '    if False:\n        env["OSPREY_PORTS_SLOT"] = str(slot)', "ci_built_environment"),
 ("merge_slice.py", '        drop_env(after)  # the full gate builds its own, fresh\n', '', "ci_built_environment"),
 ("merge_slice.py", '        if venv:\n            env["UV_PROJECT_ENVIRONMENT"] = str(venv)', '        if False:\n            env["UV_PROJECT_ENVIRONMENT"] = str(venv)', "ci_built_environment"),
 ("slice_start.py", '    if row["env"] == "full":', '    if False:', "env_full_builds"),
 ("merge_slice.py", '        if scans and run(scan_select.command(', '        if False and run(scan_select.command(', "scans_of_the_touched_files"),
 ("slice_start.py", '    hashes = bring_client_hashes(wt)\n', '    hashes = "The hashed client-name list was copied"\n', "hashed_list_into_the_worktree"),
 ("slice_start.py", '    if subprocess.run(["git", "-C", str(wt), "check-ignore", "-q", ms.CLIENT_HASHES_REL]).returncode != 0:', '    if False:', "where_git_would_take_it"),
 ("slice_start.py", '    if not src.is_file() or not src.read_text().strip():\n        return (f"The main', '    if False:\n        return (f"The main', "no_hashed_list"),
 ("usage_hook.py", '        conductor_row(Path(event.get("transcript_path") or ""), event.get("session_id", ""), account)', '        pass', "session_end_hook_writes"),
 ("usage_hook.py", '            tot[k] += t[k]\n    append_usage', '            pass\n    append_usage', "session_end_hook_writes"),
 ("usage_hook.py", '                  tot["cache_create"], tot["cache_read"], tot["output"], "", window(account, "five_hour"),\n                  window(account, "seven_day")])', '                  tot["cache_create"], tot["cache_read"], tot["output"], "", "", ""])', "session_end_hook_writes"),
 ("run_seat.py", '    if f.exists() and any(ln.split("\\t")[7:8] == [session] for ln in f.read_text().splitlines()[1:]):', '    if False:', "never_twice"),
 ("run_seat.py", '    usage_hook.conductor_row(Path(tp), session, account)', '    pass', "never_twice"),
 ("board.py", '        print(f"{a:8} {line(v)}  {windows_of(a)}")', '        print(f"{a:8} {line(v)}")', "board_usage_totals"),
 ("board.py", '            out.append(f"{shown}: not reported by its sessions\' stream")', '            pass', "board_usage_totals"),
 ("merge_slice.py", '        if ci["state"] == "red":\n', '        if False:\n', "failed_run_on_main"),
 ("common.py", '            return {"state": "red", "run": run, "url": url, "why": "cancelled, with nothing newer"}', '            return {"state": "green", "run": run, "url": url, "why": "x"}', "cancelled_run_with_nothing_newer"),
 ("merge_slice.py", '        if ci["state"] != "green":\n', '        if False:\n', "cannot_be_read_refuses"),
 ("common.py", '            return {"state": "unknown", "run": None, "url": "", "why": "no run on main has completed"}', '            return {"state": "green", "run": None, "url": "", "why": "x"}', "cannot_be_read_refuses_never_green"),
 ("board.py", '            print(f"main is red: run {ci[\'run\']}', '            print(f"main: run {ci[\'run\']}', "board_prints_main_is_red"),
 ("board.py", '    ci = c.main_ci()\n    path = write_status(builds, owed=owed, ci=ci)', '    ci = c.main_ci()\n    path = write_status(builds, owed=owed)', "board_prints_main_is_red"),
]
bad = 0
for f, old, new, test in M:
    if ONLY and not any(o in f + " " + test for o in ONLY.split(",")):
        continue
    d = S / "OspreyFlow_Build/scripts/slice_line"
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(W / "OspreyFlow_Build/scripts/slice_line", d, ignore=shutil.ignore_patterns("__pycache__"))
    agents = S / ".claude/agents"  # the seats' definitions, read by the suite from the repository's root
    if agents.exists(): shutil.rmtree(agents)
    shutil.copytree(W / ".claude/agents", agents)
    target = S / f if f.startswith(".claude/") else d / f
    t = target.read_text()
    if old not in t:
        print("NOT FOUND", f, test); bad += 1; continue
    target.write_text(t.replace(old, new, 1))
    p = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-c", str(d / "tests/pytest.ini"), str(d / "tests"), "-k", test],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"})
    summary = ([ln for ln in p.stdout.splitlines() if ln.strip()] or [""])[-1]  # pytest's own last line, not a quoted one
    red = p.returncode != 0 and " failed" in f" {summary}" and "no tests ran" not in summary
    print(("RED  " if red else "STILL GREEN ") + f"{f:16} -> {test}")
    bad += 0 if red else 1
print("planted faults not caught:", bad)
