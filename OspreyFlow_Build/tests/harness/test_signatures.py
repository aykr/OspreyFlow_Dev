"""ADR-114 Amendment 6 point 1, Amendment 8 point 5: every owned image of a release is checked with
cosign before anything changes — keyless, against the user repository's release workflow at that
tag — and one failure refuses the whole release, naming each image.

The cosign here is a fake that refuses as cosign does (exit 1, "no matching signatures") for any
image it was not told is signed; the real cosign is exercised by the live proof (`07_BUILD_PLAN.md`,
the B5c row), against a throwaway registry and key.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
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


# --- the lock's own signature, and offline verification (Amendment 8 points 10 and 11) ----------


def test_the_lock_is_verified_as_a_blob_against_the_same_identity(tmp_path: Path) -> None:
    lock, signature = tmp_path / "versions.lock", tmp_path / "versions.lock.sigstore.json"
    lock.write_text("images: []\n")
    signature.write_text("{}")
    asked: list[list[str]] = []

    def cosign(argv: Sequence[str]) -> tuple[int, str]:
        asked.append(list(argv))
        return 0, "Verified OK"

    Cosign(cosign).verify_blob(lock, signature, Keyless("acme", "ospreyflow", "v0.5.0"))
    argv = asked[0]
    assert argv[argv.index(COSIGN_IMAGE) + 1] == "verify-blob"
    assert f"{tmp_path}:/blob:ro" in argv
    assert argv[-3:] == ["--bundle", "/blob/versions.lock.sigstore.json", "/blob/versions.lock"]
    workflow = "https://github.com/acme/ospreyflow/.github/workflows/release.yml"
    assert f"{workflow}@refs/tags/v0.5.0" in argv


def test_a_lock_whose_signature_does_not_verify_is_refused(tmp_path: Path) -> None:
    lock, signature = tmp_path / "versions.lock", tmp_path / "versions.lock.sigstore.json"
    lock.write_text("images: [evil]\n")
    signature.write_text("{}")
    refusing = Cosign(lambda argv: (1, "invalid signature when validating ASN.1 encoded signature"))
    with pytest.raises(SignatureRefused, match="the release's versions.lock is not signed by"):
        refusing.verify_blob(lock, signature, Keyless("acme", "ospreyflow", "v0.5.0"))


def test_offline_verification_never_reaches_out_and_reads_a_saved_image(tmp_path: Path) -> None:
    """`update --from`: each image as `cosign save` kept it, verified with no network at all."""
    saved = tmp_path / "signed" / "api"
    argv = Cosign.docker_argv_local(saved, PublicKey(tmp_path / "keys" / "cosign.pub"))
    assert ["--network", "none"] == argv[3:5]
    assert f"{saved.parent}:/saved:ro" in argv
    tail = argv[argv.index(COSIGN_IMAGE) + 1 :]
    assert tail[0] == "verify" and "--offline" in tail
    assert tail[-2:] == ["--local-image", "/saved/api"]


def test_a_blob_check_offline_never_reaches_out(tmp_path: Path) -> None:
    lock = tmp_path / "versions.lock"
    asked: list[list[str]] = []
    Cosign(lambda argv: (asked.append(list(argv)) or (0, "ok"))).verify_blob(
        lock, tmp_path / "s.json", Keyless("a", "b", "v1.0.0"), offline=True
    )
    assert asked[0][3:5] == ["--network", "none"] and "--offline" in asked[0]


def test_the_command_line_also_checks_the_locks_own_signature(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lock = tmp_path / "versions.lock"
    lock.write_text(_lock(workspace=D, api=E, ingest=D, ner=E))
    (tmp_path / "versions.lock.sigstore.json").write_text("{}")
    signed = set(owned_references(lock.read_text()))

    def cosign(argv: Sequence[str]) -> tuple[int, str]:
        if "verify-blob" in argv:
            return 1, "invalid signature when validating ASN.1 encoded signature"
        return (0, "ok") if argv[-1] in signed else (1, "no signatures found")

    argv = ["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0",
            "--lock-signature", str(tmp_path / "versions.lock.sigstore.json")]  # fmt: skip
    assert main(argv, cosign=Cosign(cosign)) == 1
    assert "versions.lock is not signed" in capsys.readouterr().err



def test_another_signed_file_of_the_release_is_checked_too(tmp_path: Path) -> None:
    """ADR-114 Amendment 11: the release's install page is verified, as an install will verify it,
    before the release is published."""
    lock = tmp_path / "versions.lock"
    lock.write_text(_lock(workspace=D, api=E, ingest=D, ner=E))
    page, bundle = tmp_path / "install-page.tar.gz", tmp_path / "install-page.tar.gz.sigstore.json"
    page.write_bytes(b"page")
    bundle.write_text("{}")
    refs = set(owned_references(lock.read_text()))
    asked: list[list[str]] = []

    def run(page_signed: bool) -> Any:
        def answer(argv: Sequence[str]) -> tuple[int, str]:
            asked.append(list(argv))
            if "verify-blob" in argv and any(a.endswith(page.name) for a in argv):
                return (0, "Verified OK") if page_signed else (1, "no matching signatures")
            return (0, "ok") if any(r in argv for r in refs) or "verify-blob" in argv else (1, "x")
        return answer

    common = ["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0",
              "--blob", str(page), "--blob-signature", str(bundle)]  # fmt: skip
    assert main(common, cosign=Cosign(run(True))) == 0
    assert any("verify-blob" in a and any(x.endswith(page.name) for x in a) for a in asked)
    assert main(common, cosign=Cosign(run(False))) == 1


CHART_REF = "ghcr.io/acme/charts/ospreyflow@" + D


def test_every_signed_file_of_the_release_is_checked_not_only_the_first(tmp_path: Path) -> None:
    """ADR-114 Amendment 17: the release carries the install page and the chart, each with its
    bundle; each is verified before the release is published, and an unsigned one refuses it."""
    lock = tmp_path / "versions.lock"
    lock.write_text(_lock(workspace=D, api=E, ingest=D, ner=E))
    files = {name: tmp_path / name for name in ("install-page.tar.gz", "ospreyflow-0.5.0.tgz")}
    for path in files.values():
        path.write_bytes(b"x")
        (tmp_path / f"{path.name}.sigstore.json").write_text("{}")
    refs = set(owned_references(lock.read_text()))

    def run(unsigned: str | None) -> Any:
        def answer(argv: Sequence[str]) -> tuple[int, str]:
            if "verify-blob" in argv:
                return (1, "no matching signatures") if any(
                    unsigned and a.endswith(unsigned) for a in argv) else (0, "Verified OK")  # fmt: skip
            return (0, "ok") if any(r in argv for r in refs) else (1, "x")
        return answer

    args = ["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0"]
    for path in files.values():
        args += ["--blob", str(path), "--blob-signature", str(tmp_path / f"{path.name}.sigstore.json")]
    assert main(args, cosign=Cosign(run(None))) == 0
    assert main(args, cosign=Cosign(run("ospreyflow-0.5.0.tgz"))) == 1
    assert main(args, cosign=Cosign(run("install-page.tar.gz"))) == 1


def test_an_oci_artifact_of_the_release_is_checked_like_an_image(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """ADR-114 Amendment 17: the chart pushed to the registry, verified by digest against the
    release workflow's identity, as every owned image is."""
    lock = tmp_path / "versions.lock"
    lock.write_text(_lock(workspace=D, api=E, ingest=D, ner=E))
    refs = set(owned_references(lock.read_text()))
    asked: list[list[str]] = []

    def run(chart_signed: bool) -> Any:
        def answer(argv: Sequence[str]) -> tuple[int, str]:
            asked.append(list(argv))
            if CHART_REF in argv:
                return (0, "ok") if chart_signed else (1, "no signatures found")
            return (0, "ok") if any(r in argv for r in refs) else (1, "x")
        return answer

    args = ["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0",
            "--artifact", CHART_REF]  # fmt: skip
    assert main(args, cosign=Cosign(run(True))) == 0
    assert any(CHART_REF in a and "verify" in a for a in asked)
    assert main(args, cosign=Cosign(run(False))) == 1
    assert CHART_REF in capsys.readouterr().err


def test_a_blob_without_its_signature_is_refused(tmp_path: Path) -> None:
    lock = tmp_path / "versions.lock"
    lock.write_text(_lock(workspace=D, api=E, ingest=D, ner=E))
    with pytest.raises(SystemExit):
        main(["--lock", str(lock), "--repository", "acme/ospreyflow", "--tag", "v0.5.0",
              "--blob", "a", "--blob", "b", "--blob-signature", "a.json"])  # fmt: skip
