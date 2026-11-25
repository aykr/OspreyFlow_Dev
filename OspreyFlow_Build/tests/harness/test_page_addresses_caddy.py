"""The real Caddy validates the front proxy's Caddyfile for every case (build id PL7, slice PL7f;
the owner's condition of 23 November 2026: the real proxy runs on every merge).

Round 9 of the earlier work rendered a Caddyfile with an HTTPS identity site on the port the
catch-all serves as plain HTTP, and Caddy refuses to load it: the deployment's only door did not
start. Every test of it ran a pure model of that refusal, and the real Caddy ran on no merge (the
Mac's gate has Docker and the proxy image, but no `caddy` binary, so `access_key_proxy_fixtures.py`
skips). **This test runs the image the deployment uses** (`harness.site.PROXY_IMAGE`,
`caddy:2.11.4-alpine`), once for the whole table, with `caddy validate` on each rendered Caddyfile.

**What is asked, and which case fails if it is broken (rule 12).**

* Every derived row of `tests/fixtures/page_addresses_cases.json`, under both brands, renders a
  Caddyfile the real Caddy loads (`test_the_real_caddy_loads_every_derived_case`). The cluster's
  is the file `render_caddyfile` writes for a proxy with no alias and no doors.
* **Red first (rule 15):** with `derive`'s port refusal taken out (`_port_taken`), the render writes
  the round-9 Caddyfile for each row where the clash is real, and the real Caddy refuses it
  (`test_the_real_caddy_refuses_each_clash_the_port_refusal_stands_in_front_of`); the pure model
  finds the same port, as the fast check that is never the only one. The same deployments with the
  setting off load, so the page service's listener is what the refusal guards.
* The refusals that are the owner's policy and not Caddy's (an HTTPS origin on 8080 in the ACME
  shape, port 80 with the redirect) are planted out too, and what Caddy says is printed, never
  assumed.

**Where it runs, and where it does not.** The Mac's gate (Docker and the image are there). GitHub's
`access-key-proxy-test` job also has Docker and the image's Caddy; GitHub is no merge gate (the
release's), so it is a second place (a diff for the owner adds this file to that job's command). The
test server has no container tooling: there it is listed as not run, never as passed. **It does not
skip:** if neither the image can be run nor a Caddy 2.11 binary (`OSPREY_CADDY_BINARY`) is given, it
fails in words. The repository's Docker guard (`tests/local_docker_guard.py`) refuses every
docker call under the owner's per-machine switch (`no-local-stacks`); the owner's ruling D234
(24 November 2026) exempts **exactly one command, this test's**: `docker run --rm --network none`
with three read-only mounts of folders under the temporary folder, the pinned image and
`sh -c <script>` (the guard names this file and holds the whole shape, and the test's script is
the guard's own constant). So this test makes **no other docker call**: it does not ask
`docker image inspect` (the run itself says whether the image is there: `--network none` cannot
pull it) and it does not hash the shared key with the image (Caddy's `validate` reads the hash as
base64 and checks nothing more, measured on 25 November 2026, so a placeholder of a bcrypt's
shape stands in: it is the Caddyfile that is validated, never a key). If the guard refuses the
one command (the shape changed) the test fails in words, never skips. When 017-1 lands this test
moves to the test server's container checks and the exemption comes out.

**What this test walks and reads.** The one table file (through `page_addresses_fixtures.py`), the
renderers it imports, and `OspreyFlow_Core/harness/site.py`'s `PROXY_IMAGE`. It writes only to
`tmp_path`: a Caddyfile per case, a self-made certificate and key (never a real one), and the
shared-key file `harness.access_key` writes, with a hash the image makes of a synthetic string.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from harness import access_key, page_addresses
from harness.site import CERT_IN_PROXY, KEY_IN_PROXY, PROXY_IMAGE, render_caddyfile

from tests.harness.page_addresses_fixtures import (
    BRANDS,
    DERIVED,
    ROWS,
    clash_findings,
    config_of,
    render_of,
)
from tests.local_docker_guard import CADDY_SCRIPT

#: A synthetic string, hashed by the image for the shared key's file; never a real key.
SYNTHETIC_KEY = "a long shared demonstration key"
#: One container validates every case (the guard holds the script: it is part of the command it
#: exempts, so the two cannot differ).
SCRIPT = CADDY_SCRIPT
#: What stands in for the shared key's hash: of a bcrypt's shape, the hash of nothing. Caddy's
#: `validate` decodes it as base64 and goes no further (measured), and no key is ever written.
PLACEHOLDER_HASH = "$2a$14$" + "a" * 53
#: The rows where the round-9 clash is real: Caddy cannot load the file the render would write.
CLASH_ROWS = [
    "9-own-certificate-8080",
    "12-own-certificate-graph-store-door",
    "12-own-certificate-conduit-door",
    "12-acme-plain-http-port",
    "12-acme-graph-store-door",
    "12-acme-conduit-door",
]
#: Refusals that are the owner's policy: the render's Caddyfile would load (measured), the
#: deployment is refused because an HTTPS identity address belongs on no plain-HTTP port.
POLICY_ROWS = ["19-acme-8080", "12-own-certificate-redirect-port"]


#: Found once, at import: the test that empties `PATH` to plant "no docker" keeps openssl.
OPENSSL = shutil.which("openssl") or "openssl"


class Result:
    def __init__(self, code: int, said: str) -> None:
        self.ok = code == 0
        self.said = said


def _row(row_id: str) -> dict[str, Any]:
    [row] = [r for r in ROWS if r["id"] == row_id]
    return row


def _own_certificate(folder: Path) -> None:
    folder.mkdir(parents=True)
    done = subprocess.run(
        [
            OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-keyout", str(folder / "key.pem"), "-out", str(folder / "cert.pem"),
            "-subj", "/CN=osprey.example.org",
            "-addext", "subjectAltName=DNS:osprey.example.org,DNS:id.osprey.example.org",
        ],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    assert done.returncode == 0, (
        f"openssl could not make the certificate the cases mount: {done.stderr}"
    )


def _parse(output: str) -> dict[str, Result]:
    found: dict[str, Result] = {}
    for block in output.split("@@CASE ")[1:]:
        head, _, said = block.partition("\n")
        name, code = head.split()
        found[name] = Result(int(code), said.strip())
    return found


def _binary() -> str | None:
    """A Caddy 2.11 binary given by `OSPREY_CADDY_BINARY` (GitHub's job takes it from the image)."""
    given = os.environ.get("OSPREY_CADDY_BINARY")
    if not given or not Path(given).is_file():
        return None
    version = subprocess.run([given, "version"], capture_output=True, text=True, check=False)
    return given if version.stdout.startswith("v2.11") else None


def _run_the_image(cases: Path, etc: Path, certs: Path) -> tuple[str | None, str]:
    """(None, what the container said) where the image ran the cases; (the words, "") where it
    could not: no docker, no image (the run cannot pull: `--network none`), or the guard's refusal.
    The command is the one the Docker guard exempts, word for word."""
    try:
        done = subprocess.run(
            [
                "docker", "run", "--rm", "--network", "none",
                "-v", f"{cases}:/cases:ro",
                "-v", f"{etc}:/etc/caddy:ro",
                "-v", f"{certs}:/certs:ro",
                PROXY_IMAGE, "sh", "-c", SCRIPT,
            ],
            capture_output=True, text=True, check=False, timeout=600,
        )  # fmt: skip
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return f"docker could not be run ({error})", ""
    except pytest.skip.Exception as refused:  # the Docker guard's refusal: never a skip here
        return f"the Docker guard refused the call ({refused})", ""
    if done.returncode != 0:
        return (
            f"docker could not run {PROXY_IMAGE} (exit {done.returncode}: "
            f"{done.stderr.strip()[:300]})",
            "",
        )
    return None, done.stdout


def _validate_all(files: dict[str, str], folder: Path) -> dict[str, Result]:
    """Every file in `files` (name -> Caddyfile text) through `caddy validate`: in one container of
    the image the deployment uses, or, where Docker cannot run it, by the binary given. Neither:
    the test fails, in words (it is never skipped)."""
    cases, etc, certs = folder / "cases", folder / "etc", folder / "certs"
    etc.mkdir(parents=True)
    _own_certificate(certs)
    for name, text in files.items():
        (cases / name).mkdir(parents=True)
        (cases / name / "Caddyfile").write_text(text, encoding="utf-8")
    (etc / access_key.ACCESS_KEY_FILE).write_text(
        access_key.snippet("demo", PLACEHOLDER_HASH, "synthetic-pass-for-validation"),
        encoding="utf-8",
    )
    problem, said = _run_the_image(cases, etc, certs)
    binary = _binary() if problem else None
    assert problem is None or binary is not None, (
        f"the real Caddy cannot be run, so the Caddyfiles are unchecked: {problem}. Pull "
        f"{PROXY_IMAGE} on a machine with Docker, or set OSPREY_CADDY_BINARY to a Caddy 2.11 "
        "binary. This test does not skip."
    )
    if problem is None:
        results = _parse(said)
    else:
        assert binary is not None
        results = {}
        for name in files:
            path = cases / name / "Caddyfile"
            text = path.read_text(encoding="utf-8")
            for old, new in (
                (CERT_IN_PROXY, str(certs / "cert.pem")),
                (KEY_IN_PROXY, str(certs / "key.pem")),
                (access_key.IN_PROXY, str(etc / access_key.ACCESS_KEY_FILE)),
            ):
                text = text.replace(old, new)
            path.write_text(text, encoding="utf-8")
            done = subprocess.run(
                [binary, "validate", "--config", str(path), "--adapter", "caddyfile"],
                capture_output=True, text=True, check=False, timeout=120,
            )  # fmt: skip
            results[name] = Result(done.returncode, (done.stdout + done.stderr).strip())
    assert set(results) == set(files), "the container said nothing about some case"
    return results


def _caddyfile(row: dict[str, Any], brand: str) -> str:
    config = config_of(row, brand)
    if row["config"]["shape"] in ("local-lite", "small"):
        return render_of(config)["Caddyfile"]
    return render_caddyfile(config, doors=False)


@pytest.fixture(scope="module")
def validated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Result]:
    """Every case's Caddyfile through the real Caddy, once: the derived rows under both brands, the
    planted ones (the port refusal taken out), and the same deployments with the setting off."""
    files: dict[str, str] = {}
    for row in DERIVED:
        for brand in BRANDS:
            files[f"derived--{row['id']}--{brand}"] = _caddyfile(row, brand)
    for row_id in CLASH_ROWS + POLICY_ROWS:
        row = _row(row_id)
        with mock.patch.object(page_addresses, "_port_taken", lambda *a, **k: None):
            files[f"planted--{row_id}"] = _caddyfile(row, "ospreyflow")
        off = {**row, "config": {**row["config"], "pages": False}}
        files[f"off--{row_id}"] = _caddyfile(off, "ospreyflow")
    results = _validate_all(files, tmp_path_factory.mktemp("caddy"))
    for name, result in sorted(results.items()):
        said = result.said.splitlines()[-1][:160] if result.said else ""
        print(f"caddy validate {name}: {'valid' if result.ok else 'REFUSED'} {said}")
    return results


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("row", DERIVED, ids=[r["id"] for r in DERIVED])
def test_the_real_caddy_loads_every_derived_case(
    row: dict[str, Any], brand: str, validated: dict[str, Result]
) -> None:
    result = validated[f"derived--{row['id']}--{brand}"]
    assert result.ok, result.said


def test_every_derived_row_of_the_table_was_asked_of_the_real_caddy(
    validated: dict[str, Result],
) -> None:
    """A row added to the table is validated at once: the cases the real Caddy was asked are the
    table's, none left out (the fixture builds its list from the table, not from a list here)."""
    asked = {name.split("--")[1] for name in validated if name.startswith("derived--")}
    assert asked == {row["id"] for row in DERIVED}


@pytest.mark.parametrize("row_id", CLASH_ROWS)
def test_the_real_caddy_refuses_each_clash_the_port_refusal_stands_in_front_of(
    row_id: str, validated: dict[str, Result]
) -> None:
    """Round 9's fault at the shape the renderer writes it: the identity site's second `https://`
    address on a port the same file serves as plain HTTP. Red: the real Caddy refuses the file.
    Green after: the refusal is back (the render raises), and the same deployment with the setting
    off loads."""
    row = _row(row_id)
    planted = validated[f"planted--{row_id}"]
    assert not planted.ok, f"the real Caddy loaded the clashing Caddyfile: {planted.said}"
    assert re.search(r"violate convention|multiplex|already|in use|cannot", planted.said), (
        planted.said
    )
    assert validated[f"off--{row_id}"].ok, validated[f"off--{row_id}"].said
    with pytest.raises(ValueError) as refused:
        _caddyfile(row, "ospreyflow")
    assert type(refused.value).__name__ == "PageServiceNeedsAnotherPort"


def test_the_pure_model_finds_the_same_clashes_as_the_real_caddy(
    validated: dict[str, Result],
) -> None:
    """The fast check agrees with the real one on every planted clash, and finds none in a Caddyfile
    the real one loads (never alone: this is the model, those are the measurement)."""
    for row_id in CLASH_ROWS:
        with mock.patch.object(page_addresses, "_port_taken", lambda *a, **k: None):
            text = _caddyfile(_row(row_id), "ospreyflow")
        assert clash_findings(text), row_id
        assert not validated[f"planted--{row_id}"].ok, row_id
    for row in DERIVED:
        assert clash_findings(_caddyfile(row, "ospreyflow")) == [], row["id"]


@pytest.mark.parametrize("row_id", POLICY_ROWS)
def test_a_refusal_that_is_the_owners_policy_is_not_mistaken_for_caddys(
    row_id: str, validated: dict[str, Result]
) -> None:
    """The render refuses these, for the owner's reasons (an HTTPS identity address does not belong
    on a plain-HTTP port in any shape; port 80 is published for the redirect). The test records what
    Caddy itself says of the Caddyfile the refusal stands in front of (printed above) and holds
    only the refusal: it names the setting and the port."""
    row = _row(row_id)
    with pytest.raises(ValueError) as refused:
        _caddyfile(row, "ospreyflow")
    assert "pages.enabled" in str(refused.value)
    assert row["config"]["origin"].rsplit(":", 1)[1] in str(refused.value)
    assert f"planted--{row_id}" in validated


def test_a_machine_with_no_caddy_fails_in_words_and_does_not_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rule 15 for the guard itself: where the image cannot be run and no binary is given, the test
    fails, saying why. Planted at the shape the helper sees: `docker` is not on the path and no
    `OSPREY_CADDY_BINARY` is set."""
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("OSPREY_CADDY_BINARY", raising=False)
    assert shutil.which("docker") is None
    with pytest.raises(AssertionError, match="the real Caddy cannot be run.*does not skip"):
        _validate_all({"a": "{\n}\n"}, tmp_path / "run")
