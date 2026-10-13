"""ADR-114 Amendment 6 point 1, Amendment 8 point 5: every owned image of a release is checked with
cosign before anything changes — keyless, against the user repository's release workflow at that
tag — and one failure refuses the whole release, naming each image.

The cosign here is a fake that refuses as cosign does (exit 1, "no matching signatures") for any
image it was not told is signed; the real cosign is exercised by the live proof (`07_BUILD_PLAN.md`,
the B5c row), against a throwaway registry and key.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest
from harness.signatures import (
    COSIGN_IMAGE,
    GITHUB_ISSUER,
    Cosign,
    Keyless,
    PublicKey,
    SignatureRefused,
    main,
    owned_references,
    verify_release,
)

D = "sha256:" + "a" * 64
E = "sha256:" + "b" * 64


def _lock(**digests: str) -> str:
    rows = []
    for service, digest in digests.items():
        repository = f"ghcr.io/acme/{service}" if service != "arcadedb" else "arcadedata/arcadedb"
        rows.append(
            f"- service: {service}\n  repository: {repository}\n  tag: x\n  digest: {digest}\n"
            "  source: registry\n"
        )
    return "# GENERATED\nimages:\n" + "".join(rows)


class _FakeCosign:
    """Answers `verify` as cosign does: 0 for an image it holds a signature for, else 1."""

    def __init__(self, signed: set[str]) -> None:
        self.signed = signed
        self.asked: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> tuple[int, str]:
        self.asked.append(list(argv))
        ref = argv[-1]
        if ref in self.signed:
            return 0, "Verification for ... -- The following checks were performed"
        return 1, f"Error: no matching signatures: {ref}"


def test_keyless_names_the_user_repositorys_release_workflow_at_that_tag() -> None:
    assert Keyless("acme", "ospreyflow", "v0.5.0").arguments() == [
        "--certificate-identity",
        "https://github.com/acme/ospreyflow/.github/workflows/release.yml@refs/tags/v0.5.0",
        "--certificate-oidc-issuer", GITHUB_ISSUER,
    ]  # fmt: skip
    assert GITHUB_ISSUER == "https://token.actions.githubusercontent.com"


def test_only_the_owned_images_are_checked_and_each_by_digest() -> None:
    lock = _lock(workspace=D, api=E, ingest=D, ner=E, arcadedb=D)
    assert owned_references(lock) == [
        f"ghcr.io/acme/workspace@{D}", f"ghcr.io/acme/api@{E}",
        f"ghcr.io/acme/ingest@{D}", f"ghcr.io/acme/ner@{E}",
    ]  # fmt: skip


@pytest.mark.parametrize("digest", ["local-build", "unresolved", "sha256:short"])
def test_an_owned_image_without_a_real_digest_is_refused_by_name(digest: str) -> None:
    with pytest.raises(SignatureRefused, match="api has no digest"):
        owned_references(_lock(workspace=D, api=digest, ingest=D, ner=D))


def test_a_lock_missing_an_owned_image_is_refused() -> None:
    with pytest.raises(SignatureRefused, match="ner"):
        owned_references(_lock(workspace=D, api=D, ingest=D))


def test_every_image_is_checked_and_every_failure_named_not_only_the_first() -> None:
    lock = _lock(workspace=D, api=E, ingest=D, ner=E)
    cosign = _FakeCosign({f"ghcr.io/acme/workspace@{D}", f"ghcr.io/acme/ingest@{D}"})
    with pytest.raises(SignatureRefused) as refused:
        verify_release(lock, Keyless("acme", "ospreyflow", "v0.5.0"), Cosign(cosign))
    said = str(refused.value)
    assert f"ghcr.io/acme/api@{E}" in said and f"ghcr.io/acme/ner@{E}" in said
    assert "workspace" not in said
    assert len(cosign.asked) == 4


def test_a_release_whose_images_are_all_signed_passes() -> None:
    lock = _lock(workspace=D, api=E, ingest=D, ner=E)
    refs = set(owned_references(lock))
    verify_release(lock, Keyless("acme", "ospreyflow", "v0.5.0"), Cosign(_FakeCosign(refs)))


def test_cosign_runs_from_its_pinned_image_with_a_key_mounted_read_only(tmp_path: Path) -> None:
    key = tmp_path / "keys" / "cosign.pub"
    argv = Cosign.docker_argv(f"ghcr.io/acme/api@{D}", PublicKey(key))
    assert argv[:3] == ["docker", "run", "--rm"]
    assert f"{key.parent}:/keys:ro" in argv
    assert COSIGN_IMAGE in argv
    tail = argv[argv.index(COSIGN_IMAGE) + 1 :]
    assert tail == ["verify", "--key", "/keys/cosign.pub", "--insecure-ignore-tlog=true",
                    f"ghcr.io/acme/api@{D}"]  # fmt: skip


def test_keyless_never_skips_the_transparency_log() -> None:
    argv = Cosign.docker_argv(f"ghcr.io/acme/api@{D}", Keyless("acme", "o", "v1.0.0"))
    assert not any("insecure" in a for a in argv)


def test_the_command_line_says_the_answer_and_exits_non_zero_on_a_refusal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = tmp_path / "versions.lock"
    lock.write_text(_lock(workspace=D, api=E, ingest=D, ner=E))
    unsigned = _FakeCosign(set())
    assert main(["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0"],
                cosign=Cosign(unsigned)) == 1  # fmt: skip
    assert "not signed by acme/ospreyflow's release workflow" in capsys.readouterr().err
    signed = _FakeCosign(set(owned_references(lock.read_text())))
    assert main(["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0"],
                cosign=Cosign(signed)) == 0  # fmt: skip
