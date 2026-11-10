"""P7's exit: `local-lite`, `small` and `cluster` render as they did before P7 (ADR-148
Consequences: "not touched except for the numeric UIDs", which are in the images, not the render).

Renders the same configurations with the tree at a base commit (`git archive`, into a folder of its
own) and with this tree, each in its own interpreter, every digest from one stand-in resolver, and
compares every artefact byte for byte, with the one thing that must differ normalised: the commit
the image tags and the release version name.

    cd OspreyFlow_Core && .venv/bin/python ../OspreyFlow_Build/process/lanes/platform/gates/p7_renders_unchanged.py 78bb4ae

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
    text = re.sub(rf"^(\s*tag: ){commit}$", r"\1<commit>", text, flags=re.M)
    text = re.sub(r"sha256:[0-9a-f]{64}", "sha256:<digest>", text)
    text = re.sub(r"(OSPREY_RELEASE_VERSION[=:] ?)\S+", r"\1<release>", text)
    return re.sub(rf'(\\?"version\\?": \\?"){commit}', r"\1<release>", text)


def main(base: str) -> int:
    with tempfile.TemporaryDirectory() as folder:
        old = Path(folder) / "OspreyFlow_Core"
        old.mkdir()
        archive = subprocess.run(
            ["git", "archive", base, "OspreyFlow_Core"], cwd=CORE.parent, capture_output=True,
            check=True,
        )  # fmt: skip
        subprocess.run(["tar", "-x", "-C", folder], input=archive.stdout, check=True)
        before, after = renders(old), renders(CORE)
    differ = 0
    for name in CONFIGS:
        for artefact in sorted(set(before[name]) | set(after[name])):
            a, b = before[name].get(artefact), after[name].get(artefact)
            same = a is not None and b is not None and normalised(a) == normalised(b)
            print(f"{'same' if same else 'DIFFERS'}  {name}  {artefact}")
            if not same:
                differ += 1
                import difflib

                sys.stdout.writelines(
                    list(difflib.unified_diff(normalised(a or "").splitlines(True),
                                              normalised(b or "").splitlines(True), n=1))[:40]
                )  # fmt: skip
    print(f"p7_renders_unchanged: {differ} artefact(s) differ from {base}")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "78bb4ae"))
