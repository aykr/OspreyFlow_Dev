"""P7's exit: `local-lite`, `small` and `cluster` render as they did before P7 (ADR-148
Consequences: "not touched except for the numeric UIDs", which are in the images, not the render).

Renders the same configurations with the tree at a base commit (`git archive`, into a folder of its
own) and with this tree, each in its own interpreter, every digest from one stand-in resolver, and
compares every artefact byte for byte, with the one thing that must differ normalised: the commit
the image tags and the release version name.

    cd OspreyFlow_Core && .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/gates/p7_renders_unchanged.py [--helm] 78bb4ae

Where the tree has no history (the server's copy, `stack_lease.sh offline`), `--base-tar=<file>` names the base's
`git archive <base> OspreyFlow_Core`, made where the history is; the base's name is then only its label.

Prints each configuration's artefacts and whether they match; exits 1 on any difference. The chart's
manifests for the cluster's values are compared the same way when Docker is there (`--helm`).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CORE = Path(__file__).resolve().parents[5] / "OspreyFlow_Core"

CONFIGS = {
    "local-lite": {},
    "local-lite-reporting": {"reporting": {"sync": True, "superset": True}},
    "local-lite-clickhouse": {"components": {"analytics_engine": "clickhouse"}},
    "small": {"profile": "small", "network": {"public_origin": "https://osprey.example.org"}},
    "small-managed": {
        "profile": "small", "network": {"public_origin": "https://osprey.example.org"},
        "external": {"postgres": {"host": "db.example.internal"},
                     "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"}},
    },
    "cluster-aws": {
        "profile": "cluster", "components": {"analytics_engine": "clickhouse"},
        "network": {"public_origin": "https://osprey.example.org"},
        "reporting": {"sync": True, "superset": True}, "cluster": {"shared_storage_class": "efs-sc"},
        "external": {"postgres": {"host": "db.example.internal"},
                     "valkey": {"host": "cache.example.internal", "port": 6380, "tls": True},
                     "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
                     "search": {"url": "https://search-osprey.eu-west-2.es.amazonaws.com"}},
    },
    "cluster-azure": {
        "profile": "cluster", "components": {"analytics_engine": "clickhouse"},
        "network": {"public_origin": "https://osprey.example.org"},
        "cluster": {"shared_storage_class": "azurefile"},
        "external": {"postgres": {"host": "db.example.internal"},
                     "valkey": {"host": "cache.example.internal"},
                     "media": {"blob_account": "ospreymedia1a2b"}},
    },
}  # fmt: skip

#: P7b: the cloud-platform profile's standard shape, its two synthetic fixtures as `make
#: cp-policy-check` renders them, unchanged but for the one intended difference there (below).
for _shape in ("development", "production"):
    CONFIGS[f"cloud-platform-{_shape}"] = json.loads(json.dumps(__import__("yaml").safe_load(
        (CORE.parent / "OspreyFlow_Build" / "tests" / "fixtures" / "cloud_platform" / f"{_shape}.yaml")
        .read_text(encoding="utf-8"))))  # fmt: skip

#: The cloud-platform profile's ceiling (ADR-148 Amendment 5 point 8): OFFICIAL-SENSITIVE where the
#: deployment names none, where the base held the scheme's highest; as an env line, a ConfigMap's
#: YAML and its JSON.
CEILING = re.compile(r'(OSPREY_HIGHEST_MARKING"?(?:: |=)("?))SECRET(\2)')
def intended(name: str, text: str) -> str:
    """The base's artefact as it would read with the one intended change, for the cloud-platform
    configurations alone; every other configuration is compared as it is."""
    if not name.startswith("cloud-platform-"):
        return text
    return CEILING.sub(r"\1OFFICIAL-SENSITIVE\3", text)

DRIVER = r"""
import hashlib, json, sys
from schemas.deployment import OspreyConfig
from harness.render import render
def resolver(ref): return "sha256:" + hashlib.sha256(ref.encode()).hexdigest()
out = {}
for name, raw in json.loads(sys.stdin.read()).items():
    out[name] = render(OspreyConfig.model_validate(raw), resolver=resolver).artefacts
print(json.dumps(out))
"""


def renders(root: Path) -> dict[str, dict[str, str]]:
    done = subprocess.run(
        [str(CORE / ".venv" / "bin" / "python"), "-c", DRIVER], input=json.dumps(CONFIGS),
        capture_output=True, text=True, cwd=root, check=True,
        env={"PYTHONPATH": f"{root}/packages:{root}", "PATH": "/usr/bin:/bin"},
    )  # fmt: skip
    return json.loads(done.stdout)


#: The one intended difference (the orchestrator's ruling, 10 November 2026): an image already given
#: by its digest was pinned a second time (`ref@sha256:…@sha256:…`) by `harness.cluster._Pins`, in the
#: cluster's values only (the gateway, Ollama, speaches). The base's doubled pin is read as the single
#: one it now is; nothing else is forgiven.
DOUBLED = re.compile(r"(@sha256:[0-9a-f]{64})@sha256:[0-9a-f]{64}")


def normalised(text: str) -> str:
    text = DOUBLED.sub(r"\1", text)
    # The commit the image tags and the release version name (a checkout's, or the archive's none).
    # (the archive has no git, so its checkout says `unknown`).
    commit = r"(?:[0-9a-f]{7,40}|unknown|dev-[0-9a-f]{7,40})"
    text = re.sub(rf"(ghcr\.io/ospreyflow/[a-z-]+:){commit}\b", r"\1<commit>", text)
    # Ours in a platform's registry (cloud-platform), and the chart's checksums of content that
    # holds that commit.
    text = re.sub(rf"(/ospreyflow/[a-z-]+:){commit}\b", r"\1<commit>", text)
    text = re.sub(r'(checksum/(?:files|environment): )"?[0-9a-f]{16}"?', r"\1<checksum>", text)
    text = re.sub(rf"^(\s*tag: ){commit}$", r"\1<commit>", text, flags=re.M)
    text = re.sub(r"sha256:[0-9a-f]{64}", "sha256:<digest>", text)
    text = re.sub(r"(OSPREY_RELEASE_VERSION[=:] ?)\S+", r"\1<release>", text)
    # A pod's configuration checksums hash the environment, which names the commit (above).
    text = re.sub(r"^(\s*checksum/[a-z]+: )[0-9a-f]{16}$", r"\1<checksum>", text, flags=re.M)
    # A Job is named by a hash of its own values (`jobs.yaml`), which are compared as values above:
    # its raw values hold the commit and the base's doubled pins, so the hash is not compared.
    text = re.sub(r"^(\s*name: [a-z-]+-models-)[0-9a-f]{8}$", r"\1<hash>", text, flags=re.M)
    return re.sub(rf'(\\?"version\\?": \\?"){commit}', r"\1<release>", text)


HELM = "alpine/helm:3.16.3"  # as `tools/cp_policy_check.py` pins it


def helm_manifests(root: Path, values: str) -> str:
    """The chart at `root`'s manifests for `values`, as `helm template` emits them."""
    done = subprocess.run(
        ["docker", "run", "--rm", "-i", "-v", f"{root}/deploy/helm/ospreyflow:/chart:ro", HELM,
         "template", "ospreyflow", "/chart", "--namespace", "ospreyflow", "-f", "-"],
        input=values, capture_output=True, text=True, timeout=300, check=True,
    )  # fmt: skip
    return done.stdout


def with_helm(root: Path, rendered: dict[str, dict[str, str]]) -> None:
    """Each configuration with chart values (the cluster's) gains the chart's manifests for them."""
    for artefacts in rendered.values():
        if "values.yaml" in artefacts:
            artefacts["helm template"] = helm_manifests(root, artefacts["values.yaml"])
            artefacts["helm template, parsed"] = parsed(artefacts["helm template"])


def parsed(text: str) -> str:
    """Helm's manifests as Kubernetes reads them: comments gone, and each checksum annotation a
    value, quoted or not (P7 round 1 quoted them; a digest may be all digits)."""
    import yaml

    docs = [d for d in yaml.safe_load_all(normalised(text)) if d]
    for doc in docs:
        template = ((doc.get("spec") or {}).get("template") or {}).get("metadata") or {}
        for key in list(template.get("annotations") or {}):
            if key.startswith("checksum/"):
                template["annotations"][key] = "<checksum>"
    return json.dumps(docs, indent=1, sort_keys=True)


def main(base: str, helm: bool = False, base_tar: str | None = None, full: bool = False) -> int:
    with tempfile.TemporaryDirectory() as folder:
        old = Path(folder) / "OspreyFlow_Core"
        old.mkdir()
        if base_tar:  # made where the history is (`git archive <base> OspreyFlow_Core`), for a copy without it
            subprocess.run(["tar", "-x", "-C", folder, "-f", base_tar], check=True)
        else:
            archive = subprocess.run(
                ["git", "archive", base, "OspreyFlow_Core"], cwd=CORE.parent, capture_output=True,
                check=True,
            )  # fmt: skip
            subprocess.run(["tar", "-x", "-C", folder], input=archive.stdout, check=True)
        before, after = renders(old), renders(CORE)
        if helm:
            with_helm(old, before)
            with_helm(CORE, after)
    differ = 0
    for name in CONFIGS:
        for artefact in sorted(set(before[name]) | set(after[name])):
            a, b = before[name].get(artefact), after[name].get(artefact)
            a = intended(name, a) if a is not None else None
            same = a is not None and b is not None and normalised(a) == normalised(b)
            print(f"{'same' if same else 'DIFFERS'}  {name}  {artefact}")
            if not same:
                differ += 1
                import difflib

                sys.stdout.writelines(
                    list(difflib.unified_diff(normalised(a or "").splitlines(True),
                                              normalised(b or "").splitlines(True), n=1))
                    [: None if full else 40]
                )  # fmt: skip
    print(f"p7_renders_unchanged: {differ} artefact(s) differ from {base}")
    return 1 if differ else 0


if __name__ == "__main__":
    tars = [a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--base-tar=")]
    args = [a for a in sys.argv[1:] if a not in {"--helm", "--full"} and not a.startswith("--base-tar=")]
    # --full: every changed line of each differing artefact, not its first 40 (the record).
    sys.exit(main(args[0] if args else "78bb4ae", helm="--helm" in sys.argv[1:],
                  base_tar=tars[0] if tars else None, full="--full" in sys.argv[1:]))  # fmt: skip
