"""What a deployment with the page service off writes for its identity and sign-in addresses, for
the origins that make a difference: a default port written out, the host in upper case, a port that
is not the scheme's own, and the plain forms (build id PL7, slice PL7f round 4; ADR-152 Amendment 3
item 2: with `pages.enabled` off every rendered file is what it was).

Run two ways, with the same code: in the test's own process, against the renderers of this
checkout, and as a script (`python pages_off_capture.py`, `PYTHONPATH` naming a tree's
`OspreyFlow_Core`, its `packages` and `OspreyFlow_Build`) against a tree taken out of git at the
commit main stood at before this part. The two answers are compared by
`tests/harness/test_pages_setting.py`; the reference file it holds was made by the script from that
commit, never written by hand. It reads nothing but the renderers and `tools.reference_render`; it
writes to standard output only and walks no folder.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from tools import reference_render as ref

#: The origins each shape is rendered with. A shape's own default is `ref.raw_config(shape)`'s.
ORIGINS: dict[str, list[str]] = {
    "local-lite": [
        "http://reference.ospreyflow.localhost:8081",
        "http://reference.ospreyflow.localhost:80",
        "http://reference.ospreyflow.localhost",
        "http://Reference.OspreyFlow.localhost:8081",
        "https://reference.ospreyflow.localhost",
        "https://reference.ospreyflow.localhost:443",
        "https://Reference.OspreyFlow.localhost",
    ],
    "small": [
        "https://osprey.example.org",
        "https://osprey.example.org:443",
        "https://OSPREY.Example.ORG",
        "https://osprey.example.org:9443",
        "http://osprey.example.org:80",
    ],
    "small+tls": [
        "https://osprey.example.org",
        "https://osprey.example.org:443",
        "https://OSPREY.Example.ORG",
        "https://osprey.example.org:9443",
    ],
    "cluster": [
        "https://osprey.example.org",
        "https://osprey.example.org:443",
        "https://OSPREY.Example.ORG",
        "https://osprey.example.org:9443",
    ],
    "cloud-platform": ["https://osprey.example.org", "https://osprey.example.org:443"],
}


def raw_of(shape: str, origin: str) -> dict[str, Any]:
    """The shape's reference configuration with the origin (and, for `small+tls`, the
    organisation's own certificate) put in. The setting is not written: it is off by default."""
    raw = ref.raw_config(shape.split("+")[0])
    raw["network"]["public_origin"] = origin
    if shape == "small+tls":
        raw["network"]["tls"] = {
            "certificate": "/etc/ospreyflow/tls/osprey.crt",
            "key": "/etc/ospreyflow/tls/osprey.key",
            "ca": "/etc/ospreyflow/tls/org-root.pem",
        }
    return raw


def capture() -> dict[str, Any]:
    """For each shape and origin: the address fields of `sites`, the Glass's sign-in client, the
    organisation's redirect addresses, the sign-in page's Glass origin, and every line of every
    rendered file that holds the deployment's host (compose, env file, Caddyfile, realm, runbook,
    Glass settings, chart values), in either case."""
    from harness import keycloak_theme, realm
    from harness.render import render
    from harness.site import sites

    from schemas.deployment import OspreyConfig

    out: dict[str, Any] = {}
    for shape, origins in ORIGINS.items():
        for origin in origins:
            key = f"{shape} {origin}"
            try:
                config = OspreyConfig.model_validate(raw_of(shape, origin))
            except Exception as error:  # noqa: BLE001
                out[key] = {"config": type(error).__name__}
                continue
            host = origin.split("://")[1].split(":")[0].lower()
            names = sites(config)
            got: dict[str, Any] = {
                "sites": [
                    names.scheme,
                    names.host,
                    names.port,
                    names.glass,
                    names.identity,
                    names.dashboards,
                ],  # fmt: skip
                "glass_client": realm.glass_client(config),
                "organisation_redirect_uris": list(realm.organisation_redirect_uris(config)),
                "theme_glass_origin": keycloak_theme.login_theme_options(config)["glass_origin"],
            }
            try:
                artefacts = render(config, resolver=ref.resolver).artefacts
            except Exception as error:  # noqa: BLE001
                got["render"] = f"{type(error).__name__}: {error}"
            else:
                lines: dict[str, list[str]] = {}
                for name, text in sorted(artefacts.items()):
                    text = text if isinstance(text, str) else text.decode("utf-8", "replace")
                    found = [line for line in text.splitlines() if host in line.lower()]
                    if found:
                        lines[name] = found
                got["render"] = lines
            out[key] = got
    return out


def as_data() -> dict[str, Any]:
    """`capture()` as the JSON the reference file holds (tuples as lists, keys in order)."""
    return json.loads(json.dumps(capture(), sort_keys=True, default=str))


if __name__ == "__main__":
    json.dump(capture(), sys.stdout, indent=1, sort_keys=True, default=str)
