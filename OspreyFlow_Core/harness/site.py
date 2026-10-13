"""One address per app (`06_DECISIONS.md` ADR-114 decision 6, Amendment 4): the names a deployment
answers at, all derived from `network.public_origin`, the front proxy's routing table, and the
loopback answer a host tool gives itself for a `*.localhost` name.

The Glass is the origin itself; the identity provider is `id.` and the dashboards `bi.` in front of
the same host, with the same scheme and port. So moving a deployment's address or port is one edit.
"""

from __future__ import annotations

import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from schemas.deployment import OspreyConfig

#: Caddy 2.11.4 (Apache-2.0), released 3 June 2026.
PROXY_IMAGE = "caddy:2.11.4-alpine"
#: Where Caddy listens inside its container for a plain-HTTP origin: unprivileged, so it runs as
#: nobody (`05_DEPLOYMENT.md` §7's non-root posture). The published port is the origin's.
PROXY_HTTP_PORT = 8080
REALM = "osprey"


@dataclass(frozen=True)
class Sites:
    scheme: str
    host: str
    port: int
    glass: str
    identity: str
    dashboards: str


def sites(config: OspreyConfig) -> Sites:
    origin = urlparse(config.network.public_origin.rstrip("/"))
    scheme, host = origin.scheme, origin.hostname or ""
    port = origin.port or (443 if scheme == "https" else 80)
    suffix = f":{origin.port}" if origin.port else ""

    def named(prefix: str) -> str:
        return f"{scheme}://{prefix}{host}{suffix}"

    return Sites(scheme, host, port, named(""), named("id."), named("bi."))


def render_caddyfile(config: OspreyConfig) -> str:
    """The front proxy's routing table: each name to its service on the internal network, and any
    other name refused. Admin API off; on plain HTTP, no certificates at all."""
    names = sites(config)
    routes = [(names.host, "workspace:8080"), (f"id.{names.host}", "keycloak:8080")]
    if config.reporting.superset:
        routes.append((f"bi.{names.host}", "superset:8088"))
    plain = names.scheme == "http"
    lines = [
        "# Rendered from osprey.yaml's network.public_origin (ADR-114 Amendment 4).",
        "{",
        "\tadmin off",
        "\tpersist_config off",
    ]
    if plain:
        lines += ["\tauto_https off", f"\thttp_port {PROXY_HTTP_PORT}"]
    lines.append("}")
    for name, upstream in routes:
        lines += ["", f"{names.scheme}://{name} {{", f"\treverse_proxy {upstream}", "}"]
    # ADR-114 Amendment 7: the doors this machine alone uses, through the proxy, so the services
    # behind them need no published port — and so no route out (measured: a published port needs
    # a network that reaches the internet).
    for port, upstream in loopback_doors(config):
        lines += ["", f"http://:{port} {{", f"\treverse_proxy {upstream}", "}"]
    # Anything else — an unknown name, or the proxy's own health — answers here and nowhere else.
    catch_all = f":{PROXY_HTTP_PORT}" if plain else ":443"
    lines += ["", f"{catch_all} {{", "\trespond /healthz 200", "\trespond 404", "}", ""]
    return "\n".join(lines)


#: A site named by host; a bare `:port` door (`loopback_doors`) is not a name and is not listed.
_SITE = re.compile(r"^(?:https?://)(?P<name>[^\s{:][^\s{]*)\s*\{\s*$")
_UPSTREAM = re.compile(r"^\s*reverse_proxy\s+(?P<upstream>\S+)\s*$")


def routes(caddyfile: str) -> dict[str, str]:
    """`name -> upstream` as a rendered Caddyfile routes them (for the tests and `status`)."""
    found: dict[str, str] = {}
    current: str | None = None
    for line in caddyfile.splitlines():
        if (site_match := _SITE.match(line)) is not None:
            current = site_match["name"]
        elif current and (upstream := _UPSTREAM.match(line)) is not None:
            found[current] = upstream["upstream"]
        elif line.strip() == "}":
            current = None
    return found


#: ADR-114 Amendment 7: `(port, upstream, published-as)` for each door through the proxy. The graph
#: store on this machine only (the owner's ruling of 29 September: seeds run on the host); the
#: Conduit only when `network.expose_conduit` asks, as before.
def loopback_doors(config: OspreyConfig) -> list[tuple[int, str]]:
    doors = [(2480, "arcadedb:2480")]
    if config.network.expose_conduit:
        doors.append((8000, "api:8000"))
    return doors


def _door_ports(config: OspreyConfig) -> list[str]:
    published = ["127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480"]
    if config.network.expose_conduit:
        published.append("${OSPREY_API_PORT:-8000}:8000")
    return published


def proxy_service(config: OspreyConfig) -> dict[str, Any]:
    names = sites(config)
    if names.scheme == "http":
        ports = [f"{names.port}:{PROXY_HTTP_PORT}"]
        extra: dict[str, Any] = {
            "user": "65534:65534",
            "environment": {"XDG_DATA_HOME": "/tmp/caddy", "XDG_CONFIG_HOME": "/tmp/caddy"},
        }
        health = f"http://127.0.0.1:{PROXY_HTTP_PORT}/healthz"
    else:
        # Caddy's automatic HTTPS: certificates for the client's own domain (proven in stage B6).
        ports = ["80:80", f"{names.port}:443"]
        extra = {"volumes": ["proxy-data:/data"]}
        health = "http://127.0.0.1:80/healthz"
    service: dict[str, Any] = {
        "restart": "unless-stopped",
        "image": PROXY_IMAGE,
        "ports": [*ports, *_door_ports(config)],
        **extra,
    }
    service.setdefault("volumes", []).insert(0, "./Caddyfile:/etc/caddy/Caddyfile:ro")
    service["healthcheck"] = {
        "test": ["CMD", "wget", "-q", "-O", "/dev/null", health],
        "interval": "10s",
        "timeout": "5s",
        "retries": 6,
    }
    return service


def marking_floor(config: OspreyConfig) -> str:
    """The marking a surface with no case data shows (ADR-115 decision 2): the deployment's own, or
    its handling scheme's lowest. The scheme is the one the Conduit loads (UK law enforcement)."""
    from ontology.handling import load_uk_le_scheme

    known = load_uk_le_scheme().classification
    chosen = config.governance.marking
    if chosen is None:
        return known[0]
    if chosen not in known:
        raise ValueError(
            f"governance.marking {chosen!r} is not a classification of the handling scheme: "
            f"use one of {', '.join(known)}"
        )
    return chosen


def deployment_version() -> str:
    """What the welcome page's footer names: the commit the deployment was built from, short, until
    stage B5's release tags exist."""
    from harness.render import git_sha

    return git_sha()[:7]


def render_glass_settings(config: OspreyConfig) -> str:
    """What the Glass reads at start (`/deployment.json`): where its identity provider is, the
    marking it shows before any case data is on screen, and the welcome page's settings."""
    welcome = config.welcome
    links = {
        name: address
        for name, address in (
            ("account_help", welcome.account_help),
            ("accessibility", welcome.accessibility),
            ("privacy", welcome.privacy),
            ("service_status", welcome.service_status),
        )
        if address
    }
    settings = {
        "identity_provider": sites(config).identity,
        "realm": REALM,
        "marking": marking_floor(config),
        "organisation_sign_in": config.governance.organisation_sign_in,
        "welcome": {"about": welcome.about, "links": links},
        "version": deployment_version(),
    }
    return json.dumps(settings, indent=2) + "\n"


_answered = False


def answer_localhost_with_loopback() -> None:
    """For this process, `localhost` and every `*.localhost` name resolve to loopback (RFC 6761
    §6.3), whatever the operating system's resolver does with them — so a host tool reaches the
    proxy with the name intact in its request. Every other name resolves as before."""
    global _answered
    if _answered and getattr(socket.getaddrinfo, "_osprey_loopback", False):
        return
    underlying = socket.getaddrinfo

    def getaddrinfo(host: Any, port: Any, family: int = 0, type: int = 0, proto: int = 0,
                    flags: int = 0) -> Any:  # fmt: skip
        name = host.decode() if isinstance(host, bytes) else host
        bare = name.lower().rstrip(".") if isinstance(name, str) else ""
        if bare == "localhost" or bare.endswith(".localhost"):
            number = int(port) if str(port).isdigit() else 0
            kinds = [type] if type else [socket.SOCK_STREAM, socket.SOCK_DGRAM]
            return [(socket.AF_INET, kind, proto, "", ("127.0.0.1", number)) for kind in kinds]
        return underlying(host, port, family, type, proto, flags)

    getaddrinfo._osprey_loopback = True  # type: ignore[attr-defined]
    socket.getaddrinfo = getaddrinfo
    _answered = True


def deployment_origins(env_file: Path) -> tuple[str, str]:
    """`(glass, identity)` as a rendered deployment's `deployment.env` names them — what every tool
    on the host reaches the deployment at. A deployment rendered before B3 names neither, and is
    answered with its old published ports, so a tool still reaches it until it is reinstalled."""
    values: dict[str, str] = {}
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and not key.startswith("#"):
                values[key.strip()] = value.strip()
    except OSError:
        pass
    if "OSPREY_IDENTITY_ORIGIN" in values:
        return values.get("OSPREY_GLASS_ORIGIN", values["OSPREY_IDENTITY_ORIGIN"]), values[
            "OSPREY_IDENTITY_ORIGIN"
        ]
    return (
        f"http://127.0.0.1:{values.get('OSPREY_WORKSPACE_PORT', '8080')}",
        f"http://127.0.0.1:{values.get('OSPREY_KEYCLOAK_PORT', '8081')}",
    )
