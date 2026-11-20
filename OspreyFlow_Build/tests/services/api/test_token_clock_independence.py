"""A test's token is minted when the test runs, so its result cannot depend on how long the suite takes
(slice CO2b, rule 12).

**Which test fails if the fault returns.** `test_the_auth_tests_pass_when_the_suite_is_slow` fails, naming
the tests and quoting "Signature has expired", if any test of the auth modules below mints a token while
its module is imported. Today's `test_auth_entra_pages.py::test_a_token_from_a_realm_client_without_the_
audience_mapper_is_refused` (both parameters) was that fault: its `parametrize` list called
`default_claims(...)` at collection, the token's 300-second life began there, and on GitHub's 40 to 49
minute suite (runs 44730215386 and 44739376824) it had ended when the test ran. On the Mac the suite is
fast and it passed, so nothing local could show it. The same module's other `parametrize` lists called
`entra_claims(...)` (an hour's life), `test_auth_entra_superset.py` did the same, and
`test_auth_entra_dashboards.py` called `app_only_claims(...)`: this test runs them all a long way
into the suite and shows each of them red on the old code.

How the delay is planted: `tests/clock_skew.py` (a plugin of `tests/conftest.py`) reads
`OSPREY_TEST_CLOCK_SKEW_SECONDS` and, once collection is over, moves the wall clock that many seconds on
(both `time.time` and the `datetime` PyJWT's `decode` reads: PyJWT does not use `time.time`). The skew
here is longer than the longest token any of these tests mints (an hour, `entra_claims`) plus the
resolver's 60 seconds of leeway. A token minted inside its test is stamped by the moved clock and so
stays valid; one minted at import is `SKEW` seconds old when its test runs.

Rule 15: the switch itself is shown to work, separately, on a module of this file's own making (a token
minted at import is refused as expired; the same token minted in the test is accepted), so "the auth
modules passed" cannot be a skew that did nothing. The standing guard, `tests/test_no_token_minted_at_
import.py`, finds the same sites by reading the source.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

BUILD = Path(__file__).resolve().parents[3]  # OspreyFlow_Build, where pytest.ini lives

#: Longer than an hour's token (`entra_claims`, `app_only_claims`) and the 60 seconds of leeway.
SKEW = 3_700

#: The modules that mint a token and put it to the Conduit's `PrincipalResolver` (or the sign-in's own
#: verifier): the auth modules and their neighbours that use `sign_token`.
AUTH_MODULES = (
    "tests/services/api/test_auth.py",
    "tests/services/api/test_auth_entra_administrator_access.py",
    "tests/services/api/test_auth_entra_claims.py",
    "tests/services/api/test_auth_entra_dashboards.py",
    "tests/services/api/test_auth_entra_pages.py",
    "tests/services/api/test_auth_entra_superset.py",
    "tests/services/api/test_auth_entra_token_version.py",
    "tests/services/api/test_entra_guests.py",
    "tests/services/api/test_entra_people.py",
    "tests/services/api/test_owner_on_entra.py",
    "tests/services/api/test_service_identity_entra.py",
    "tests/services/api/test_service_identity_and_rollup.py",
    "tests/services/api/test_sign_in_refusal_tags.py",
    "tests/services/api/test_websocket_auth.py",
    "tests/harness/test_oidc.py",
)


def _pytest(args: list[str], *, skew: int, cwd: Path = BUILD) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        # No store: the same pins every pure command carries, so a stray test cannot reach the live ones.
        "ARCADEDB_HTTP_PORT": os.environ.get("ARCADEDB_HTTP_PORT", "9"),
        "POSTGRES_PORT": os.environ.get("POSTGRES_PORT", "9"),
        "OSPREY_TEST_CLOCK_SKEW_SECONDS": str(skew),
        "PYTHONPATH": os.pathsep.join(
            [str(BUILD), *([os.environ["PYTHONPATH"]] if os.environ.get("PYTHONPATH") else [])]
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--no-header", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=1_500,
        check=False,
    )


def _failed(output: str) -> str:
    return "\n".join(line for line in output.splitlines() if line.startswith("FAILED"))


def test_the_auth_tests_pass_when_the_suite_is_slow() -> None:
    """The auth modules, run with the clock `SKEW` seconds past collection, pass: no token's result depends
    on how long the suite has been running. On the old code this names the pages module's parameters
    (`test_a_token_from_a_realm_client_without_the_audience_mapper_is_refused`) among the failures."""
    for module in AUTH_MODULES:
        assert (BUILD / module).is_file(), f"{module}: listed as an auth module but not there"
    ran = _pytest(["-c", "pytest.ini", *AUTH_MODULES], skew=SKEW)
    output = ran.stdout + ran.stderr
    assert ran.returncode == 0 and "Signature has expired" not in output, (
        f"the auth tests failed with the clock {SKEW} s past collection:\n{_failed(output)}\n"
        + "\n".join(line for line in output.splitlines() if "Signature has expired" in line)[:1_500]
    )
    passed = re.search(r"(\d+) passed", output)
    assert passed and int(passed.group(1)) > 300, (
        f"too few tests ran to mean anything: {output[-400:]}"
    )


# --- rule 15: the switch is shown to age a token minted at import, and not one minted in the test -------

_PLANTED = textwrap.dedent(
    """
    import time

    import jwt
    import pytest
    from cryptography.hazmat.primitives.asymmetric import rsa

    KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


    def mint() -> str:
        now = int(time.time())
        return jwt.encode({"sub": "a", "iat": now, "exp": now + 300}, KEY, algorithm="RS256")


    def verify(token: str) -> None:
        jwt.decode(token, KEY.public_key(), algorithms=["RS256"], options={"verify_aud": False})


    AT_IMPORT = mint()


    @pytest.mark.parametrize("token", [AT_IMPORT], ids=["minted-at-import"])
    def test_minted_at_import(token):
        verify(token)


    @pytest.mark.parametrize("make", [mint], ids=["minted-when-it-runs"])
    def test_minted_when_it_runs(make):
        verify(make())
    """
)


def _planted_run(tmp_path: Path, skew: int) -> tuple[subprocess.CompletedProcess[str], str]:
    (tmp_path / "test_planted.py").write_text(_PLANTED)
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    ran = _pytest(
        ["-c", str(tmp_path / "pytest.ini"), "--rootdir", str(tmp_path), "-p", "tests.clock_skew",
         str(tmp_path / "test_planted.py")],
        skew=skew,
        cwd=tmp_path,
    )  # fmt: skip
    return ran, ran.stdout + ran.stderr


def test_the_switch_ages_a_token_minted_at_import_and_not_one_minted_in_the_test(
    tmp_path: Path,
) -> None:
    ran, output = _planted_run(tmp_path, skew=400)
    assert "Signature has expired" in output, output[-1_500:]
    assert "test_minted_at_import" in _failed(output)
    assert "test_minted_when_it_runs" not in _failed(output)
    assert "1 failed, 1 passed" in output


def test_with_no_skew_the_same_planted_module_passes(tmp_path: Path) -> None:
    """The failure above is the clock's, not the planted module's own."""
    ran, output = _planted_run(tmp_path, skew=0)
    assert ran.returncode == 0 and "2 passed" in output, output[-1_500:]


def test_a_skew_that_is_not_a_number_is_refused_in_words(tmp_path: Path) -> None:
    (tmp_path / "test_x.py").write_text("def test_x(): ...\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    env = {**os.environ, "OSPREY_TEST_CLOCK_SKEW_SECONDS": "slow", "PYTHONPATH": str(BUILD)}
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-c", str(tmp_path / "pytest.ini"),
         "-p", "tests.clock_skew", str(tmp_path / "test_x.py")],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=300, check=False,
    )  # fmt: skip
    assert ran.returncode != 0 and "must be a number of seconds" in ran.stdout + ran.stderr
