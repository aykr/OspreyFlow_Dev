"""The organisation's own certificate, checked before anything starts (`06_DECISIONS.md` ADR-114
Amendment 33 decision 3).

A Small on a server of your own serves the certificate and key `network.tls` names. A bad pair is
found here, in words, before a container is touched — not by a front proxy that never becomes
healthy after everything else has started. `ospreyflow doctor` and `install` run this module as a
step (the command itself depends on PyYAML alone); `harness.apply` calls `check_deployment` on every
install and every `apply`, and refuses with nothing changed.

Refused: a file that cannot be read or holds no PEM; a key encrypted with a passphrase (the proxy
cannot be given one); a key that does not match the certificate; a certificate expired or not yet
valid; one of the deployment's names (`<host>`, `id.<host>`, and `bi.<host>` when the dashboards
are on) not covered — a wildcard covers one label, so `*.example.internal` does not cover
`id.osprey.example.internal`; and, with `network.tls.ca`, a chain that does not reach that root.
Warned: fewer than 30 days left.

Subject alternative names alone are read, as browsers read them: a certificate's common name is not
a name it covers.

    python -m harness.tls_check --certificate /etc/ospreyflow/tls/osprey.crt \\
        --key /etc/ospreyflow/tls/osprey.key [--ca /etc/ospreyflow/tls/org-root.pem] \\
        --name osprey.example.internal --name id.osprey.example.internal
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import stat
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization

from schemas.deployment import OspreyConfig

#: Fewer days than this left is a warning, not a refusal.
WARN_DAYS = 30
_CHAIN_LIMIT = 10


@dataclass
class Report:
    refusals: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: The server certificate's SHA-256, in hex (what `apply` records to see a renewal).
    fingerprint: str | None = None

    @property
    def ok(self) -> bool:
        return not self.refusals


def _read(path: Path, what: str, report: Report) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError as error:
        report.refusals.append(
            f"the {what} {path} cannot be read ({error.strerror or error}): give a file the "
            "installing account can read"
        )
        return None


def covers(pattern: str, name: str) -> bool:
    """Whether a certificate's DNS name `pattern` covers `name` (RFC 6125 §6.4.3, as browsers apply
    it): equal, or a wildcard standing for exactly one whole leftmost label."""
    pattern, name = pattern.lower().rstrip("."), name.lower().rstrip(".")
    if pattern == name:
        return True
    if not pattern.startswith("*."):
        return False
    first, dot, rest = name.partition(".")
    return bool(first) and bool(dot) and rest == pattern[2:]


def _dns_names(cert: x509.Certificate) -> list[str]:
    try:
        extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except x509.ExtensionNotFound:
        return []
    return list(extension.value.get_values_for_type(x509.DNSName))


def _issued_by(child: x509.Certificate, parent: x509.Certificate) -> bool:
    if child.issuer != parent.subject:
        return False
    try:
        child.verify_directly_issued_by(parent)
    except (InvalidSignature, ValueError, TypeError, UnsupportedAlgorithm):
        return False
    return True


def _reaches(chain: list[x509.Certificate], anchors: list[x509.Certificate]) -> bool:
    """Whether `chain[0]` reaches one of `anchors` through the certificates after it."""
    current = chain[0]
    for _ in range(_CHAIN_LIMIT):
        if any(_issued_by(current, anchor) or current == anchor for anchor in anchors):
            return True
        parent = next((c for c in chain[1:] if c != current and _issued_by(current, c)), None)
        if parent is None:
            return False
        current = parent
    return False


def _when(moment: dt.datetime) -> str:
    return moment.strftime("%d %B %Y %H:%M UTC")


def check(
    certificate: Path,
    key: Path,
    names: Sequence[str],
    ca: Path | None = None,
    *,
    now: dt.datetime | None = None,
) -> Report:
    """Every refusal and warning for this certificate, key and set of names, in words."""
    now = now or dt.datetime.now(dt.UTC)
    report = Report()
    cert_bytes = _read(certificate, "certificate file", report)
    key_bytes = _read(key, "key file", report)
    chain: list[x509.Certificate] = []
    if cert_bytes is not None:
        try:
            chain = x509.load_pem_x509_certificates(cert_bytes)
        except ValueError:
            chain = []
        if not chain:
            report.refusals.append(
                f"{certificate} holds no PEM certificate (a block beginning -----BEGIN "
                "CERTIFICATE-----): give the server certificate, then its intermediates, in PEM"
            )
    private = None
    if key_bytes is not None:
        try:
            private = serialization.load_pem_private_key(key_bytes, password=None)
        except TypeError:
            report.refusals.append(
                f"the key {key} is encrypted with a passphrase, which the front proxy cannot be "
                "given: write it unencrypted (openssl pkey -in <encrypted file> -out "
                f"{key}), owned by the installing account, mode 600"
            )
        except (ValueError, UnsupportedAlgorithm):
            report.refusals.append(
                f"{key} holds no PEM private key (a block beginning -----BEGIN PRIVATE KEY----- or "
                "-----BEGIN RSA/EC PRIVATE KEY-----)"
            )
    if not chain:
        return report
    leaf = chain[0]
    report.fingerprint = hashlib.sha256(leaf.public_bytes(serialization.Encoding.DER)).hexdigest()

    if private is not None:
        given = private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        named = leaf.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        if given != named:
            report.refusals.append(
                f"the key {key} does not match the certificate {certificate} (it is the key of "
                "another certificate): give the key this certificate was issued for"
            )

    start, end = leaf.not_valid_before_utc, leaf.not_valid_after_utc
    if end <= now:
        report.refusals.append(
            f"the certificate expired on {_when(end)}: ask the organisation's CA for a new one, "
            "replace the two files, then run ospreyflow apply"
        )
    elif start > now:
        report.refusals.append(
            f"the certificate is not valid until {_when(start)}: wait until then, or check the "
            "server's clock is right"
        )
    elif end - now < dt.timedelta(days=WARN_DAYS):
        days = (end - now).days
        report.warnings.append(
            f"the certificate expires on {_when(end)}, in {days} days: renew it soon (replace the "
            "two files, then run ospreyflow apply)"
        )

    sans = _dns_names(leaf)
    missing = [n for n in names if not any(covers(p, n) for p in sans)]
    if missing:
        host = names[0] if names else "<host>"
        report.refusals.append(
            f"the certificate does not cover {', '.join(missing)}: it names "
            f"{', '.join(sans) if sans else 'no DNS names (its common name is not read)'}. A "
            "wildcard covers one label only, so *.example.internal does not cover "
            f"id.osprey.example.internal. Ask the CA for {', '.join(names)} — or {host} and "
            f"*.{host} — as subject alternative names"
        )

    if ca is not None:
        ca_bytes = _read(ca, "CA file", report)
        if ca_bytes is not None and not ca.stat().st_mode & stat.S_IROTH:
            # Keycloak mounts it into its truststore and runs as uid 1000, not the installing
            # account (as found on the first server, 4 November 2026). A root certificate is
            # public.
            mode = stat.S_IMODE(ca.stat().st_mode)
            report.refusals.append(
                f"{ca} is mode {mode:o}, so the identity provider, which reads it through its "
                "mount as another account, cannot: it is the organisation's "
                f"root certificate and holds no secret, so make it readable by every account "
                f"(chmod 644 {ca})"
            )
        anchors: list[x509.Certificate] = []
        if ca_bytes is not None:
            try:
                anchors = x509.load_pem_x509_certificates(ca_bytes)
            except ValueError:
                anchors = []
            if not anchors:
                report.refusals.append(f"{ca} holds no PEM certificate for the organisation's root")
        if anchors and not _reaches(chain, anchors):
            report.refusals.append(
                f"the certificate's chain does not reach the organisation's root in {ca}: put the "
                f"intermediate certificates after the server certificate in {certificate}, or "
                f"check that {ca} is the root that issued it"
            )
    return report


def names_of(config: OspreyConfig) -> list[str]:
    """The names the deployment answers at (`harness.site.sites`): the host, `id.`, and `bi.` when
    the dashboards are on."""
    from harness.site import sites

    host = sites(config).host
    found = [host, f"id.{host}"]
    if config.reporting.superset:
        found.append(f"bi.{host}")
    return found


def check_deployment(config: OspreyConfig, *, now: dt.datetime | None = None) -> Report:
    """`check` for `network.tls` and the deployment's own names. Nothing to check without it."""
    tls = config.network.tls
    if tls is None:
        return Report()
    return check(
        Path(tls.certificate),
        Path(tls.key),
        names_of(config),
        Path(tls.ca) if tls.ca else None,
        now=now,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness.tls_check", description=(__doc__ or "").split("\n\n")[0]
    )
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--ca", type=Path)
    parser.add_argument(
        "--name", action="append", default=[], required=True, help="a name it must cover"
    )
    args = parser.parse_args(argv)
    report = check(args.certificate, args.key, args.name, args.ca)
    for refusal in report.refusals:
        print(f"refused: {refusal}")
    for warning in report.warnings:
        print(f"warning: {warning}")
    if report.ok:
        print(
            f"ok: the certificate covers {', '.join(args.name)}; its SHA-256 fingerprint is "
            f"{report.fingerprint}"
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
