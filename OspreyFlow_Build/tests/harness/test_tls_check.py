"""`harness.tls_check`: the organisation's certificate, checked before anything starts (ADR-114
Amendment 33 decision 3) — by `ospreyflow doctor`, `install` and every `apply`.

Each refusal is in words and changes nothing. The certificates are made per test by a throwaway CA
(`tls_fixtures.py`); none is real and none is committed.

Rule 15: what the check must refuse is measured against the real dependencies, not assumed. Caddy
is the fixture for the key: `test_every_pair_caddy_refuses_the_check_refuses_too` gives the same
files to the pinned Caddy and to the check, and requires that every pair Caddy will not start with,
the check refuses too. A real TLS client (Python's `ssl`, OpenSSL's host matching) is the fixture
for the names: `test_a_wildcard_for_the_parent_domain_does_not_cover_id_and_is_refused` shows a real
client refusing `id.<host>` behind a parent-domain wildcard, which is why the check refuses it.

What a mistake would do, and the case that catches it:
- a proxy that never starts, found only after everything else has — the Caddy-paired case;
- `bi.` or `id.` uncovered, so sign-in or the dashboards fail in the browser —
  `test_a_certificate_missing_id_or_bi_is_refused_naming_it`;
- the one-level wildcard trap (the client briefing's "or one wildcard") —
  `test_a_wildcard_for_the_parent_domain_does_not_cover_id_and_is_refused`, with
  `test_a_wildcard_for_the_host_with_the_host_itself_is_accepted` for the shape that works;
- an expired, not-yet-valid or encrypted certificate let through —
  `test_an_expired_certificate_is_refused_naming_its_end`,
  `test_a_certificate_not_yet_valid_is_refused`, `test_an_encrypted_key_is_refused_in_words`;
- a chain the organisation's browsers will not trust — `test_a_chain_that_does_not_reach_the_given_ca_is_refused`;
- the organisation's CA unreadable by Keycloak, which mounts it —
  `test_a_ca_file_keycloak_cannot_read_is_refused_in_words`;
- a certificate near its end refused, so a deployment cannot be applied the week before renewal —
  `test_thirty_days_left_is_a_warning_not_a_refusal`.
"""

from __future__ import annotations

import datetime as dt
import socket
import ssl
from pathlib import Path

import pytest
from harness import tls_check
from harness.render import render
from schemas.deployment import OspreyConfig

from .tls_fixtures import (
    HOST,
    NAMES,
    NOW,
    Authority,
    Files,
    caddy,
    key_pem,
    pem,
    wait_until_healthy,
    wait_until_stopped,
    write_set,
)


def _check(files: Files, names: tuple[str, ...] = NAMES) -> tls_check.Report:
    return tls_check.check(files.certificate, files.key, names, files.ca)


def _caddyfile(files: Files) -> str:
    config = OspreyConfig.model_validate({
        "profile": "small",
        "network": {"public_origin": f"https://{HOST}",
                    "tls": {"certificate": str(files.certificate), "key": str(files.key)}},
        "reporting": {"sync": True, "superset": True},
    })  # fmt: skip
    return render(config, resolver=lambda _i: "sha256:" + "0" * 64).artefacts[
        "Caddyfile"
    ]


def test_a_good_certificate_passes_with_its_fingerprint(tmp_path: Path) -> None:
    files = write_set(tmp_path)
    report = _check(files)
    assert report.ok, report.refusals
    assert report.refusals == [] and report.warnings == []
    assert report.fingerprint is not None and len(report.fingerprint) == 64


def _garbage_key(folder: Path) -> Files:
    files = write_set(folder)
    files.key.write_text("this is not a key\n", encoding="utf-8")
    return files


def _not_a_certificate(folder: Path) -> Files:
    files = write_set(folder)
    files.certificate.write_text(
        "-----BEGIN NOTHING-----\nAAAA\n-----END NOTHING-----\n"
    )
    return files


@pytest.mark.parametrize(
    ("label", "make", "words"),
    [
        (
            "mismatched key",
            lambda f: write_set(f, mismatched_key=True),
            "does not match",
        ),
        ("encrypted key", lambda f: write_set(f, password=b"passphrase"), "encrypted"),
        ("not a key", _garbage_key, "no PEM private key"),
        ("not a certificate", _not_a_certificate, "no PEM certificate"),
    ],
)
def test_every_pair_caddy_refuses_the_check_refuses_too(
    tmp_path: Path, label: str, make: object, words: str
) -> None:
    """The same files to the real Caddy and to the check. Caddy refuses to start with each, so the
    check must refuse each — before Caddy is ever asked."""
    files = make(tmp_path / "tls")  # type: ignore[operator]
    with caddy(_caddyfile(files), files, tmp_path, user=None) as running:
        assert wait_until_stopped(running), (
            f"Caddy started with a {label}: the fixture is wrong"
        )
    report = _check(files)
    assert not report.ok, f"Caddy refuses a {label}; the check let it through"
    assert any(words in r for r in report.refusals), report.refusals
    # And the good pair, for contrast: Caddy starts with it and the check passes it.
    good = write_set(tmp_path / "good")
    with caddy(_caddyfile(good), good, tmp_path / "good", user=None) as running:
        assert wait_until_healthy(running), running.logs()[-1200:]
    assert _check(good).ok


@pytest.mark.parametrize("missing", [f"id.{HOST}", f"bi.{HOST}"])
def test_a_certificate_missing_id_or_bi_is_refused_naming_it(
    tmp_path: Path, missing: str
) -> None:
    files = write_set(tmp_path, names=tuple(n for n in NAMES if n != missing))
    report = _check(files)
    assert not report.ok
    said = " ".join(report.refusals)
    assert missing in said and "does not cover" in said
    # Without dashboards `bi.` is not one of the deployment's names, so it is not asked for.
    if missing.startswith("bi."):
        assert _check(files, names=NAMES[:2]).ok


def _client_accepts(port: int, name: str, ca: Path) -> bool:
    context = ssl.create_default_context(cafile=str(ca))
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
            with context.wrap_socket(raw, server_hostname=name):
                return True
    except ssl.SSLError:
        return False


def test_a_wildcard_for_the_parent_domain_does_not_cover_id_and_is_refused(
    tmp_path: Path,
) -> None:
    """`*.example.internal` covers `osprey.example.internal` but not `id.osprey.example.internal`
    (a wildcard is one label). Measured with a real client against the real Caddy first, then the
    check is required to agree."""
    files = write_set(tmp_path / "tls", names=("*.example.internal",))
    caddyfile = _caddyfile(files)
    with caddy(caddyfile, files, tmp_path, user=None) as running:
        assert wait_until_healthy(running), running.logs()[-1200:]
        assert running.https_port is not None
        assert _client_accepts(running.https_port, HOST, files.ca)
        assert not _client_accepts(running.https_port, f"id.{HOST}", files.ca)
    report = _check(files)
    assert not report.ok
    said = " ".join(report.refusals)
    assert f"id.{HOST}" in said and f"bi.{HOST}" in said and "one label" in said
    assert HOST not in said.split("does not cover", 1)[1].split(":", 1)[0].split(", ")


def test_a_wildcard_for_the_host_with_the_host_itself_is_accepted(
    tmp_path: Path,
) -> None:
    files = write_set(tmp_path, names=(HOST, f"*.{HOST}"))
    assert _check(files).ok
    # The wildcard alone does not cover the host itself.
    alone = write_set(tmp_path / "alone", names=(f"*.{HOST}",))
    report = _check(alone)
    assert not report.ok and HOST in " ".join(report.refusals)


def test_an_expired_certificate_is_refused_naming_its_end(tmp_path: Path) -> None:
    end = NOW - dt.timedelta(days=3)
    files = write_set(tmp_path, not_before=NOW - dt.timedelta(days=400), not_after=end)
    report = _check(files)
    assert not report.ok
    said = " ".join(report.refusals)
    assert "expired" in said and end.strftime("%d %B %Y") in said
    assert "ospreyflow apply" in said


def test_a_certificate_not_yet_valid_is_refused(tmp_path: Path) -> None:
    start = NOW + dt.timedelta(days=2)
    files = write_set(
        tmp_path, not_before=start, not_after=NOW + dt.timedelta(days=300)
    )
    report = _check(files)
    assert not report.ok
    said = " ".join(report.refusals)
    assert (
        "not valid until" in said
        and start.strftime("%d %B %Y") in said
        and "clock" in said
    )


def test_an_encrypted_key_is_refused_in_words(tmp_path: Path) -> None:
    files = write_set(tmp_path, password=b"a passphrase")
    report = _check(files)
    assert not report.ok
    said = " ".join(report.refusals)
    assert "encrypted with a passphrase" in said and "unencrypted" in said
    assert "a passphrase" not in said.replace("with a passphrase", "")


def test_a_chain_that_does_not_reach_the_given_ca_is_refused(tmp_path: Path) -> None:
    files = write_set(tmp_path)
    # Another organisation's root given as the CA.
    files.ca.write_bytes(pem(Authority.root("Another Root CA (test only)").cert))
    report = _check(files)
    assert not report.ok and "does not reach" in " ".join(report.refusals)
    # The right root, but the intermediate left out of the certificate file.
    right = Authority.root()
    issuing = right.intermediate()
    leaf, key = issuing.issue()
    folder = tmp_path / "no-intermediate"
    folder.mkdir()
    (folder / "osprey.crt").write_bytes(pem(leaf))
    (folder / "osprey.key").write_bytes(key_pem(key))
    (folder / "org-root.pem").write_bytes(pem(right.cert))
    lone = tls_check.check(
        folder / "osprey.crt", folder / "osprey.key", NAMES, folder / "org-root.pem"
    )
    assert not lone.ok and "intermediate" in " ".join(lone.refusals)
    # With no CA given, the chain is not checked.
    assert tls_check.check(folder / "osprey.crt", folder / "osprey.key", NAMES, None).ok


def test_a_ca_file_keycloak_cannot_read_is_refused_in_words(tmp_path: Path) -> None:
    """Keycloak mounts `network.tls.ca` into its truststore and runs as uid 1000, not the installing
    account, so it reads the file only through the "other" bits. Found on the first server (4
    November 2026, ADR-114 Amendment 33): under a strict umask Keycloak could not read what the
    install wrote; a CA left `600` fails the same way, so the check refuses it before anything
    starts. The key is different: the proxy runs as its owner, so `600` is right for it."""
    files = write_set(tmp_path)
    assert _check(files).ok
    for mode in (0o600, 0o640):
        files.ca.chmod(mode)
        refusals = " ".join(_check(files).refusals)
        assert f"{files.ca} is mode {mode:o}" in refusals and f"chmod 644 {files.ca}" in refusals
    files.ca.chmod(0o444)
    assert _check(files).ok


def test_thirty_days_left_is_a_warning_not_a_refusal(tmp_path: Path) -> None:
    files = write_set(tmp_path, not_after=NOW + dt.timedelta(days=20))
    report = _check(files)
    assert report.ok
    assert len(report.warnings) == 1
    assert any(days in report.warnings[0] for days in ("19 days", "20 days")), (
        report.warnings
    )
    roomy = write_set(tmp_path / "roomy", not_after=NOW + dt.timedelta(days=45))
    assert _check(roomy).warnings == []


def test_an_unreadable_file_is_refused_naming_it(tmp_path: Path) -> None:
    files = write_set(tmp_path)
    report = tls_check.check(tmp_path / "missing.crt", files.key, NAMES, None)
    assert not report.ok and "missing.crt" in " ".join(report.refusals)


def test_the_deployments_names_follow_its_address_and_dashboards(
    tmp_path: Path,
) -> None:
    files = write_set(tmp_path)
    base = {"profile": "small", "network": {"public_origin": f"https://{HOST}",
            "tls": {"certificate": str(files.certificate), "key": str(files.key)}}}  # fmt: skip
    on = OspreyConfig.model_validate(
        {**base, "reporting": {"sync": True, "superset": True}}
    )
    off = OspreyConfig.model_validate(
        {**base, "reporting": {"sync": False, "superset": False}}
    )
    assert tls_check.names_of(on) == list(NAMES)
    assert tls_check.names_of(off) == list(NAMES[:2])
    assert tls_check.check_deployment(on).ok


def test_the_command_line_says_each_refusal_and_exits_non_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = write_set(tmp_path, names=(HOST,), mismatched_key=True)
    argv = ["--certificate", str(files.certificate), "--key", str(files.key), "--ca", str(files.ca),
            *(a for n in NAMES for a in ("--name", n))]  # fmt: skip
    assert tls_check.main(argv) == 1
    out = capsys.readouterr().out
    assert "does not match" in out and "does not cover" in out
    good = write_set(tmp_path / "good")
    argv = ["--certificate", str(good.certificate), "--key", str(good.key), "--ca", str(good.ca),
            *(a for n in NAMES for a in ("--name", n))]  # fmt: skip
    assert tls_check.main(argv) == 0
    assert "fingerprint" in capsys.readouterr().out
