"""Rule 15's red-then-green record for the early warning: one planted fault per guard, each shown turning its test red,
in the line's own style (OspreyFlow_Build/scripts/slice_line/tests/plant_faults.py).

Usage: plant_faults.py <scratch dir> <a checkout of this branch> <a python with pytest and PyYAML> [<only tests naming this>]
Expected: every line RED, and "planted faults not caught: 0".
"""
import shutil, subprocess, sys
from pathlib import Path
S = Path(sys.argv[1]); W = Path(sys.argv[2]); PY = sys.argv[3]; ONLY = sys.argv[4] if len(sys.argv) > 4 else ""
E, D = "early_warning.py", "demo_server/"
M = [
 (E, '    if st.get("phase") != "verified":', '    if False:', "unverified_slice_is_refused"),
 (E, '    if not tip or st.get("tip") != tip:', '    if False:', "another_tip_is_refused"),
 (E, '    if not SETTING.is_file():', '    if False:', "missing_setting_file"),
 (E, '"refs/heads/main", *[f"refs/heads/{b}" for b in branches]]', '"--all"]', "bundle_carries_main_and_the_slice_tip"),
 (E, '    path = c.REPO / NOTES_REL / f"{name}.md"', '    path = c.rec_dir(slice_id) / f"{name}.md"', "nothing_under_records_changes"),
 (E, '        return "NO RESULT", NO_RESULT, f"the server could not be reached', '        return "GREEN", GREEN, f"the server could not be reached', "unreachable_server_is_no_result"),
 (E, '        return "NO RESULT", NO_RESULT, f"still running', '        return "GREEN", GREEN, f"still running', "still_going_at_the_deadline"),
 (E, '        return "REFUSED", REFUSED_THERE,', '        return "GREEN", GREEN,', "refusal_by_the_runner"),
 (E, '        return "RED", RED, "a check the server ran failed"', '        return "GREEN", GREEN, "a check the server ran failed"', "red_names_the_failing"),
 (E, '        text = text.replace(v, "<setting>")', '        pass', "host_shaped_string_in_the_setting"),
 (E, 'data.get("reason") == "bundle-prerequisites" and not full:', 'data.get("reason") == "bundle-prerequisites" and False:', "full_bundle_when_the_server_has_lost_it"),
 (D + "protocol.py", 'COMMAND = re.compile(r"\\A(?:(run)|(result) (%s)|(stack)((?: %s){2,%d}))\\Z"', 'COMMAND = re.compile(r"(?:(run)|(result) (%s)|(stack)((?: %s){2,%d}))"', "every_other_command_is_refused"),
 (D + "protocol.py", '    if "\\n" in received or "\\r" in received:\n        return None, "newline"', '    if False:\n        return None, "newline"', "every_other_command_is_refused"),
 (D + "protocol.py", 'return "%s\\trefused\\t%s\\tlength=%d\\n" % (at, reason, len(received or ""))', 'return "%s\\trefused\\t%s\\tlength=%d\\t%s\\n" % (at, reason, len(received or ""), received)', "every_other_command_is_refused"),
 (D + "runner.py", '    return real == root or real.startswith(root + os.sep)', '    return True', "planted_mount_outside_the_work_folder"),
 (D + "runner.py", '    if not run:\n        return False', '    if not run:\n        return True', "nothing_runs_uncapped"),
 (D + "runner.py", '    if set(heads) != {"refs/heads/main", *slices.values()} or (order is None and len(slices) != 1) \\', '    if not slices or False \\', "another_head_is_refused"),
 (D + "runner.py", '    if shutil.disk_usage(str(WORK)).free < p.MIN_FREE_BYTES:', '    if False:', "free_space_floor"),
 # the owner's condition before install: no test switch, no stand-in, no work folder from the environment, -I
 (D + "runner.py", '    run = shutil.which("systemd-run")\n', '    if os.environ.get("OSPREY_EARLY_TEST_LAUNCH") == "direct":\n        subprocess.Popen(me, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n        return True\n    run = shutil.which("systemd-run")\n', "launches_capped_and_runs_the_real_gate"),
 (D + "runner.py", '        result["steps"] = GATE(tree, job, log, deadline, result)', '        result["steps"] = ([{"step": "stand-in", "exit": 0, "seconds": 0}] if os.environ.get("OSPREY_EARLY_TEST_GATE") else GATE(tree, job, log, deadline, result))', "launches_capped_and_runs_the_real_gate"),
 (D + "runner.py", 'WORK = HERE.parent / "data"', 'WORK = Path(os.environ.get("OSPREY_EARLY_WORK") or str(HERE.parent / "data"))', "forced_command_ignores_them"),
 (D + "runner.py", '    me = [sys.executable, "-I", str(Path(__file__).resolve()), "_job", jid]', '    me = [sys.executable, str(Path(__file__).resolve()), "_job", jid]', "launches_capped_and_runs_the_real_gate"),
 (D + "install.sh", 'say "command=\\"/usr/bin/python3 -I $ROOT/bin/runner.py', 'say "command=\\"/usr/bin/python3 $ROOT/bin/runner.py', "forced_command_ignores_them"),
 (D + "runner.py", '"--property", "CPUQuota=" + p.CPU_QUOTA, ', '', "launches_capped_and_runs_the_real_gate"),
 # the demo shield
 (D + "runner.py", '        breaches = shield_breaches()\n', '        breaches = []\n', "reaches_another_accounts_port_runs_nothing"),
 (D + "runner.py", '            if len(parts) < 8 or parts[3] != "0A" or int(parts[7]) == own_uid:', '            if len(parts) < 8 or parts[3] != "0A":', "this_accounts_own_are_not"),
 (D + "runner.py", '            return s.connect_ex((addr, port)) == 0', '            return s.connect_ex((addr, port)) == 99', "reachable_is_a_breach"),
 (D + "runner.py", '        return ["the listening sockets cannot be read', '        return []\n        return ["the listening sockets cannot be read', "shield_cannot_be_checked"),
 # the failing tests named (002, item 3; run fc4d450f6f238ae2)
 (D + "runner.py", '"PYTEST_ADDOPTS": " ".join(["-rfEs"]', '"PYTEST_ADDOPTS": " ".join(["-rs"]', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '                names += [n for n in pending if n not in names]\n                pending = []\n                continue', '                pending = []\n                continue', "real_gate_runs_only_what_the_list_allows"),
 (E, '            out += [f"  - test `{n}`" for n in by.get(t, [])]', '            pass', "names_each_failing_test_under_its_target"),
 (E, '        out += [f"- test `{t}`" for t in fail.get("tests", []) if t not in named]', '        out += [f"- test `{t}`" for t in fail.get("tests", [])]', "names_each_failing_test_under_its_target"),
 # 005: the set-up faults of run fc4d450f6f238ae2
 (D + "runner.py", '    git(["clone", "-q", "--shared", "--no-checkout", str(SOURCE), str(tree)])\n    git(["-C", str(tree), "remote", "remove", "origin"])\n    git(["-C", str(tree), "checkout", "-q", "--detach", commit])', '    git(["-C", str(SOURCE), "worktree", "add", "-q", "--detach", str(tree), commit])', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '    git(["-C", str(tree), "remote", "remove", "origin"])\n', '', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '"OSPREY_LEASE_DIR": str(lease), "TEST_WORKERS": str(p.TEST_WORKERS),', '"OSPREY_LEASE_DIR": str(lease), "DOCKER_HOST": "unix:///dead.sock", "TEST_WORKERS": str(p.TEST_WORKERS),', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '        if docker_reachable():\n            raise Stop("error", "Docker\'s socket answers this account (%s): nothing was run" % ", ".join(docker_reachable()))\n        make_tree(tree, meta["main"])', '        make_tree(tree, meta["main"])', "reaches_dockers_socket_runs_nothing"),
 (D + "runner.py", '                s.connect(path)\n                open_.append(path)', '                s.connect(path)', "reaches_dockers_socket_runs_nothing"),
 (D + "runner.py", 'url = "https://extensions.duckdb.org/', 'url = "http://extensions.duckdb.org/', "docker_host_and_fetches_duckdbs_extension_over_https"),
 (D + "runner.py", '    result["duckdb_spatial"] = duckdb_spatial(core, env, log, deadline)\n', '', "real_gate_runs_only_what_the_list_allows"),
 # the resolver the shield allows (run 7a6267988c4ebce6)
 (D + "runner.py", '        if is_allowed_resolver(family, bound, port, resolvers):\n            continue', '        if False:\n            continue', "resolver_on_53_at_its_own_address"),
 (D + "runner.py", '    if port != 53:\n        return False', '    if False:\n        return False', "another_port_at_the_resolvers_address"),
 (D + "runner.py", '        return socket.inet_pton(family, bound) in resolvers', '        return True', "another_service_on_53_at_a_different_address"),
 (D + "runner.py", '                addr = "127.0.0.1" if bound == "0.0.0.0" else bound\n', '                addr = "127.0.0.1" if bound == "0.0.0.0" else bound\n                bound = addr\n', "wildcard_listener_on_53"),
 (D + "runner.py", '    out = set()\n    try:\n        lines = RESOLV.read_text().splitlines()', '    out = {socket.inet_pton(socket.AF_INET, socket.inet_ntoa(bytes((127, 0, 0, 53))))}\n    try:\n        lines = RESOLV.read_text().splitlines()', "resolv_conf_names_another_resolver"),
 (D + "shield.nft", '\t\tmeta skuid != "@USER@" accept\n', '', "touch_only_the_runners_account"),
 (D + "shield.nft", '\t\tct state established,related accept\n', '\t\tct state established,related accept\n\t\tmeta l4proto tcp th dport 443 accept\n', "refuse_this_machine_and_every_private_network"),
 (D + "shield.nft", '172.16.0.0/12,', '', "refuse_this_machine_and_every_private_network"),
 (D + "cleanup.sh", '  gone "the shield (nftables table inet osprey_early)" nft delete table inet osprey_early', '  : "the shield"', "removes_only_the_runners"),
 (D + "runner.py", '    clean_job(job, tree)  # first: a result means its work is gone, and the next job may start (run 7\'s race)\n    tmp = job / "result.json.tmp"\n    tmp.write_text(json.dumps(result, indent=1, sort_keys=True))\n    os.replace(str(tmp), str(job / "result.json"))\n', '    tmp = job / "result.json.tmp"\n    tmp.write_text(json.dumps(result, indent=1, sort_keys=True))\n    os.replace(str(tmp), str(job / "result.json"))\n    clean_job(job, tree)  # first: a result means its work is gone, and the next job may start (run 7\'s race)\n', "result_says_running_then_done"),
 (D + "runner.py", 'ask = urllib.request.Request(url, headers={"User-Agent": AGENT})', 'ask = urllib.request.Request(url, headers={"User-Agent": "Python-urllib/3.12"})', "spatial_fetch_names_a_client"),
 (D + "runner.py", '    said["stage"] = stage\n', '', "refused_spatial_fetch_says_where"),
 (D + "runner.py", '        said["http_status"] = e.code', '        pass', "refused_spatial_fetch_says_where"),
 ("early_warning.py", 'return "%s%s: %s" % (s["status"], where,', 'return "%s%s" % (s["status"], where) or (', "one_line_what_happened_to_duckdbs"),
 ("early_warning.py", '    if "duckdb_spatial" in d:', '    if False:', "one_line_what_happened_to_duckdbs"),
 (D + "runner.py", '    if job_alive(job):\n        return say({"state": "running"', '    if False:\n        return say({"state": "running"', "result_says_running_then_done"),
 (D + "runner.py", '    (lease / "no-local-stacks").write_text(', '    (lease / "stacks-allowed").write_text(', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '    env = {"PATH": os.pathsep.join([str(shim), str(node_bin)', '    env = {"PATH": os.pathsep.join([str(node_bin)', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '        elif r["verdict"] == "not-run":', '        elif False:', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '["--ignore=../%s" % n for n in ignores]', '[]', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '    not_run["test_files"] += [{"name": n,', '    [{"name": n,', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '        red = any(s["exit"] != 0 for s in result["steps"]) or result["failing"]["targets"] or result["failing"]["tests"]', '        red = False', "red_names_the_failing"),
 (D + "runner.py", '"PYTEST_DEBUG_TEMPROOT": str(job / "pytest"),', '', "real_gate_runs_only_what_the_list_allows"),
 (D + "lists.py", '        if r is None:\n            problems.append("test file', '        if False:\n            problems.append("test file', "starts_a_container_is_red_until_listed"),
 (D + "lists.py", '        elif PORT_FLAG.search(ln):', '        elif False:', "binds_a_fixed_port_is_red_until_listed"),
 (D + "lists.py", 'if SERVER_CALL.search(ln) and LITERAL_PORT.search(', 'if False and LITERAL_PORT.search(', "binds_a_fixed_port_is_red_until_listed"),
 (D + "lists.py", '        if spec not in mac:', '        if False:', "snapshot_for_macos_only"),
 (D + "lists.py", '            if not (tree / name).exists() and r["note"].startswith("pending: "):', '            if not (tree / name).exists():', "pending_row_may_name_a_file"),
 (D + "lists.py", '            if not (tree / name).exists() and r["note"].startswith("pending: "):', '            if r["note"].startswith("pending: "):', "checked_as_any_other_once"),
 (D + "lists.py", '        if kind == "test" and name not in tests:', '        if False:', "stale_row_is_red"),
 (D + "lists.py", '        if r["verdict"] == "run" and t["found"] and r["reason"] != "split" and not r["note"]:', '        if False:', "new_ci_target_is_red_until_listed"),
 (D + "cleanup.sh", 'case "$name" in "$PREFIX"*) gone "container $name"', 'case "$name" in *) gone "container $name"', "removes_only_the_runners"),
 (D + "cleanup.sh", 'case "$name" in "$PREFIX"*) gone "volume $name"', 'case "$name" in *) gone "volume $name"', "removes_only_the_runners"),
 (D + "cleanup.sh", 'if [ "$DRY" = yes ]; then printf', 'if false; then printf', "dry_run_lists_and_removes_nothing"),
 (D + "cleanup.sh", '  gone "the key\'s line in $keys (marker $MARKER)"', '  : "the key\'s line in $keys (marker $MARKER)"', "removes_only_the_runners"),
 # 009: the stack, the slots, one check per target, and the trust the merge asks for
 (D + "runner.py", '        for i, s in enumerate(stack):  # in merge order', '        for i, s in enumerate(stack[-1:]):  # in merge order', "each_candidate_at_once_one_job_each"),
 (D + "runner.py", '    if len(running) + want > p.MAX_JOBS:', '    if False:', "result_says_running_then_done"),
 (D + "runner.py", '    if len(running) + want > p.MAX_JOBS:', '    if len(running) > p.MAX_JOBS:', "waits_for_enough_free_slots"),
 (D + "runner.py", '    lanes = [ln for ln in GATE_LANES if ln not in lanes_in_use(running)][:want]', '    lanes = [GATE_LANES[0]] * want', "each_candidate_at_once_one_job_each"),
 (D + "runner.py", '            or (order is not None and set(slices) != set(order)):', '            or False:', "carries_exactly_the_slices_named"),
 (D + "runner.py", '        checks.append({"name": target, "kind": kind, "status": "passed" if ok else "failed",', '        checks.append({"name": target, "kind": kind, "status": "passed",', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '            checks.append({"name": t["name"], "kind": t["kind"], "status": "not run", "why": why["why"]})', '            pass', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '"OSPREY_PORTS_SLOT": lane_slot(tree, lane),', '"OSPREY_PORTS_SLOT": lane_slot(tree),', "take_their_own_port_slot"),
 (D + "protocol.py", '        if len(set(order)) != len(order):\n            return None, "shape"', '        if False:\n            return None, "shape"', "two_or_three_different_slices"),
 (D + "protocol.py", 'CPU_QUOTA = "400%"', 'CPU_QUOTA = "600%"', "launches_capped_and_runs_the_real_gate"),
 (D + "protocol.py", 'MEMORY_MAX = "12G"', 'MEMORY_MAX = "16G"', "launches_capped_and_runs_the_real_gate"),
 (E, '    code, data = ssh(s, ["result", jid], timeout=120)\n    if data is None:\n        return NO_RESULT', '    code, data = 0, {**json.loads(re.search(r"```json\\n(.*?)\\n```", (c.REPO / NOTES_REL / f"{slice_id}-{tip[:8]}.md").read_text(), re.S).group(1)), "state": "done", "id": jid, "checks": [{"name": n, "status": "passed"} for n in expected_checks(tree)]}\n    if data is None:\n        return NO_RESULT', "note_written_by_hand_never_counts"),
 (E, '    elif data.get("tree") != tree:', '    elif False:', "another_tree_is_not_trusted"),
 (E, '    elif data.get("verdict") != "pass":', '    elif False:', "red_run_is_not_trusted"),
 (E, '    elif data.get("runner_version") not in TRUSTED_VERSIONS:', '    elif False:', "no_check_per_target_is_not_trusted"),
 (E, '    elif data.get("slice") != slice_id or data.get("tip") != tip:', '    elif False:', "another_slice_tip_is_not_trusted"),
 (E, '            if missing:\n', '            if False:\n', "does_not_account_for_is_not_trusted"),
 (E, '    names += named_lists.prerequisites(core, "check")\n', '', "does_not_account_for_is_not_trusted"),
 (E, '        out.insert(out.index(f"- Main: `{d.get(\'main\', \'?\')}`") + 1, "- Stack: candidate', '        (lambda *a: None)(0, "- Stack: candidate', "one_note_per_candidate_naming_its_stack"),
 (E, '    name = f"{slice_id}-{tip[:8]}" + ("-after-" + "-".join(before) if before else "")', '    name = f"{slice_id}-{tip[:8]}"', "one_note_per_candidate_naming_its_stack"),
 (E, '                "by hand proves nothing.", "", "```json", json.dumps(block, indent=1), "```"]', '                "by hand proves nothing."]', "carries_the_lists_for_scripts"),
 (E, '        if r.get("slice") == slice_id and r.get("tip") == tip and isinstance(jid, str) \\', '        if isinstance(jid, str) \\', "auto_with_no_recorded_run"),
 (E, '    same = [x for x, tr in seen if tr == tree]', '    same = []', "auto_asks_about_the_run_of_this_tree"),
 # 012: the line-fix session's shape
 (D + "runner.py", '        if ok and (target == "test" or not server_skips) and target not in mac_owners:', '        if ok and target not in mac_owners:', "skip_inside_or_owning_a_mac_only_spec"),
 (D + "runner.py", '        if ok and (target == "test" or not server_skips) and target not in mac_owners:', '        if ok and (target == "test" or not server_skips):', "skip_inside_or_owning_a_mac_only_spec"),
 (D + "runner.py", '        if ok and (target == "test" or not server_skips) and target not in mac_owners:', '        if code == 0 and (target == "test" or not server_skips) and target not in mac_owners:', "real_gate_runs_only_what_the_list_allows"),
 (D + "runner.py", '    state = "running" if "running" in states else "died" if "died" in states else "done"', '    state = "done"', "each_candidate_at_once_one_job_each"),
 (D + "runner.py", '        return {"id": jid, "state": "done", **{k: r.get(k) for k in MEMBER_FIELDS}}', '        return {"id": jid, "state": "done", **{k: r.get(k) for k in MEMBER_FIELDS[:3]}}', "each_candidate_at_once_one_job_each"),
 (E, '    print(LAST_LINE[0])\n    return GREEN', '    print(json.dumps({k: v for k, v in data.items() if k != "advice"}, indent=1))\n    return GREEN', "fetch_prints_the_runners_own_line"),
 (E, '        print(LAST_LINE[0])\n        return REFUSED_THERE', '        print(LAST_LINE[0])\n        return GREEN', "fetch_of_a_run_the_server_does_not_hold"),
 (E, '    RUNNING.mkdir(parents=True, exist_ok=True)\n    c.write_json(', '    return\n    c.write_json(', "running_file"),
 (E, '    try:\n        running_file(slice_id, tip).unlink()', '    try:\n        pass', "running_file"),
 (E, '    if d.get("stack_id"):', '    if False:', "note_names_the_stacks_id"),
]
bad = 0
for f, old, new, test in M:
    if ONLY and not any(o in f + " " + test for o in ONLY.split(",")):
        continue
    d = S / "OspreyFlow_Build/scripts/slice_line"
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(W / "OspreyFlow_Build/scripts/slice_line", d, ignore=shutil.ignore_patterns("__pycache__"))
    target = d / f
    t = target.read_text()
    if old not in t:
        print("NOT FOUND", f, test); bad += 1; continue
    target.write_text(t.replace(old, new, 1))
    tests = d / "demo_server/tests"
    p = subprocess.run([PY, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", "-c", str(tests / "pytest.ini"), str(tests), "-k", test],
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"})
    summary = ([ln for ln in p.stdout.splitlines() if ln.strip()] or [""])[-1]
    red = p.returncode != 0 and " failed" in f" {summary}" and "no tests ran" not in summary
    print(("RED  " if red else "STILL GREEN ") + f"{f:28} -> {test}")
    bad += 0 if red else 1
print("planted faults not caught:", bad)
