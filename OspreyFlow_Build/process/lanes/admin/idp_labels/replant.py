"""The test-IdP labels' plants (the orchestrator's ruling, 14 Nov): each one violation, run alone against
test_run_owned.py with a fresh PYTHONPYCACHEPREFIX on closed ports, then restored. `python3 replant.py` from anywhere
in the checkout; a plant whose text is not found, or whose -k selects nothing (exit 5), is a MISS, not red."""
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE.parents[3]
CORE = BUILD.parent / "OspreyFlow_Core"
F, O = BUILD / "tests/harness/run_owned.py", BUILD / "tests/harness/test_organisation_sign_in.py"
PLANTS = [
    ("no_labels_on_the_container", O, '"--name", OWNED.container(name), *run_labels(), "--network"', '"--name", OWNED.container(name), "--network"', "labels"),
    ("no_labels_on_the_network", O, 'docker("network", "create", *run_labels(), name)', 'docker("network", "create", name)', "labels"),
    ("no_term_handler", F, "        signal.signal(signal.SIGTERM, on_term)\n", "", "term"),
    ("no_atexit", F, "        atexit.register(self.remove_all)\n", "", "exits_without"),
    ("network_removed_first", F, "        for name in containers:\n            self.remove_container(name)\n        for name in networks:\n            self.remove_network(name)\n", "        for name in networks:\n            self.remove_network(name)\n        for name in containers:\n            self.remove_container(name)\n", "term or exits_without"),
    ("container_not_recorded", O, '"--name", OWNED.container(name),', '"--name", name,', "term or exits_without"),
    ("network_not_recorded", O, '    name = OWNED.network(f"osprey-test-idp-{uuid.uuid4().hex[:8]}")', '    name = f"osprey-test-idp-{uuid.uuid4().hex[:8]}"', "term or exits_without"),
    ("term_swallowed", F, "            if callable(previous):\n                previous(signum, frame)\n            else:\n                os.kill(os.getpid(), signal.SIGTERM)\n", "", "term"),
]
CLOSED = {"ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
          "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | CLOSED
for name, f, old, new, k in PLANTS:
    src = f.read_text(encoding="utf-8")
    record = HERE / f"plant_{name}.txt"
    if src.count(old) != 1:
        record.write_text(f"PLANT MISS {name}\n"); print("MISS", name); continue
    f.write_text(src.replace(old, new), encoding="utf-8")
    try:
        r = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c",
                            "../OspreyFlow_Build/pytest.ini", "../OspreyFlow_Build/tests/harness/test_run_owned.py", "-k", k],
                           cwd=CORE, env=env | {"PYTHONPYCACHEPREFIX": tempfile.mkdtemp()}, capture_output=True,
                           text=True, timeout=300)
    finally:
        f.write_text(src, encoding="utf-8")
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "E   ")) or " passed" in ln or " failed" in ln]
    state = {0: "GREEN (not caught)", 5: "MISS (nothing selected)"}.get(r.returncode, "RED")
    record.write_text(f"# plant: {name}; fresh PYTHONPYCACHEPREFIX; closed ports; -k {k}\n# {state}\n" + "\n".join(lines[-6:]) + "\n")
    print(name, state, lines[-1] if lines else "")
