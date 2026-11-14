"""The guest words' backend plants (ADR-148 Amendment 17's line, rule 15). Each is planted alone in
principal_auth, the guest test run, and the tree restored from git. A plant counts as red only when every failing
case stopped at the assertion it names (the test file's line pytest reports), so a plant that some other check
refuses first, such as principal_auth's own assert, counts as missed rather than red.

Run from the repository root: python OspreyFlow_Build/process/lanes/admin/guest_words/plants.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
AUTH = "OspreyFlow_Core/packages/principal_auth/__init__.py"
TEST = "tests/services/api/test_entra_guests.py"
SITE = "            verified = _with_what_the_administrator_set(verified, mapping, stored)\n"

PLANTS = [
    ("a guest's token value kept where the deployment sets it (every value)",
     SITE + "            if verified.guest:  # PLANT: each value read from the token's own claim, as a member's unset ones are not\n"
            "                said = {k.rsplit('_', 1)[-1]: v for k, v in claims.items() if k.startswith('extension_')}\n"
            "                verified = dataclasses.replace(verified, clearance=said['clearance'], org_unit=said['orgUnit'], codes=list(said['handlingCodes']))\n",
     r"assert getattr\(guest, attr\)"),
    ("a guest refused in words of its own when a value set here is not set",
     "            try:  # PLANT\n"
     "                verified = _with_what_the_administrator_set(verified, mapping, stored)\n"
     "            except PrincipalResolutionError:\n"
     "                if verified.guest:\n"
     "                    raise PrincipalResolutionError(\"a guest's values are not set here: ask an administrator\") from None\n"
     "                raise\n",
     r"str\(as_guest\.value\) == str\(as_member\.value\)"),
]


def main() -> int:
    if subprocess.run(["git", "diff", "--quiet", "--", AUTH], cwd=ROOT).returncode:
        sys.exit(f"{AUTH} has changes: commit them first, since each plant is restored from git")
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    print(f"# backend plants at {head}")
    missed = 0
    # Offline, on the closed ports (no OSPREY_LANE): nothing here reaches a store.
    env = {k: v for k, v in os.environ.items() if k != "OSPREY_LANE"} | {
        "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(), "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992",
        "POSTGRES_PASSWORD": "throwaway", "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994"}
    for name, new, why in PLANTS:
        path = ROOT / AUTH
        s = path.read_text()
        assert s.count(SITE) == 1, name
        path.write_text(s.replace(SITE, new))
        try:
            out = subprocess.run(
                ["../OspreyFlow_Core/.venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider", TEST,
                 "-k", "people_never", "--tb=short"],
                cwd=ROOT / "OspreyFlow_Build", capture_output=True, text=True, env=env,
            ).stdout
        finally:
            subprocess.run(["git", "checkout", "--", AUTH], cwd=ROOT, check=True)
        source = (ROOT / "OspreyFlow_Build" / TEST).read_text().splitlines()
        stops = [int(n) for n in re.findall(rf"{re.escape(TEST)}:(\d+): in ", out)]
        failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", out)) else 0
        if not failed and not re.search(r"\d+ passed", out):
            sys.exit(f"{name}: the test did not run:\n{out[-2000:]}")
        off = [source[n - 1].strip() for n in stops if not re.search(why, source[n - 1])]
        red = failed > 0 and len(stops) == failed and not off
        missed += not red
        said = "RED at its assertion" if red else ("GREEN" if not failed else f"red for another reason: {off or stops}")
        print(f"== {name} (must fail at /{why}/): {said}, {failed} failed")
        print("\n".join(l for l in out.splitlines() if re.match(r"(E |\S+\.py:\d+: in |\d+ (passed|failed))", l))[:3000])
    print(f"plants: {len(PLANTS)}, missed: {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
