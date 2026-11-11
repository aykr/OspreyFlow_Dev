"""The namespace's Terraform the `cloud-platform` profile renders (ADR-148 decisions 1, 4 and 8)
is what OpenTofu formats as written and accepts as valid, for both environments, so the pull
request a person raises from it is not refused for its syntax. OpenTofu runs as the image
`make opentofu-check` pins; `init` fetches the three providers, so this needs Docker and the
network. Shown red by a planted fault in the shape the renderer emits (rule 15)."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from harness.render import render
from tools.cp_policy_check import FIXTURES, _resolver

from schemas.deployment import OspreyConfig

TOFU = "ghcr.io/opentofu/opentofu:1.10.6"


def _terraform(fixture: str) -> dict[str, str]:
    """`fixture` is a fixture's name, `+opensearch` added for the platform's OpenSearch as well."""
    name, _, search = fixture.partition("+")
    raw = yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))
    if search:
        raw.setdefault("components", {})["search"] = search
    artefacts = render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts
    return {
        name.removeprefix("terraform/"): text
        for name, text in artefacts.items()
        if name.startswith("terraform/")
    }


def _write(folder: Path, fixture: str) -> Path:
    for name, text in _terraform(fixture).items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def _tofu(folder: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "run", "--rm", "-v", f"{folder}:/w", TOFU, "-chdir=/w", *args],
        capture_output=True, text=True, timeout=600, check=False,
    )  # fmt: skip


@pytest.mark.parametrize(
    "fixture", ["development", "production", "production+opensearch", "production-bedrock", "poc"]
)
def test_the_terraform_is_formatted_and_valid(tmp_path: Path, fixture: str) -> None:
    """`production-bedrock` renders the gateway's own account and role (P11 part 2)."""
    folder = _write(tmp_path, fixture)
    if fixture == "production-bedrock":
        assert (folder / "gateway.tf").is_file()
    fmt = _tofu(folder, "fmt", "-check", "-diff")
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    init = _tofu(folder, "init", "-backend=false", "-input=false", "-no-color")
    assert init.returncode == 0, init.stdout + init.stderr
    valid = _tofu(folder, "validate", "-no-color")
    assert valid.returncode == 0, valid.stdout + valid.stderr


def test_a_reference_to_nothing_is_refused(tmp_path: Path) -> None:
    folder = _write(tmp_path, "development")
    rds = folder / "rds.tf"
    # What the renderer would emit had a secret's value named a resource it does not write.
    rds.write_text(
        rds.read_text(encoding="utf-8").replace(
            "aws_db_instance.postgres.address", "aws_db_instance.missing.address"
        ),
        encoding="utf-8",
    )
    assert _tofu(folder, "init", "-backend=false", "-input=false", "-no-color").returncode == 0
    assert _tofu(folder, "validate", "-no-color").returncode != 0


# ---- the independent review of P7's Terraform points ---------------------------------------------


@pytest.mark.parametrize("fixture", ["development", "production+opensearch"])
def test_the_providers_and_backend_are_the_namespace_folder_s(fixture: str) -> None:
    """The environments repository's namespace folder already declares its backend, its providers
    and the region; a second unaliased `provider "aws"` beside it is refused as a duplicate."""
    for name, text in _terraform(fixture).items():
        assert not re.search(r"^\s*(terraform|provider\s+\"[^\"]+\")\s*\{", text, re.M), name


def test_the_bucket_role_trusts_the_service_account_s_tokens_for_sts_alone() -> None:
    irsa = _terraform("development")["irsa.tf"]
    assert re.search(r'variable = "\$\{var\.eks_oidc_issuer\}:sub"\s+values\s+= '
                     r'\["system:serviceaccount:\$\{var\.namespace\}:ospreyflow"\]', irsa)  # fmt: skip
    assert re.search(
        r'variable = "\$\{var\.eks_oidc_issuer\}:aud"\s+values\s+= \["sts\.amazonaws\.com"\]', irsa
    )


def test_opensearch_is_reached_from_the_namespace_s_networks_by_the_bucket_role_alone() -> None:
    search = _terraform("production+opensearch")["opensearch.tf"]
    assert "security_group_ids = [aws_security_group.search.id]" in search
    assert re.search(r"from_port\s+= 443", search)
    assert "identifiers = [aws_iam_role.service.arn]" in search
    assert 'resource "aws_opensearch_domain_policy" "search"' in search
