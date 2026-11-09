"""A synthetic certificate authority and server certificates for the connectors' TLS cases
(`06_DECISIONS.md` ADR-140 Amendment 15): made fresh for each test, valid for an hour, never
written anywhere but the test's own temporary folder. Used by `test_api_tls.py` (offline) and
`test_sql_connector_live.py`'s `verify-full` cases (live)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def issue(subject: str, key: Any, issuer: x509.Name, signer: Any, *, ca: bool) -> x509.Certificate:
    """A certificate for `subject` (a CA's, or a server's naming `subject` as its one DNS name)."""
    now = datetime.now().astimezone()
    built = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if ca:
        built = built.add_extension(
            x509.KeyUsage(digital_signature=True, key_cert_sign=True, crl_sign=True,
                          content_commitment=False, key_encipherment=False,
                          data_encipherment=False, key_agreement=False, encipher_only=False,
                          decipher_only=False),  # fmt: skip
            critical=True,
        ).add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
    else:
        built = (
            built.add_extension(
                x509.SubjectAlternativeName([x509.DNSName(subject)]), critical=False
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(signer.public_key()),
                critical=False,
            )
        )
    return built.sign(signer, hashes.SHA256())


@dataclass
class Ca:
    pem: str
    key: Any
    name: x509.Name

    def server(self, name: str) -> tuple[bytes, bytes]:
        """A server certificate this CA signed for `name`, and its key, both in PEM."""
        key = ec.generate_private_key(ec.SECP256R1())
        cert = issue(name, key, self.name, self.key, ca=False)
        key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())  # fmt: skip
        return cert.public_bytes(serialization.Encoding.PEM), key_pem


def make_ca() -> Ca:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "OspreyFlow fixture CA")])
    cert = issue("OspreyFlow fixture CA", key, name, key, ca=True)
    return Ca(pem=cert.public_bytes(serialization.Encoding.PEM).decode(), key=key, name=name)
