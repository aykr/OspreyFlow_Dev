"""Rule 15's red-then-green for the step 6 driver: each plant breaks one check at its real call site in a
copy of the driver, runs the driver's tests against that copy, and must turn them red; the unplanted copy
must stay green; then the route reading's plants, in place and put back. Run from OspreyFlow_Core:

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
    ('install_verify.py', '        unknown.extend(f"{entry}: {k}" for k in got if k not in known)', '        pass', 'an unknown key inside an entry is not a stop'),
    ('install_verify.py', '    unknown: list[str] = [s for s in m if s not in SECTIONS]', '    unknown: list[str] = []', 'an unknown section is not a stop'),
    ('install_verify.py', '    if pending and not allow_pending:', '    if False:', 'a pending entry is not a stop'),
    ('install_verify.py', '        if held and got.get("suspended") is not True:', '        if False:', 'a CronJob listed suspended that runs by itself passes'),
    ('install_verify.py', '        if not got.get("succeeded"):', '        if False:', 'a job never succeeded passes'),
    ('install_verify.py', '            elif steps[step].get("exit_code") != 0:', '            elif False:', 'a failed restore step passes'),
    ('install_verify.py', '        "ready": status.get("readyReplicas", 0),', '        "ready": status.get("readyReplicas", obj["spec"].get("replicas", 1)),', "kubectl's absent readyReplicas read as all ready"),
    ('install_verify.py', '    mine = found & set(expected)', '    mine = found', 'a database reached by a stranger passes'),
    ('install_verify.py', "        except BaseException as error:  # noqa: BLE001 - a check that cannot read its answer has failed, not passed (r1's shell exits)\n            ok, said = False,", "        except BaseException as error:  # noqa: BLE001 - a check that cannot read its answer has failed, not passed (r1's shell exits)\n            ok, said = True,", 'a check that raises passes'),
    ('install_verify.py', '        except BaseException as error:', '        except Exception as error:', "r1's SystemExit ends the whole run"),
    ('install_verify.py', '        if not got.get("settled"):', '        if False:', 'a rollout the controller has not observed passes'),
    ('install_verify.py', '        return (got == m["shape"], ', '        return (True, ', 'another shape passes'),
    ('install_verify.py', '    if answer == "blocked":\n        return False\n    raise', '    if True:\n        return False\n    raise', 'a probe with no answer reads as blocked'),
    ('install_verify.py', '        if (c.get("image"), c.get("command"), c.get("args")) != (template.get("image"), template.get("command"), template.get("args")):', '        if False:', "the runbook's listing Job or a v0.5.1 run counts as a backup"),
    ('install_verify.py', '    return [j for j in job_names if j.startswith(prefix) and not any(j.startswith(p) for p in longer)]', '    return [j for j in job_names if j.startswith(prefix)]', "the claims restore's run counts as the graph's"),
    ('install_verify.py', '    return [p for p in pods if (p.get("status") or {}).get("phase") == "Running"]', '    return pods', "a finished pod's address names a reader"),
    ('install_verify.py', '            if "restore-graph" not in steps:\n                problems.append("step restore-graph absent")\n            else:\n                problems +=', '            if "restore-graph" not in steps or "restore-graph" not in j.get("steps", []):\n                pass\n            else:\n                problems +=', 'restore-graph unchecked when steps does not name it'),
    ('install_verify.py', '        keys(f"egress.{host}", entry or {}, EGRESS_KEYS)', '        pass', 'a key inside an egress entry is not a stop'),
    ('spec08_poc.py', '    if unplaced:\n        raise Undisposed', '    if False:\n        raise Undisposed', 'a collected case with no disposition runs'),
    ('spec08_poc.py', '    check_cases(cases_in(MODULE.read_text(encoding="utf-8")))  # the module as written, whatever the selection', '    check_cases({getattr(i, "originalname", i.name) for i in ours})', 'a narrowed selection stops the run'),
    ('spec08_poc.py', '    unknown = sorted(set(cases) - set(DISPOSITIONS))', '    unknown: list[str] = []', 'a spec 08 case with no disposition runs unremarked'),
    ('spec08_poc.py', '    gone = sorted(set(DISPOSITIONS) - set(cases))', '    gone: list[str] = []', 'a disposition for a case that no longer exists is not noticed'),
    ('spec08_poc.py', '            item.add_marker(pytest.mark.skip(reason=f"not on poc: {reason}"))', '            pass', 'a case that cannot run on poc is run anyway'),
    ('spec08_poc.py', '    module._sign_in_as_the_demo_analyst = mint', '    pass', 'the module still signs in at Keycloak'),
    ('install_verify.py', '        return False, f"{UNLISTED_HOST} reached on 443: egress is open"', '        pass', 'open egress passes'),
    ('install_verify.py', '                if not got.get("current"):\n                    behind.append', '                if False:\n                    behind.append', 'a workload or job on another reference passes the version check'),
    ('install_verify.py', '        if not ok:\n            behind.append(said)', '        if False:\n            behind.append(said)', 'a deployment of another release passes'),
    ('install_verify.py', '        if re.fullmatch(r"[0-9a-f]{7,40}", short) and candidate.startswith(short):', '        if True:', 'dev-unknown or another commit passes as the candidate'),
    ('install_verify.py', '                elif entry.get("image") in ours and got.get("tag") != candidate:', '                elif False:', 'one of ours tagged with another commit (or unknown) passes'),
    ('install_verify.py', '        if not _COMMIT.fullmatch(candidate):', '        if not candidate:', 'a short or tag-shaped candidate is taken'),
    ('install_verify.py', '    if "failed" in answer:', '    if False:', "the probe's failure read as an answer"),
    ('install_verify.py', '    if unsigned.get("status") != 403 or "not authorized" not in str(unsigned.get("error", "")):', '    if unsigned.get("status") != 403:', "any 403 taken for the domain's refusal"),
    ('install_verify.py', 'except BaseException as error:  # r1\'s kubectl keeps stdout alone', 'except ZeroDivisionError as error:  # r1\'s kubectl keeps stdout alone', "the probe's failure left on stderr"),
    ('install_verify.py', '        return release_of(self._get("configmap", "ospreyflow-env"))', '        return release_of(self._get("configmap", "ospreyflow-files"))', 'the release read from another ConfigMap'),
    ('install_verify.py', '    return all(expected[r] == c["image"] for c in containers if (r := _repository(c["image"], registry)) in expected)', '    return expected[_repository(spec["containers"][0]["image"], registry)] == spec["containers"][0]["image"]', 'an init or second container on the old reference passes'),
    ('install_verify.py', '    if _repository(spec["containers"][0]["image"], registry) not in expected:\n        return False', '    if False:\n        return False', 'a template the render never pinned reads as the candidate'),
    ('install_verify.py', '        runs.sort(key=lambda j: j["metadata"].get("creationTimestamp", ""))  # the newest last: the candidate\'s', '        pass', "kubectl's name order picks the run read"),
    ('install_verify.py', '    if unsigned.get("status") != 403 or "not authorized" not in str(unsigned.get("error", "")):', '    if False:', 'a search reader answered unsigned passes (not the domain)'),
    ('install_verify.py', '    if not isinstance(signed.get("count"), int) or signed["count"] < 1:', '    if False:', 'an empty search alias passes'),
    ('install_verify.py', '    if signed.get("status") != 200:', '    if False:', 'a refused signed search count passes'),
    ('install_verify.py', '    if answer.get("signing") != "sigv4":', '    if False:', 'a search reader that does not sign passes'),
    ('install_verify.py', '            if refused:\n                raise LookupError', '            if False:\n                raise LookupError', "a search reader's refusal is not said"),
    ('install_verify.py', '    if host.startswith("<"):', '    if False:', 'an egress placeholder is probed'),
    ('install_verify.py', '        if got.get("replicas") != w["count"]:', '        if False:', 'a rollout still holding the old pod passes'),
    ('install_verify.py', '        if got.get("unavailable"):', '        if False:', 'an unavailable replica passes'),
    ('install_verify.py', '        for field in ("updated", "ready", "available"):', '        for field in ():', 'updated, ready and available unchecked'),
    ('install_verify.py', '        if got.get("revisions_match") is False:', '        if False:', 'a StatefulSet mid-update passes'),
    ('install_verify.py', '        "unavailable": status.get("unavailableReplicas", 0),', '        "unavailable": 0,', "kubectl's unavailableReplicas ignored"),
    ('install_verify.py', '    if not d.reachable_outside(UNLISTED_HOST):', '    if False:', 'an offline node reads as egress blocked'),
    ('install_verify.py', '    return str((config.get("cloud_platform") or {}).get("shape") or "standard")', '    return "poc"', 'the shape is not read from the deployed configuration'),
    ('install_verify.py', '"current": current(template, self.registry, self.expected), "tag"', '"current": True, "tag"', "a CronJob's template on the old release reads as current"),
    ('install_verify.py', '                "current": current(job["spec"]["template"]["spec"], self.registry, self.expected),\n                "tag"', '                "current": False,\n                "tag"', "a restore run at the candidate's image reads as old"),
    ('install_verify.py', '        found += [c["image"] for c in w.get("initContainers") or []]', '        pass', "init containers' references left out of the candidate's"),
    ('install_verify.py', '            if obj:\n                return read_workload', '            if obj and kind == "deployment":\n                return read_workload', 'a StatefulSet is never found'),
    ('install_verify.py', '        for field in ("updated", "ready", "available"):\n            if got.get(field) != w["count"]:', '        for field in ("updated", "available"):\n            if got.get(field) != w["count"]:', 'a workload not ready passes'),
]


#: The closing-pass proof's route reading (tests/scenarios/test_over_the_wire_routes_exist.py), planted in place and
#: put back: (the line as it stands, the planted line, what it breaks).
ROUTES = HERE.parents[3] / "tests" / "scenarios" / "test_over_the_wire_routes_exist.py"
ROUTE_PLANTS: list[tuple[str, str, str]] = [
    ('        if path is None or path.startswith("{") or ("/v1/" in path and not path.startswith("/v1/")):', '        if False:', 'unreadable calls skipped'),
    ('        if path is None or path.startswith("{") or ("/v1/" in path and not path.startswith("/v1/")):', '        if path is None or ("/v1/" in path and not path.startswith("/v1/")):', 'a path led by a field that is not an origin skipped'),
    ('NOT_THE_CONDUIT = {"browser.get(authorize)", "browser.post(form_action.group(1)", "browser.post(f\'{KEYCLOAK_ORIGIN}/realms/"}', 'NOT_THE_CONDUIT: set[str] = set()', 'the sign-in exceptions removed (the real module has unreadable calls)'),
    ('        return text.removeprefix("{}") if text.startswith("{}/v1/") else text  # an origin before the path', '        return text', 'an origin-prefixed path not read'),
    ('            match = re.fullmatch(r"\\{\\}://\\{\\}(/v1/.*)", text)', '            match = None', 'the stream the module opens not read'),
]


def run_routes() -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"}
    env.update(ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993",
               CLICKHOUSE_HTTP_PORT="59994")  # closed ports: the reading needs no store
    done = subprocess.run([sys.executable, "-m", "pytest", "-c", str(HERE.parents[3] / "pytest.ini"), "-p", "no:cacheprovider",
                           "-q", "-p", "no:randomly", str(ROUTES)], capture_output=True, text=True, check=False, env=env)
    last = [line for line in done.stdout.splitlines() if line.strip()][-1:] or [done.stderr[-200:]]
    return done.returncode, last[0]


def route_plants() -> int:
    bad = 0
    original = ROUTES.read_text()
    try:
        code, said = run_routes()
        print(f"{'GREEN' if code == 0 else 'RED  '} routes unplanted: {said}")
        bad += code != 0
        for line, planted, what in ROUTE_PLANTS:
            if original.count(line) != 1:
                print(f"MISS  {what}: the line is not in {ROUTES.name} exactly once")
                bad += 1
                continue
            ROUTES.write_text(original.replace(line, planted))
            code, said = run_routes()
            print(f"{'RED  ' if code else 'GREEN'} {what}: {said}")
            bad += code == 0
    finally:
        ROUTES.write_text(original)
    return bad


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
    bad += route_plants()
    print("every plant red, unplanted green" if not bad else f"{bad} plant(s) not shown red")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
