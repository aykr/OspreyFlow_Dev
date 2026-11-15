"""Stage 2's never-join reach (the orchestrator's ruling, 15 November 2026), shown red (rule 15): main's
measure_search.py before the change, then three plants in measure_leaks as a real regression would
make them, each run against the reach tests and restored. Run from OspreyFlow_Core with closed ports:
.venv/bin/python ../OspreyFlow_Build/process/lanes/v060/stage2/reach_plants.py"""
import subprocess
from pathlib import Path

SRC = Path("scripts/measure_search.py")
TESTS = ["../OspreyFlow_Build/tests/test_measure_search.py", "-k",
         "page_2 or bound or last_result"]
PLANTS = [
    ("the control asks page 1 alone (the bound collapsed)",
     "for page in range(1, (REACH_PAGES if search else 1) + 1):",
     "for page in range(1, 2):"),
    ("the part-cleared principal asked page 1 alone, whatever page the control reached",
     "        for page in range(1, pages + 1):\n            page_path, page_body",
     "        for page in range(1, 2):\n            page_path, page_body"),
    ("the control looks past the bound",
     "for page in range(1, (REACH_PAGES if search else 1) + 1):",
     "for page in range(1, (REACH_PAGES + 2 if search else 1) + 1):"),
]


def run() -> tuple[int, str]:
    out = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
                          "no:cacheprovider", *TESTS], capture_output=True, text=True)
    failed = [ln.split("::")[1].split(" ")[0] for ln in out.stdout.splitlines() if ln.startswith("FAILED")]
    return out.returncode, ", ".join(failed) or out.stdout.strip().splitlines()[-1]


original = SRC.read_text(encoding="utf-8")
before = subprocess.run(["git", "show", "main:OspreyFlow_Core/scripts/measure_search.py"],
                        capture_output=True, text=True, check=True).stdout
try:
    SRC.write_text(before, encoding="utf-8")
    code, what = run()
    print(f"{'RED ' if code else 'GREEN (missed)'} main's measure_search.py: {what}")
    for name, old, new in PLANTS:
        assert original.count(old) == 1, f"plant site not unique: {name}"
        SRC.write_text(original.replace(old, new), encoding="utf-8")
        code, what = run()
        print(f"{'RED ' if code else 'GREEN (plant missed)'} {name}: {what}")
finally:
    SRC.write_text(original, encoding="utf-8")
code, what = run()
print(f"control (restored): {what}")
