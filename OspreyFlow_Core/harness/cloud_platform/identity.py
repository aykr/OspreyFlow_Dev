"""The install runbook's sign-in step (`INSTALL.md` §6, ADR-148 Amendment 5): what a cluster's
install does once Keycloak answers (`harness.cluster_install`, its steps 5 and 6), which this
profile has no install of its own to do (ADR-148 Amendment 1, "Left"; P10's sign-in replaces it):
the Conduit's client secret set on its clients, its service account's roles and the realm's sign-in
settings, from the deployment's settings and our Secret together, as the cluster's install gives
them; then the first administrator, `admin`, made with a one-time code printed once.

    python -m harness.cloud_platform.identity <the rendered values.yaml> [--email E]
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from schemas.deployment import OspreyConfig


def main(argv: list[str] | None = None, kube: Any = None) -> int:
    from harness.cluster_install import (
        KCADM_CREATE_FROM_STDIN,
        SystemKube,
        _configure_identity,
    )
    from harness.first_admin import first_administrator, one_time_code
    from ontology.handling import load_uk_le_scheme

    parser = argparse.ArgumentParser(prog="python -m harness.cloud_platform.identity")
    parser.add_argument("values", type=Path, help="the rendered values.yaml")
    parser.add_argument("--email", help="the first administrator's email address")
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as stopped:
        return int(stopped.code or 0)
    kube = kube or SystemKube()
    values = yaml.safe_load(args.values.read_text(encoding="utf-8"))
    config = OspreyConfig.model_validate(yaml.safe_load(values["files"]["osprey.yaml"]))
    assert config.cloud_platform is not None and config.cloud_platform.namespace is not None
    namespace = config.cloud_platform.namespace
    status, out, err = kube.run(
        ["kubectl", "-n", namespace, "get", "secret", values["secrets"]["name"], "-o",
         "jsonpath={.data}"]
    )  # fmt: skip
    if status != 0:
        print(f"our Secret could not be read: {(err or out).strip()}", file=sys.stderr)
        return 1
    held = {key: base64.b64decode(value).decode() for key, value in json.loads(out).items()}
    # As the cluster's install gives them (`cluster_install`, step 5): the ConfigMap's settings,
    # which the realm's sign-in reads (the dashboards' address among them), then our Secret's.
    for line in _configure_identity(kube, namespace, config, {**values["environment"], **held}):
        print(line)
    code = one_time_code()
    user = first_administrator("admin", code=code, scheme=load_uk_le_scheme(), email=args.email)
    status, out, err = kube.run(
        ["kubectl", "-n", namespace, "exec", "-i", "keycloak-0", "-c", "keycloak", "--",
         "sh", "-c", KCADM_CREATE_FROM_STDIN],
        stdin=json.dumps(user),
    )  # fmt: skip
    if status == 0:
        print(f"first administrator admin made: sign in once with the code {code}")
    elif "Conflict" in err or "exists" in err:
        print("first administrator admin already exists; unchanged")
    else:
        said = (err or out).strip().splitlines()
        print(f"making the first administrator: {said[-1] if said else status}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
