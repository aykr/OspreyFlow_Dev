"""What the tests of the page service's addresses share (build id PL7, slice PL7f): the table of
cases (`tests/fixtures/page_addresses_cases.json`, the owner's, approved on 24 November 2026), a
row as a deployment configuration, a render of it, and the readers of a rendered Caddyfile.
Shared, as `access_key_proxy_fixtures.py` is, by `test_page_addresses.py` and
`test_page_addresses_caddy.py`, so neither imports the other's test file. It reads the one table
file and imports the renderers; it writes nothing and walks no folder.
"""

from __future__ import annotations

import contextlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import urlsplit

import yaml
from tools import reference_render as ref

TABLE = Path(__file__).resolve().parents[1] / "fixtures" / "page_addresses_cases.json"
CASES = json.loads(TABLE.read_text(encoding="utf-8"))
ROWS: list[dict[str, Any]] = CASES["rows"]
IDS = [row["id"] for row in ROWS]
SECRET_VARIABLE: str = CASES["secret_variable"]
DERIVED = [row for row in ROWS if "derived" in row["expect"]]
REFUSED = [row for row in ROWS if "refuse" in row["expect"]]
REFUSED_BY_DERIVE = [row for row in REFUSED if row["expect"]["refuse"].get("by") != "schema"]
BRANDS = ref.BRANDS
CA_ON_THE_HOST = "/etc/ospreyflow/tls/org-root.pem"
#: A secret as long as the service wants, standing for what the env file or the cluster's Secret
#: holds.
A_SECRET = "s" * 40
PAGES_CONFIG_TS = ref.CORE / "apps" / "pages" / "server" / "config.ts"


# ---- the table, as configurations ------------------------------------------------------------


def raw_of(row: dict[str, Any], brand: str | None = None) -> dict[str, Any]:
    """The row's configuration as plain data: the shape's own, with the row's origin, certificate,
    doors, key and setting put in."""
    given = row["config"]
    raw = ref.raw_config(given["shape"])
    raw["network"]["public_origin"] = given["origin"]
    own = given["own_certificate"]
    if own is not None:
        raw["network"]["tls"] = {
            "certificate": "/etc/ospreyflow/tls/osprey.crt",
            "key": "/etc/ospreyflow/tls/osprey.key",
            **({"ca": CA_ON_THE_HOST} if own["ca"] else {}),
        }
    if given["expose_conduit"]:
        raw["network"]["expose_conduit"] = True
    if given["redirect_http"]:
        raw["network"]["redirect_http"] = True
    if given["access_key"]:
        raw["network"]["access_key"] = True
    chosen = brand or given["brand"]
    if chosen == "govuk":
        raw["appearance"] = dict(ref.GOVUK_APPEARANCE)
    raw["pages"] = {"enabled": given["pages"]}
    return raw


def config_of(row: dict[str, Any], brand: str | None = None) -> Any:
    from schemas.deployment import OspreyConfig

    return OspreyConfig.model_validate(raw_of(row, brand))


@contextlib.contextmanager
def tree_of(row: dict[str, Any]) -> Iterator[None]:
    """`scripts.tree_parity.govuk_tree_state()` says complete where the row says so (its own seam,
    as `test_pages_setting.py` points it)."""
    from scripts import tree_parity

    state = tree_parity.COMPLETE if row["config"]["complete_govuk_tree"] else "partial"
    with mock.patch.object(tree_parity, "govuk_tree_state", lambda *a, **k: state):
        yield


def render_of(config: Any) -> dict[str, str]:
    """A render's artefacts, rendered directly (nothing staged, no key read)."""
    from harness.render import render

    return {
        name: text if isinstance(text, str) else text.decode("utf-8")
        for name, text in render(config, resolver=ref.resolver).artefacts.items()
    }


def caddyfile_of(row: dict[str, Any], config: Any, artefacts: dict[str, str]) -> str:
    """The front proxy's Caddyfile as the shape has it: the compose shapes' own artefact, the
    cluster's as `render_caddyfile` writes it for a proxy with no alias and no doors."""
    if row["config"]["shape"] in ("local-lite", "small"):
        return artefacts["Caddyfile"]
    from harness.site import render_caddyfile

    return render_caddyfile(config, doors=False)


def pages_environment(row: dict[str, Any], artefacts: dict[str, str]) -> dict[str, str] | None:
    """The page service's variables by name, as the shape writes them (a compose service's
    `environment`; a chart workload's `env`), or None when there is no page service."""
    if row["config"]["shape"] in ("local-lite", "small"):
        services = yaml.safe_load(artefacts["compose.yaml"])["services"]
        found = services.get("pages")
        return None if found is None else {k: str(v) for k, v in found["environment"].items()}
    workloads = {
        w["name"]: w for w in yaml.safe_load(artefacts["values.yaml"]).get("workloads", [])
    }
    found = workloads.get("pages")
    if found is None:
        return None
    env: dict[str, str] = {}
    for entry in found.get("env") or []:
        if "value" in entry:
            env[entry["name"]] = str(entry["value"])
        elif "secret" in entry:
            env[entry["name"]] = f"secret:{entry['secret']}"
        else:
            env[entry["name"]] = f"config:{entry.get('config')}"
    return env


def resolved(env: dict[str, str]) -> dict[str, str]:
    """The variables as the container would see them: a secret reference is the secret."""
    seen: dict[str, str] = {}
    for name, value in env.items():
        if value.startswith("secret:") or (name.endswith("_SECRET") and value.startswith("${")):
            seen[name] = A_SECRET
        elif value.startswith("config:"):
            continue
        elif value.startswith("${"):
            seen[name] = (
                re.sub(r"^\$\{\w+:-(.*)\}$", r"\1", value) if ":-" in value else "valkey.internal"
            )
        else:
            seen[name] = value
    return seen


def site_addresses(caddyfile: str) -> list[list[str]]:
    """Each site block's address list: a line at the margin that ends in `{` (not the global
    block's own)."""
    found = []
    for line in caddyfile.splitlines():
        if line.endswith("{") and line != "{" and not line.startswith(("\t", " ", "#")):
            found.append([a.strip() for a in line[:-1].split(",")])
    return found


def identity_site(caddyfile: str, alias: str) -> list[str]:
    sites = [a for a in site_addresses(caddyfile) if urlsplit(a[0]).hostname == alias]
    return sites[0] if sites else []


def explicit_https_ports(caddyfile: str) -> set[int]:
    """Every port an `https://` address in the Caddyfile names."""
    ports: set[int] = set()
    for addresses in site_addresses(caddyfile):
        for address in addresses:
            url = urlsplit(address)
            if url.scheme == "https" and url.port:
                ports.add(url.port)
    return ports


def clash_findings(caddyfile: str) -> list[str]:
    """Each port the Caddyfile makes both a plain-HTTP listener and an HTTPS one, as Caddy reads the
    addresses: `http://` with a port (else the global `http_port`, 80), a bare `:port` (plain HTTP),
    `https://` with a port (else the global `https_port`, 443). A pure model of Caddy's refusal
    ("cannot natively multiplex HTTP and HTTPS"), a fast check that is never the only one: the real
    Caddy runs in `test_page_addresses_caddy.py`."""

    def written(name: str, default: int) -> int:
        found = re.search(rf"(?m)^\t{name} (\d+)$", caddyfile)
        return int(found[1]) if found else default

    http_default, https_default = written("http_port", 80), written("https_port", 443)
    plain: set[int] = set()
    secure: set[int] = set()
    for addresses in site_addresses(caddyfile):
        for address in addresses:
            if address.startswith(":"):
                plain.add(int(address[1:]))
                continue
            url = urlsplit(address)
            if url.scheme == "https":
                secure.add(url.port or https_default)
            elif url.scheme == "http":
                plain.add(url.port or http_default)
    return [
        f"port {port} is served as plain HTTP and as HTTPS in one Caddyfile, which Caddy refuses"
        for port in sorted(plain & secure)
    ]
