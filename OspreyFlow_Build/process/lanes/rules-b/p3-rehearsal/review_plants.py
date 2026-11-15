"""rules-b P3, after the lane review: plants for the tests added for its findings 2 and 5 (rule 15).
Each plant edits map_admin.py as a real regression would, runs the stage tests, and restores the file.
Run from OspreyFlow_Core with the closed ports pinned: .venv/bin/python <this file>."""
import subprocess
from pathlib import Path

SRC = Path("services/api/map_admin.py")
TESTS = "../OspreyFlow_Build/tests/test_basemap_build_stages.py"
PLANTS = [
    ("--stage places sent down the bare tiles path (the dispatch widened)",
     'if args.verb == "build" and args.stage == "tiles":',
     'if args.verb == "build" and args.stage in ("tiles", "places"):'),
    ("the unit check skipped for the places stage",
     "        await check_unit_from_env(unit, region=region)\n",
     '        if stage != "places":\n            await check_unit_from_env(unit, region=region)\n'),
    ("the admin reached for in the bare tiles branch after the builder check",
     '            progress("Saving the extract\'s settlements for the places stage...")\n',
     '            progress("Saving the extract\'s settlements for the places stage...")\n'
     '            admin.basemap()\n'),
    ("the bare stage's refusal exits 0",
     "    except MapAdminRefused as refused:\n        print(refused.words, file=sys.stderr)\n        return 1\n"
     "    except Exception as error:",
     "    except MapAdminRefused as refused:\n        print(refused.words, file=sys.stderr)\n        return 0\n"
     "    except Exception as error:"),
]


def run() -> tuple[int, str]:
    out = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
                          "no:cacheprovider", TESTS], capture_output=True, text=True)
    failed = [ln.split("::")[1].split(" ")[0] for ln in out.stdout.splitlines() if ln.startswith("FAILED")]
    return out.returncode, ", ".join(failed) or out.stdout.strip().splitlines()[-1]


original = SRC.read_text(encoding="utf-8")
try:
    for name, old, new in PLANTS:
        assert original.count(old) == 1, f"plant site not unique: {name}"
        SRC.write_text(original.replace(old, new), encoding="utf-8")
        code, what = run()
        print(f"{'RED ' if code else 'GREEN (plant missed)'} {name}: {what}")
finally:
    SRC.write_text(original, encoding="utf-8")
code, what = run()
print(f"control (restored): {what}")
