"""A throwaway certificate authority for the organisation's-own-certificate tests (ADR-114
Amendment 33 decision 3), and the real Caddy those tests run against.

Every key and certificate here is made per test, in a temporary folder, by `cryptography`; none is
committed and none is real (Amendment 33's tests: "the test CA, certificates and keys are generated
per test in a temporary folder"). The shapes are the ones an organisation's CA hands over: a root,
an intermediate, and a server certificate naming its names as subject alternative names, written
leaf first and then the intermediate, as `network.tls.certificate` takes it.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import time
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtendedKeyUsageOID, NameOID
from harness.site import PROXY_IMAGE

NOW = dt.datetime.now(dt.UTC)
HOST = "osprey.example.internal"
NAMES = (HOST, f"id.{HOST}", f"bi.{HOST}")


def _name(common: str) -> x509.Name:
    return x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Example Organisation (test only)"),
        x509.NameAttribute(NameOID.COMMON_NAME, common),
    ])  # fmt: skip


def _key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


@dataclass
class Authority:
    """A root, or an intermediate signed by one."""

    key: ec.EllipticCurvePrivateKey
    cert: x509.Certificate

    @classmethod
    def root(cls, common: str = "Example Root CA (test only)") -> Authority:
        key = _key()
        name = _name(common)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(NOW - dt.timedelta(days=30))
            .not_valid_after(NOW + dt.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )  # fmt: skip
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .sign(key, hashes.SHA256())
        )
        return cls(key, cert)

    def intermediate(self, common: str = "Example Issuing CA (test only)") -> Authority:
        key = _key()
        cert = (
            x509.CertificateBuilder()
            .subject_name(_name(common))
            .issuer_name(self.cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(NOW - dt.timedelta(days=30))
            .not_valid_after(NOW + dt.timedelta(days=1825))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )  # fmt: skip
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), False
            )
            .sign(self.key, hashes.SHA256())
        )
        return Authority(key, cert)

    def issue(
        self,
        names: Sequence[str] = NAMES,
        *,
        not_before: dt.datetime | None = None,
        not_after: dt.datetime | None = None,
        ocsp: str | None = None,
        key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey | None = None,
    ) -> tuple[x509.Certificate, ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey]:
        """A server certificate for `names` (subject alternative names; the first is the subject's
        common name too), and its key."""
        leaf_key = key or _key()
        builder = (
            x509.CertificateBuilder()
            .subject_name(_name(names[0] if names else "no-names"))
            .issuer_name(self.cert.subject)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(not_before or NOW - dt.timedelta(days=1))
            .not_valid_after(not_after or NOW + dt.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(self.key.public_key()), False
            )
        )
        if names:
            builder = builder.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(n) for n in names]), critical=False
            )
        if ocsp:
            builder = builder.add_extension(
                x509.AuthorityInformationAccess([
                    x509.AccessDescription(
                        AuthorityInformationAccessOID.OCSP, x509.UniformResourceIdentifier(ocsp)
                    )
                ]),
                critical=False,
            )  # fmt: skip
        return builder.sign(self.key, hashes.SHA256()), leaf_key


def pem(*certs: x509.Certificate) -> bytes:
    return b"".join(c.public_bytes(serialization.Encoding.PEM) for c in certs)


def key_pem(
    key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey, password: bytes | None = None
) -> bytes:
    encryption: serialization.KeySerializationEncryption = (
        serialization.BestAvailableEncryption(password)
        if password
        else serialization.NoEncryption()
    )
    return key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, encryption
    )


@dataclass
class Files:
    certificate: Path
    key: Path
    ca: Path


def write_set(
    folder: Path,
    *,
    names: Sequence[str] = NAMES,
    not_before: dt.datetime | None = None,
    not_after: dt.datetime | None = None,
    ocsp: str | None = None,
    password: bytes | None = None,
    mismatched_key: bool = False,
    root: Authority | None = None,
) -> Files:
    """A root, an intermediate and a server certificate under `folder`: `osprey.crt` (the leaf then
    the intermediate), `osprey.key` (mode 600) and `org-root.pem`."""
    folder.mkdir(parents=True, exist_ok=True)
    root = root or Authority.root()
    issuing = root.intermediate()
    leaf, key = issuing.issue(names, not_before=not_before, not_after=not_after, ocsp=ocsp)
    if mismatched_key:
        key = _key()
    files = Files(folder / "osprey.crt", folder / "osprey.key", folder / "org-root.pem")
    files.certificate.write_bytes(pem(leaf, issuing.cert))
    files.key.write_bytes(key_pem(key, password))
    files.key.chmod(0o600)
    files.ca.write_bytes(pem(root.cert))
    return files


# ---- the real Caddy ------------------------------------------------------------------------------


def docker(*args: str, check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    done = subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if check:
        assert done.returncode == 0, done.stderr or done.stdout
    return done


@dataclass
class RunningCaddy:
    name: str
    #: The host port published for the container's 8443, on 127.0.0.1 (None on an internal network).
    https_port: int | None

    def logs(self) -> str:
        done = docker("logs", self.name, check=False)
        return done.stdout + done.stderr

    def running(self) -> bool:
        done = docker("inspect", "-f", "{{.State.Running}}", self.name, check=False)
        return done.stdout.strip() == "true"


@contextmanager
def caddy(
    caddyfile: str,
    files: Files,
    folder: Path,
    *,
    user: str | None = None,
    network: str | None = None,
    publish: bool = True,
    loopback_names: Sequence[str] = (),
) -> Iterator[RunningCaddy]:
    """The pinned Caddy with `caddyfile`, the certificate and key mounted read-only where the
    rendered compose file mounts them (`/certs/cert.pem`, `/certs/key.pem`), its 8443 published on
    a free port of 127.0.0.1 — never 80 or 443 of this machine."""
    path = folder / "Caddyfile"
    path.write_text(caddyfile, encoding="utf-8")
    name = f"osprey-test-tls-{uuid.uuid4().hex[:8]}"
    argv = ["run", "-d", "--name", name,
            "-v", f"{path}:/etc/caddy/Caddyfile:ro",
            "-v", f"{files.certificate}:/certs/cert.pem:ro",
            "-v", f"{files.key}:/certs/key.pem:ro",
            "--env", "XDG_DATA_HOME=/tmp/caddy", "--env", "XDG_CONFIG_HOME=/tmp/caddy"]  # fmt: skip
    if user:
        argv += ["--user", user]
    for host in loopback_names:
        argv += ["--add-host", f"{host}:127.0.0.1"]
    if network:
        argv += ["--network", network]
    if publish and not network:
        argv += ["-p", "127.0.0.1::8443"]
    docker(*argv, PROXY_IMAGE)
    try:
        port: int | None = None
        if publish and not network:
            # A Caddy that refused its configuration has already exited, and has no port.
            mapped = docker("port", name, "8443/tcp", check=False).stdout.strip().splitlines()
            port = int(mapped[0].rsplit(":", 1)[1]) if mapped else None
        yield RunningCaddy(name, port)
    finally:
        docker("rm", "-f", name, check=False)


def wait_until_healthy(running: RunningCaddy, seconds: int = 30) -> bool:
    """Caddy's own health answer, asked inside its container as the compose file asks it."""
    for _ in range(seconds):
        if not running.running():
            return False
        done = docker(
            "exec", running.name, "wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz",
            check=False,
        )  # fmt: skip
        if done.returncode == 0:
            return True
        time.sleep(1)
    return False


def wait_until_stopped(running: RunningCaddy, seconds: int = 20) -> bool:
    for _ in range(seconds):
        if not running.running():
            return True
        time.sleep(1)
    return False
