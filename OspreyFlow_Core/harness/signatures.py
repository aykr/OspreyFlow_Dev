"""A release's owned images checked with cosign before anything changes (ADR-114 Amendment 6 point
1, Amendment 8 point 5).

Keyless: each image must carry a signature made by the user repository's `release.yml` running for
that tag, issued through GitHub's OIDC — the identity is the workflow, so no key exists to lose. One
image that does not verify refuses the whole release, and every failure is named. Third-party images
are pinned by digest in the lock and not signature-checked: their publishers do not sign to one
identity this deployment could name.

cosign (Apache-2.0) runs from its pinned image on the host, as OpenTofu does; in the release
workflow, as the binary the workflow installs (`--cosign cosign`).

    python -m harness.signatures --lock versions.lock --repository acme/ospreyflow --tag v0.5.0
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

COSIGN_IMAGE = "ghcr.io/sigstore/cosign/cosign:v2.4.1"
GITHUB_ISSUER = "https://token.actions.githubusercontent.com"
#: The images this repository builds; every other image in a lock is a third party's.
OWNED_SERVICES = ("workspace", "api", "ingest", "ner")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")

Run = Callable[[Sequence[str]], tuple[int, str]]


class SignatureRefused(Exception):
    """A release that may not be applied, and why."""


@dataclass(frozen=True)
class Keyless:
    """Signed by `owner/repo`'s release workflow for `tag`, through GitHub's OIDC."""

    owner: str
    repo: str
    tag: str

    def arguments(self, *, mounted: bool = True) -> list[str]:
        del mounted
        workflow = f"https://github.com/{self.owner}/{self.repo}/.github/workflows/release.yml"
        return [
            "--certificate-identity", f"{workflow}@refs/tags/{self.tag}",
            "--certificate-oidc-issuer", GITHUB_ISSUER,
        ]  # fmt: skip

    def describe(self) -> str:
        return f"{self.owner}/{self.repo}'s release workflow for {self.tag}"


@dataclass(frozen=True)
class PublicKey:
    """Signed with a key pair's private half. Only a test sets this (Amendment 8 point 9): its
    signatures are never uploaded to the public transparency log, so the log is not consulted."""

    path: Path

    def arguments(self, *, mounted: bool = True) -> list[str]:
        key = f"/keys/{self.path.name}" if mounted else str(self.path)
        return ["--key", key, "--insecure-ignore-tlog=true"]

    def describe(self) -> str:
        return f"the key {self.path.name}"


Identity = Keyless | PublicKey


def _subprocess_run(argv: Sequence[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(list(argv), capture_output=True, text=True, timeout=300, check=False)
    except (OSError, subprocess.SubprocessError) as failed:
        return 1, str(failed)
    return done.returncode, (done.stdout + done.stderr).strip()


class Cosign:
    """`cosign verify`, from its image (the default) or a binary (`binary`)."""

    def __init__(
        self, run: Run = _subprocess_run, *, binary: str | None = None,
        docker_args: Sequence[str] = (),
    ) -> None:  # fmt: skip
        self._run = run
        self._binary = binary
        self._docker_args = tuple(docker_args)

    @staticmethod
    def docker_argv(ref: str, identity: Identity, docker_args: Sequence[str] = ()) -> list[str]:
        mounts = (
            ["-v", f"{identity.path.parent}:/keys:ro"] if isinstance(identity, PublicKey) else []
        )
        return [
            "docker", "run", "--rm", *mounts, *docker_args, COSIGN_IMAGE,
            "verify", *identity.arguments(mounted=True), ref,
        ]  # fmt: skip

    def verify(self, ref: str, identity: Identity) -> tuple[bool, str]:
        if self._binary is not None:
            argv = [self._binary, "verify", *identity.arguments(mounted=False), ref]
        else:
            argv = self.docker_argv(ref, identity, self._docker_args)
        code, said = self._run(argv)
        return code == 0, said

    @staticmethod
    def _keys(identity: Identity) -> list[str]:
        return ["-v", f"{identity.path.parent}:/keys:ro"] if isinstance(identity, PublicKey) else []

    @staticmethod
    def docker_argv_local(saved: Path, identity: Identity) -> list[str]:
        """An image as `cosign save` kept it, verified with no network at all (`update --from`)."""
        return [
            "docker", "run", "--rm", "--network", "none", *Cosign._keys(identity),
            "-v", f"{saved.parent}:/saved:ro", COSIGN_IMAGE,
            "verify", *identity.arguments(mounted=True), "--offline",
            "--local-image", f"/saved/{saved.name}",
        ]  # fmt: skip

    def verify_local(self, saved: Path, identity: Identity) -> tuple[bool, str]:
        if self._binary is not None:
            argv = [self._binary, "verify", *identity.arguments(mounted=False), "--offline",
                    "--local-image", str(saved)]  # fmt: skip
        else:
            argv = self.docker_argv_local(saved, identity)
        code, said = self._run(argv)
        return code == 0, said

    def save(self, ref: str, dest: Path) -> tuple[bool, str]:
        """The image and its signatures as an OCI layout in `dest` (`cosign save`), for a bundle."""
        if self._binary is not None:
            argv = [self._binary, "save", "--dir", str(dest), ref]
        else:
            argv = [
                "docker", "run", "--rm", *self._docker_args, "-v", f"{dest.parent}:/out",
                COSIGN_IMAGE, "save", "--dir", f"/out/{dest.name}", ref,
            ]  # fmt: skip
        code, said = self._run(argv)
        return code == 0, said

    def verify_blob(
        self, blob: Path, signature: Path, identity: Identity, *, offline: bool = False
    ) -> None:
        """The release's `versions.lock` against its `cosign sign-blob` bundle (Amendment 8 point
        11); refuses in words. The two files must sit in one folder."""
        if self._binary is not None:
            argv = [
                self._binary, "verify-blob", *identity.arguments(mounted=False),
                *(["--offline"] if offline else []), "--bundle", str(signature), str(blob),
            ]  # fmt: skip
        else:
            network = ["--network", "none"] if offline else list(self._docker_args)
            argv = [
                "docker", "run", "--rm", *network, *self._keys(identity),
                "-v", f"{blob.parent}:/blob:ro", COSIGN_IMAGE,
                "verify-blob", *identity.arguments(mounted=True),
                *(["--offline"] if offline else []),
                "--bundle", f"/blob/{signature.name}", f"/blob/{blob.name}",
            ]  # fmt: skip
        code, said = self._run(argv)
        if code != 0:
            last = said.splitlines()[-1] if said else "no answer"
            raise SignatureRefused(
                f"the release's {blob.name} is not signed by {identity.describe()} ({last})"
            )


def owned_references(lock_text: str) -> list[str]:
    """`repository@digest` of each owned image in a lock, in the lock's order. An owned image with
    no real digest, or one missing, refuses the release."""
    entries = (yaml.safe_load(lock_text) or {}).get("images") or []
    by_service = {e.get("service"): e for e in entries if isinstance(e, dict)}
    missing = [s for s in OWNED_SERVICES if s not in by_service]
    if missing:
        raise SignatureRefused(f"the release's lock names no image for {', '.join(missing)}")
    refs = []
    for entry in entries:
        service = entry.get("service")
        if service not in OWNED_SERVICES:
            continue
        digest = str(entry.get("digest"))
        if not _DIGEST.match(digest):
            raise SignatureRefused(
                f"{service} has no digest in the release's lock ({digest}); it cannot be checked"
            )
        refs.append(f"{entry['repository']}@{digest}")
    return refs


def verify_release(lock_text: str, identity: Identity, cosign: Cosign) -> None:
    """Every owned image checked; refuses naming every one that does not verify."""
    failed = []
    for ref in owned_references(lock_text):
        ok, said = cosign.verify(ref, identity)
        if not ok:
            failed.append(f"{ref} ({said.splitlines()[-1] if said else 'no answer'})")
    if failed:
        raise SignatureRefused(f"not signed by {identity.describe()}: " + "; ".join(failed))


def verify_artifacts(refs: Sequence[str], identity: Identity, cosign: Cosign) -> None:
    """An OCI artifact of the release (the chart, ADR-114 Amendment 17) checked by digest as an
    owned image is; refuses naming every one that does not verify."""
    failed = []
    for ref in refs:
        ok, said = cosign.verify(ref, identity)
        if not ok:
            failed.append(f"{ref} ({said.splitlines()[-1] if said else 'no answer'})")
    if failed:
        raise SignatureRefused(f"not signed by {identity.describe()}: " + "; ".join(failed))


def main(argv: Sequence[str] | None = None, *, cosign: Cosign | None = None) -> int:
    parser = argparse.ArgumentParser(prog="signatures", description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--repository", required=True, help="owner/repo of the user repository")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--cosign", help="a cosign binary, instead of its image")
    parser.add_argument("--lock-signature", type=Path, help="the lock's cosign sign-blob bundle")
    parser.add_argument(
        "--blob", type=Path, action="append", default=[],
        help="another signed file of the release (repeatable)",
    )  # fmt: skip
    parser.add_argument(
        "--blob-signature", type=Path, action="append", default=[],
        help="each --blob's sign-blob bundle, in the same order",
    )  # fmt: skip
    parser.add_argument(
        "--artifact", action="append", default=[],
        help="an OCI artifact of the release by digest, the chart among them (repeatable)",
    )  # fmt: skip
    args = parser.parse_args(argv)
    if len(args.blob) != len(args.blob_signature):
        parser.error("each --blob is given with its --blob-signature")
    owner, _, repo = args.repository.partition("/")
    checker = cosign or Cosign(binary=args.cosign)
    try:
        if args.lock_signature is not None:
            checker.verify_blob(args.lock, args.lock_signature, Keyless(owner, repo, args.tag))
        # ADR-114 Amendments 11 and 17: the install page and the chart, as an install checks them.
        for blob, signature in zip(args.blob, args.blob_signature, strict=True):
            checker.verify_blob(blob, signature, Keyless(owner, repo, args.tag))
        verify_release(
            args.lock.read_text(encoding="utf-8"), Keyless(owner, repo, args.tag), checker
        )
        verify_artifacts(args.artifact, Keyless(owner, repo, args.tag), checker)
    except (SignatureRefused, OSError) as refused:
        print(f"signatures: {refused}", file=sys.stderr)
        return 1
    print(f"signatures: every owned image is signed by {args.repository}'s release workflow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
