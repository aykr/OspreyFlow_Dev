"""ADR-148 Amendment 18 in INSTALL.md: step 6's token-version check, run after the first sign-in, finds the one
line the Conduit logs about a token-version mismatch and stops with its words; before any such refusal it says
only that none has happened so far. The block is the rendered one, taken by the runbook's own block parser and
run in bash with a stand-in `kubectl` whose log holds the line the real resolver writes when it refuses a v1.0
token: the prefix and the words are the Conduit's own, never a copy written here.

The stand-in answers as the real `kubectl logs` does (rule 15), and leaves out what it leaves
out: `logs deploy/api` reads one pod of the Deployment's, never the others; `logs -l <selector>`
reads each matching pod, but only its last 10 lines unless `--tail` says otherwise, each line
prefixed by its pod with `--prefix`; a selector matching no pod says "No resources found" on
stderr and ends 0. The standard shape runs two api replicas, and on the poc shape a restarted
Conduit's old pod lingers. v0.6.0's package test (row 9b, 16 November 2026) found the line in one
pod while the check read the other and said none had been refused, ending 0 —
`test_the_check_finds_the_line_in_any_api_pod_however_far_back`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from harness.cloud_platform.runbooks import command_blocks
from services.api.auth import PrincipalResolver

from principal_auth import TOKEN_VERSION_LOG, TokenVersionMismatch
from schemas.deployment import OspreyConfig
from tests.conftest import sign_token
from tests.harness.test_cloud_platform_render import FIXTURES, _artefacts
from tests.services.api.test_auth import _config
from tests.services.api.test_auth_entra_claims import BY_EXTENSION, CLIENT_ID, FakePeople
from tests.services.api.test_auth_entra_token_version import V2, _v1_claims


def _install() -> str:
    raw = yaml.safe_load((FIXTURES / "poc.yaml").read_text(encoding="utf-8"))
    return _artefacts(OspreyConfig.model_validate(raw))["INSTALL.md"]


def _block() -> str:
    blocks = [b for b in command_blocks(_install(), on_the_platform=False) if TOKEN_VERSION_LOG in b]
    assert len(blocks) == 1, "INSTALL step 6's token-version check"
    return blocks[0]


def _conduit_line(keypair, jwks_url, caplog) -> str:  # type: ignore[no-untyped-def]
    """What the real resolver logs when it refuses a v1.0 token where v2.0 is expected."""
    resolver = PrincipalResolver(_config(jwks_url, oidc_issuer=V2, oidc_audience=CLIENT_ID),
                                 claim_mapping=BY_EXTENSION, role_source=FakePeople(), role_lookup_timeout_seconds=0.2)  # fmt: skip
    with caplog.at_level(logging.WARNING, logger="principal_auth"), pytest.raises(TokenVersionMismatch):
        asyncio.run(resolver.resolve_principal(sign_token(keypair[0], _v1_claims())))
    (line,) = [r.getMessage() for r in caplog.records if r.getMessage().startswith(TOKEN_VERSION_LOG)]
    return f"2026-11-18T09:12:00Z WARNING principal_auth {line}"


#: The api pods' label, as the chart gives each workload's pods (`ospreyflow.labels`, its `.name`).
API_PODS = "app.kubernetes.io/name=api"

_KUBECTL = r"""#!/usr/bin/env python3
# kubectl logs as the real one answers it, over the pods in $PODS (one log file a pod, in order).
import os, sys
API_PODS = os.environ["API_PODS"]
args = sys.argv[1:]
pods = [p for p in os.environ["PODS"].split(":") if p]
if "logs" not in args:
    sys.exit(9)
def lines(pod):
    with open(pod, encoding="utf-8") as f:
        return f.read().splitlines()
if "deploy/api" in args:  # one pod of the Deployment's, never the others
    print("\n".join(lines(pods[0])))
    sys.exit(0)
selector = next((a.split("=", 1)[1] for a in args if a.startswith("--selector=")), None)
if "-l" in args:
    selector = args[args.index("-l") + 1]
if selector is None:
    sys.exit(9)
if selector != API_PODS:
    print(f"No resources found in {os.environ['NS']} namespace.", file=sys.stderr)
    sys.exit(0)
tail = next((a.split("=", 1)[1] for a in args if a.startswith("--tail=")), "10")  # -l's default
for i, pod in enumerate(pods):
    found = lines(pod) if tail == "-1" else lines(pod)[-int(tail):]
    for line in found:
        print(f"[pod/api-{i}/api] {line}" if "--prefix" in args else line)
"""


def _run(block: str, log: str | list[str], tmp_path: Path) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pods = []
    for i, text in enumerate([log] if isinstance(log, str) else log):
        pods.append(tmp_path / f"api-{i}.log")
        pods[-1].write_text(text)
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(_KUBECTL)
    kubectl.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "NS": "ospreyflow-poc",
           "PODS": ":".join(str(p) for p in pods), "API_PODS": API_PODS}  # fmt: skip
    return subprocess.run(["bash", "-c", block], env=env, capture_output=True, text=True)


def test_install_step_6_names_the_version_the_conduit_expects() -> None:
    text = _install()
    step6 = text[text.index("## 6. Sign-in"):text.index("## 7. Check")]
    assert "expects v2.0 access tokens" in step6 and "requestedAccessTokenVersion" in step6


def test_the_check_stops_with_the_conduit_s_own_words_after_a_refused_sign_in(keypair, jwks_url, caplog, tmp_path) -> None:  # type: ignore[no-untyped-def]
    log = "starting\n" + _conduit_line(keypair, jwks_url, caplog) + "\nGET /healthz 200\n"
    done = _run(_block(), log, tmp_path)
    assert done.returncode != 0, done.stdout
    assert "requestedAccessTokenVersion to 2" in done.stdout and "refused for the token version" in done.stdout


def test_before_any_such_refusal_the_check_says_only_that(tmp_path) -> None:  # type: ignore[no-untyped-def]
    done = _run(_block(), "starting\nGET /healthz 200\ntoken rejected: Invalid issuer\n", tmp_path)
    assert done.returncode == 0 and "no sign-in refused for its token version so far" in done.stdout


def test_the_check_finds_the_line_in_any_api_pod_however_far_back(  # type: ignore[no-untyped-def]
    keypair, jwks_url, caplog, tmp_path
) -> None:
    """Two api pods; the refusal in the second, with more than ten lines after it (every request
    since is logged). Read as one pod, or by the label at its default tail, it would be missed."""
    quiet = "starting\nGET /healthz 200\n"
    refused = _conduit_line(keypair, jwks_url, caplog)
    busy = "starting\n" + refused + "\n" + "GET /healthz 200\n" * 20
    done = _run(_block(), [quiet, busy], tmp_path)
    assert done.returncode != 0, done.stdout
    assert "requestedAccessTokenVersion to 2" in done.stdout
    assert "refused for the token version" in done.stdout


def test_the_check_selects_the_api_pods_by_the_chart_s_own_label() -> None:
    """The selector the stand-in admits is the label the chart gives the api pods."""
    core = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
    helpers = core / "deploy" / "helm" / "ospreyflow" / "templates" / "_helpers.tpl"
    assert "app.kubernetes.io/name: {{ .name }}" in helpers.read_text(encoding="utf-8")
    assert f"-l {API_PODS} " in _block()
