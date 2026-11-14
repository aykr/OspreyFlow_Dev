"""ADR-044 Amendment 1's offline plants: each one violation, run alone against its test with a fresh
PYTHONPYCACHEPREFIX on closed ports, then restored. `python3 replant.py`; a plant whose text is not found, or whose -k
selects nothing (exit 5), is a MISS, not red. The store's live plant and the Glass's run beside these."""
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
CORE = BUILD.parent / "OspreyFlow_Core"
EV, WS = "services/api/evaluation.py", "services/api/watch_status.py"
TEST = "../OspreyFlow_Build/tests/services/api/test_stopped_why.py"
PLANTS = [
    ("hotlist_stop_says_nothing", EV, "            await hotlist_store.set_status(hotlist.id, \"stopped\", why)", "            await hotlist_store.set_status(hotlist.id, \"stopped\")", "hotlist_s_owner"),
    ("watch_stop_says_nothing", EV, "            await monitor_store.set_status(monitor.id, \"stopped\", why)", "            await monitor_store.set_status(monitor.id, \"stopped\")", "watch_s_owner_stops"),
    ("pattern_gone_unsaid", EV, "        await monitor_store.set_status(monitor.id, \"stopped\", \"pattern_gone\")", "        await monitor_store.set_status(monitor.id, \"stopped\")", "pattern_is_no_longer"),
    ("schedule_revoked_unsaid", "services/api/monitor_schedule.py", "            await self.monitors.set_status(monitor.id, \"stopped\", \"revoked\")", "            await self.monitors.set_status(monitor.id, \"stopped\")", "schedule_stops_it_as_revoked"),
    ("every_refusal_unresolved", EV, "        return None, reason_of(error)", "        return None, \"unresolved\"", "owner_stops_it_with_the_reason"),
    ("load_given_the_collapsed_resolver", "services/api/recipe_run.py", "    _principal_for_owner = _watch_owner_resolver(principal, principal_resolver)", "    _principal_for_owner = _owner_resolver(principal, principal_resolver)", "reason_the_detailed_resolver_gives"),
    ("out_of_date_read_as_unreachable", WS, "    if isinstance(error, PrincipalAccessOutOfDate):\n        return \"out_of_date\"\n", "", "out-of-date or out_of_date"),
    ("out_of_date_words_their_own", WS, "        f\"Its owner {ACCESS_OUT_OF_DATE_WORDS}. It is active again at the first load after they \"", "        \"Its owner is out of date. It is active again at the first load after they \"", "every_reason_has_its_words"),
    ("words_name_the_owner_id", WS, "    return STOPPED_WHY.get(reason) if reason else None", "    return (STOPPED_WHY.get(reason) or '') + ' (owner-1)' if reason in STOPPED_WHY else None", "every_reason_has_its_words"),
    ("not_held_said_as_refused", WS, "    if isinstance(error, OwnerNotHeld):\n        return \"not_held\"\n", "", "not-held"),
    ("unresolved_left_out_of_the_guide", WS, "    \"unresolved\": \"Its owner could not be acted as at the last load.\",", "    \"unresolved\": \"Its owner could not be acted as at the last load, for now.\",", "user_guide"),
    ("named_revoked_read_as_refused", WS, "    if isinstance(error, PrincipalRevoked):\n        return \"revoked\"\n", "", "revoked_principal_sets"),
    ("named_unreachable_read_as_unresolved", WS, "    if isinstance(error, (OwnerRecordUnavailable, PrincipalExchangeUnavailable)):\n        return \"unreachable\"\n", "", "unreachable_identity_provider_sets"),
    ("guide_reason_reworded", WS, "    \"refused\": \"The identity provider refused to act as its owner.\",", "    \"refused\": \"The sign-in service would not act for its owner.\",", "user_guide"),
]
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
          "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
for name, path, old, new, k in PLANTS:
    f = CORE / path
    src = f.read_text(encoding="utf-8")
    record = HERE / f"plant_{name}.txt"
    if src.count(old) != 1:
        record.write_text(f"PLANT MISS {name}\n"); print("MISS", name); continue
    f.write_text(src.replace(old, new), encoding="utf-8")
    try:
        r = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c",
                            "../OspreyFlow_Build/pytest.ini", "-m", "not live", TEST, "-k", k],
                           cwd=CORE, env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}, capture_output=True,
                           text=True, timeout=300)
    finally:
        f.write_text(src, encoding="utf-8")
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "E   ")) or " passed" in ln or " failed" in ln]
    state = {0: "GREEN (not caught)", 5: "MISS (nothing selected)"}.get(r.returncode, "RED")
    record.write_text(f"# plant: {name} ({path}); fresh PYTHONPYCACHEPREFIX; closed ports; -k {k}\n# {state}\n" + "\n".join(lines[-6:]) + "\n")
    print(name, state, lines[-1] if lines else "")
