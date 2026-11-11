"""The install runbook's sign-in step (`INSTALL.md` §5, ADR-148 Amendment 5): what a cluster's
install does once Keycloak answers, which this profile has no install of its own to do (ADR-148
Amendment 1, "Left"; P10's sign-in replaces it): the Conduit's client secret set on its clients,
its service account's roles and the realm's sign-in settings, from our Secret in the namespace.

    python -m harness.cloud_platform.identity deploy/generated/cloud-platform/values.yaml
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import yaml

from schemas.deployment import OspreyConfig


def main(argv: list[str] | None = None) -> int:
    from harness.cluster_install import SystemKube, _configure_identity

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    values = yaml.safe_load(Path(args[0]).read_text(encoding="utf-8"))
    config = OspreyConfig.model_validate(yaml.safe_load(values["files"]["osprey.yaml"]))
    assert config.cloud_platform is not None and config.cloud_platform.namespace is not None
    namespace = config.cloud_platform.namespace
    secret = values["secrets"]["name"]
    data = json.loads(
        subprocess.run(  # noqa: S603 - the operator's own kubectl
            ["kubectl", "-n", namespace, "get", "secret", secret, "-o", "jsonpath={.data}"],
            check=True, capture_output=True, text=True,
        ).stdout
    )  # fmt: skip
    held = {key: base64.b64decode(value).decode() for key, value in data.items()}
    for line in _configure_identity(SystemKube(), namespace, config, held):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
