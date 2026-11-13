"""Rule 15's red-then-green for the step 6 driver: each plant breaks one check at its real call site in a
copy of the driver, runs the driver's tests against that copy, and must turn them red; the unplanted copy
must stay green. Run from OspreyFlow_Core:

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/v052/plants.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: (file, the line as it stands, the planted line, what it breaks)
PLANTS: list[tuple[str, str, str, str]] = [
    ("install_verify.py", "        if got.get(\"ready\") != w[\"count\"]:", "        if False:", "a workload not ready passes"),
    ("install_verify.py", "        unknown.extend(f\"{entry}: {k}\" for k in got if k not in known)", "        pass", "an unknown key inside an entry is not a stop"),
    ("install_verify.py", "    unknown: list[str] = [s for s in m if s not in SECTIONS]", "    unknown: list[str] = []", "an unknown section is not a stop"),
    ("install_verify.py", "    if pending and not allow_pending:", "    if False:", "a pending entry is not a stop"),
    ("install_verify.py", "    return (False, f\"{UNLISTED_HOST} reached on 443: egress is open\") if d.connects(UNLISTED_HOST) else (True, \"refused\")", "    return (True, \"refused\")", "open egress passes"),
    ("install_verify.py", "        if held and got.get(\"suspended\") is not True:", "        if False:", "a CronJob listed suspended that runs by itself passes"),
    ("install_verify.py", "        if not got.get(\"succeeded\"):", "        if False:", "a job never succeeded passes"),
    ("install_verify.py", "            elif steps[step].get(\"exit_code\") != 0:", "            elif False:", "a failed restore step passes"),
    ("install_verify.py", "        \"ready\": (obj.get(\"status\") or {}).get(\"readyReplicas\", 0),", "        \"ready\": (obj.get(\"status\") or {}).get(\"readyReplicas\", obj[\"spec\"].get(\"replicas\", 1)),", "kubectl's absent readyReplicas read as all ready"),
    ("install_verify.py", "    mine = found & set(expected)", "    mine = found", "a database reached by a stranger passes"),
    ("install_verify.py", "        except Exception as error:  # noqa: BLE001 - a check that cannot read its answer has failed, not passed\n            ok, said = False,", "        except Exception as error:  # noqa: BLE001 - a check that cannot read its answer has failed, not passed\n            ok, said = True,", "a check that raises passes"),
    ("spec08_poc.py", "    unknown = sorted(set(cases) - set(DISPOSITIONS))", "    unknown: list[str] = []", "a spec 08 case with no disposition runs unremarked"),
    ("spec08_poc.py", "    gone = sorted(set(DISPOSITIONS) - set(cases))", "    gone: list[str] = []", "a disposition for a case that no longer exists is not noticed"),
    ("spec08_poc.py", "            item.add_marker(pytest.mark.skip(reason=f\"not on poc: {reason}\"))", "            pass", "a case that cannot run on poc is run anyway"),
    ("spec08_poc.py", "    module._sign_in_as_the_demo_analyst = mint", "    pass", "the module still signs in at Keycloak"),
]


def run(folder: Path) -> tuple[int, str]:
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-c", str(HERE.parents[3] / "pytest.ini"), "-p", "no:cacheprovider", "-q", "-x",
         "-p", "no:randomly", str(folder)], capture_output=True, text=True, check=False,
        env={**os.environ, "OSPREY_V052_SPEC08_MODULE": str(HERE.parents[3] / "tests" / "scenarios" / "test_phase8_exit_over_the_wire.py")})
    last = [line for line in done.stdout.splitlines() if line.strip()][-1:] or [done.stderr[-200:]]
    return done.returncode, last[0]


def main() -> int:
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "v052"
        shutil.copytree(HERE, base, ignore=shutil.ignore_patterns("gates", "__pycache__", "plants.py"))
        code, said = run(base)
        print(f"{'GREEN' if code == 0 else 'RED  '} unplanted: {said}")
        bad += code != 0
        for file, line, planted, what in PLANTS:
            folder = Path(tmp) / f"p{PLANTS.index((file, line, planted, what))}"
            shutil.copytree(base, folder)
            text = (folder / file).read_text()
            if text.count(line) != 1:
                print(f"MISS  {what}: the line is not in {file} exactly once")
                bad += 1
                continue
            (folder / file).write_text(text.replace(line, planted))
            code, said = run(folder)
            print(f"{'RED  ' if code else 'GREEN'} {what}: {said}")
            bad += code == 0
    print("every plant red, unplanted green" if not bad else f"{bad} plant(s) not shown red")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
