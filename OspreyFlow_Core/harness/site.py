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
import ssl
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from schemas.deployment import EntraSignInConfig, OspreyConfig, Profile, self_contained_small

#: Caddy 2.11.4 (Apache-2.0), released 3 June 2026.
PROXY_IMAGE = "caddy:2.11.4-alpine"
#: Where Caddy listens inside its container for a plain-HTTP origin: unprivileged, so it runs as
#: nobody (`05_DEPLOYMENT.md` §7's non-root posture). The published port is the origin's.
PROXY_HTTP_PORT = 8080
#: Where Caddy listens for HTTPS with the organisation's own certificate (ADR-114 Amendment 33
#: decision 3): unprivileged, as the account that owns the key. The published port is the origin's.
PROXY_HTTPS_PORT = 8443
#: Where the compose file mounts `network.tls`'s two files into the proxy, read-only.
CERT_IN_PROXY = "/certs/cert.pem"
KEY_IN_PROXY = "/certs/key.pem"
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


def render_caddyfile(config: OspreyConfig, *, doors: bool = True) -> str:
    """The front proxy's routing table: each name to its service on the internal network, and any
    other name refused. Admin API off; on plain HTTP, no certificates at all. A cluster has no host
    to open the loopback doors to (`doors=False`)."""
    names = sites(config)
    routes = [(names.host, "workspace:8080"), (f"id.{names.host}", "keycloak:8080")]
    if config.reporting.superset:
        routes.append((f"bi.{names.host}", "superset:8088"))
    plain = names.scheme == "http"
    own = config.network.tls is not None
    lines = [
        "# Rendered from osprey.yaml's network.public_origin (ADR-114 Amendment 4).",
        "{",
        "\tadmin off",
        "\tpersist_config off",
    ]
    if plain:
        lines += ["\tauto_https off", f"\thttp_port {PROXY_HTTP_PORT}"]
    elif own:
        # ADR-114 Amendment 33 decision 3: the organisation's certificate, given; no certificate
        # obtained, no redirect listener of Caddy's own, no OCSP fetched from the CA's responder
        # (measured against Caddy 2.11.4: without `ocsp_stapling off` it asks the responder a
        # certificate names; without `auto_https off` it adds its own redirects).
        lines += [
            "\tauto_https off",
            "\tocsp_stapling off",
            f"\thttp_port {PROXY_HTTP_PORT}",
            f"\thttps_port {PROXY_HTTPS_PORT}",
        ]
    lines.append("}")
    gate = config.network.access_key
    if gate:
        # ADR-114 Amendment 41: the shared key's hash and the pass, written on the server by
        # `python -m harness.access_key set` and mounted into the proxy alone; never rendered here.
        from harness.access_key import IN_PROXY

        lines += ["", f"import {IN_PROXY}"]
    given = [f"\ttls {CERT_IN_PROXY} {KEY_IN_PROXY}"] if own else []
    for name, upstream in routes:
        if name == f"id.{names.host}" and config.appearance.brand == "govuk":
            # ADR-132 Amendment 2: the sign-in page's GOV.UK stylesheet and fonts come from the
            # Glass, on the sign-in page's own name, so they are same-origin there.
            handlers = [
                "\thandle /assets/govuk/* {",
                "\t\treverse_proxy workspace:8080",
                "\t}",
                "\thandle {",
                f"\t\treverse_proxy {upstream}",
                "\t}",
            ]
        else:
            handlers = [f"\treverse_proxy {upstream}"]
        if gate:
            handlers = _behind_the_key(
                names.host, identity=name == f"id.{names.host}", handlers=handlers
            )
        lines += ["", f"{names.scheme}://{name} {{", *given, *handlers, "}"]
    # ADR-114 Amendment 7: the doors this machine alone uses, through the proxy, so the services
    # behind them need no published port — and so no route out (measured: a published port needs
    # a network that reaches the internet).
    for port, upstream in loopback_doors(config) if doors else []:
        lines += ["", f"http://:{port} {{", f"\treverse_proxy {upstream}", "}"]
    # Anything else — an unknown name, or the proxy's own health — answers here and nowhere else.
    # On HTTPS that is plain HTTP on 80: the health check asks a bare address, which has no
    # certificate, and a name's own plain-HTTP request still goes to HTTPS first (measured against
    # Caddy; `tests/harness/test_proxy_health.py`).
    if own and config.network.redirect_http:
        # Amendment 33 decision 2: port 80, when asked, only sends each name to its https://
        # address (on the origin's own port, if it has one).
        suffix = "" if names.port == 443 else f":{names.port}"
        for name, _upstream in routes:
            lines += ["", f"http://{name} {{", *([NOINDEX] if gate else []),
                      f"\tredir https://{name}{suffix}{{uri}} 308", "}"]  # fmt: skip
    catch_all = f":{PROXY_HTTP_PORT}" if plain or own else "http://:80"
    lines += ["", f"{catch_all} {{", *([NOINDEX] if gate else []), "\trespond /healthz 200",
              "\trespond 404", "}", ""]  # fmt: skip
    return "\n".join(lines)


#: ADR-114 Amendment 41: every answer of a deployment that asks for the key says so to a crawler.
NOINDEX = '\theader X-Robots-Tag "noindex, nofollow"'
#: What the Glass asks its identity provider from its own origin, where a browser sends no stored
#: credential and no cookie: its discovery document, its keys and its token. Each answers nothing
#: without a code, a refresh token or a signature to check against; the sign-in page itself is
#: behind the key.
OPEN_ON_THE_IDENTITY_PROVIDER = (
    f"/realms/{REALM}/protocol/openid-connect/token",
    f"/realms/{REALM}/protocol/openid-connect/certs",
    f"/realms/{REALM}/.well-known/openid-configuration",
)


def _behind_the_key(host: str, *, identity: bool, handlers: list[str]) -> list[str]:
    """One name's handlers behind the shared key (ADR-114 Amendment 41), in this order: a request
    that has no pass, is not a CORS preflight (an `OPTIONS` naming the method it asks about, which
    never carries a credential) and, on the identity provider, is not one of its open answers,
    is asked for the key (`basic_auth`); once it has answered, it is given the pass for the
    deployment's base name, `host`, so the other two names let it through too (ADR-114 Amendment
    42). **Any Basic `Authorization`, whatever its case, is taken off** before anything behind
    the proxy sees it, so the key never reaches a service. The file's three snippets,
    `harness.access_key.snippet`, carry the hash and the pass."""
    unasked = [
        "\t\tnot {",
        "\t\t\tmethod OPTIONS",
        "\t\t\theader Access-Control-Request-Method *",
        "\t\t}",
    ]
    if identity:
        # Exactly these paths as asked, decoded but not cleaned: Caddy's own `path` matcher cleans
        # first, so `.../auth%2F..%2Ftoken` matched the token and went on raw (found by
        # `test_an_encoded_or_disguised_path_never_reaches_the_sign_in_page_without_the_key`).
        listed = ", ".join(f'"{path}"' for path in OPEN_ON_THE_IDENTITY_PROVIDER)
        unasked.append(f"\t\tnot expression `{{http.request.orig_uri.path}} in [{listed}]`")
    unasked += ["\t\tnot {", "\t\t\timport osprey_access_pass", "\t\t}"]
    basic = ["\t\theader_regexp Authorization (?i)^basic\\s"]
    return [
        NOINDEX,
        # Every answer, a refusal included, is in the proxy's own log (Caddy redacts
        # `Authorization` and `Cookie` there): an attempt at the key is seen.
        "\tlog",
        "\t@osprey_locked {",
        *unasked,
        "\t}",
        "\t@osprey_answered {",
        *unasked,
        *basic,
        "\t}",
        "\t@osprey_basic {",
        *basic,
        "\t}",
        "\troute {",
        "\t\tbasic_auth @osprey_locked bcrypt OspreyFlow {",
        "\t\t\timport osprey_access_key",
        "\t\t}",
        f"\t\timport osprey_access_pass_set {host}",
        "\t\trequest_header @osprey_basic -Authorization",
        *("\t" + line for line in handlers),
        "\t}",
    ]


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


#: S10 (GDS re-audit, the owner's ruling of 2 November 2026; `05_DEPLOYMENT.md` §7): **Lite answers
#: on this computer only.** Every port a Lite deployment publishes is bound to `127.0.0.1`; a bare
#: `HOST:CONTAINER` makes Docker publish it on every interface, and a machine on the same network
#: that sent `Host: ospreyflow.localhost` reached the Glass and sign-in in plain HTTP. Small and
#: Enterprise are reached by other people, so their 80 and 443 stay on every interface.
LOOPBACK = "127.0.0.1"


def _bind(config: OspreyConfig, mapping: str) -> str:
    """`mapping` as Lite publishes it, on loopback; as written for Small, on every interface."""
    return f"{LOOPBACK}:{mapping}" if config.profile is Profile.LOCAL_LITE else mapping


def _door_ports(config: OspreyConfig) -> list[str]:
    published = [f"{LOOPBACK}:${{OSPREY_ARCADEDB_PORT:-2480}}:2480"]
    if config.network.expose_conduit:
        conduit = "${OSPREY_API_PORT:-8000}:8000"
        # ADR-114 Amendment 33 decision 2: on a Small with every store in a container, 443 is the
        # one door other machines reach; the Conduit's opt-in door is this server's alone.
        published.append(
            f"{LOOPBACK}:{conduit}" if self_contained_small(config) else _bind(config, conduit)
        )
    return published


#: The account that owns `network.tls.key`, which the proxy runs as so the key can stay `600`
#: (ADR-114 Amendment 33 decision 3). `apply` writes both into `deployment.env` from the key file
#: itself; the render never reads the machine.
PROXY_USER = "${OSPREY_PROXY_UID:?}:${OSPREY_PROXY_GID:?}"


def _own_certificate_service(config: OspreyConfig, port: int) -> dict[str, Any]:
    """The proxy with the organisation's certificate: 443 (the origin's port) alone, on every
    interface or the one `network.listen_address` names; 80 only when `redirect_http` asks; run as
    the key's owner; the two files mounted read-only; no `proxy-data` volume."""
    network = config.network
    assert network.tls is not None
    listen = f"{network.listen_address}:" if network.listen_address else ""
    ports = [f"{listen}{port}:{PROXY_HTTPS_PORT}"]
    if network.redirect_http:
        ports.append(f"{listen}80:{PROXY_HTTP_PORT}")
    return {
        "ports": ports,
        "user": PROXY_USER,
        "environment": {
            "XDG_DATA_HOME": "/tmp/caddy",
            "XDG_CONFIG_HOME": "/tmp/caddy",
        },
        "volumes": [
            f"{network.tls.certificate}:{CERT_IN_PROXY}:ro",
            f"{network.tls.key}:{KEY_IN_PROXY}:ro",
            # `apply` writes the certificate's SHA-256 here: a renewed certificate changes this one
            # file, which only the proxy mounts, so `ospreyflow apply` restarts the proxy alone.
            f"./{TLS_FINGERPRINT_FILE}:/certs/fingerprint:ro",
        ],
    }


#: The file in the deployment's folder that holds the served certificate's SHA-256 fingerprint.
TLS_FINGERPRINT_FILE = "tls-fingerprint"


def proxy_service(config: OspreyConfig) -> dict[str, Any]:
    names = sites(config)
    extra: dict[str, Any]
    if names.scheme == "https" and config.network.tls is not None:
        extra = _own_certificate_service(config, names.port)
        ports = extra.pop("ports")
        health = f"http://127.0.0.1:{PROXY_HTTP_PORT}/healthz"
    elif names.scheme == "http":
        ports = [_bind(config, f"{names.port}:{PROXY_HTTP_PORT}")]
        extra = {
            "user": "65534:65534",
            "environment": {"XDG_DATA_HOME": "/tmp/caddy", "XDG_CONFIG_HOME": "/tmp/caddy"},
        }
        health = f"http://127.0.0.1:{PROXY_HTTP_PORT}/healthz"
    else:
        # Caddy's automatic HTTPS: certificates for the client's own domain (proven in stage B6).
        ports = [_bind(config, "80:80"), _bind(config, f"{names.port}:443")]
        extra = {"volumes": ["proxy-data:/data"]}
        health = "http://127.0.0.1:80/healthz"
    service: dict[str, Any] = {
        "restart": "unless-stopped",
        "image": PROXY_IMAGE,
        "ports": [*ports, *_door_ports(config)],
        **extra,
    }
    service.setdefault("volumes", []).insert(0, "./Caddyfile:/etc/caddy/Caddyfile:ro")
    if config.network.access_key:
        from harness.access_key import ACCESS_KEY_FILE, IN_PROXY

        # ADR-114 Amendment 41: the key's hash and the pass, to the proxy alone; read-only. The long
        # form, never creating its source: Docker's short form makes a folder where a file is
        # missing, which then stands in the key's place; this way a missing key stops the start.
        service["volumes"].insert(1, {
            "type": "bind",
            "source": f"./{ACCESS_KEY_FILE}",
            "target": IN_PROXY,
            "read_only": True,
            "bind": {"create_host_path": False},
        })  # fmt: skip
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


#: A profile's own ceiling where the deployment names none (ADR-148 decision 10; Amendment 5): the
#: client's platform holds OFFICIAL-SENSITIVE at most. Every other profile takes the scheme's
#: highest.
PROFILE_CEILINGS: dict[Profile, str] = {Profile.CLOUD_PLATFORM: "OFFICIAL-SENSITIVE"}


def highest_marking(config: OspreyConfig) -> str:
    """The highest marking the deployment may hold (ADR-148 decision 10): its own, else its
    profile's own (`PROFILE_CEILINGS`), else its handling scheme's highest. The scheme is the one
    the Conduit loads (UK law enforcement); a profile's default it does not hold is refused."""
    from ontology.handling import load_uk_le_scheme

    known = load_uk_le_scheme().classification
    chosen = config.deployment.highest_marking
    if chosen is None:
        default = PROFILE_CEILINGS.get(config.profile)
        if default is None:
            return known[-1]
        if default not in known:
            raise ValueError(
                f"the {config.profile.value} profile's ceiling {default} is not a classification "
                f"of the handling scheme: its classifications are {', '.join(known)}"
            )
        return default
    if chosen not in known:
        raise ValueError(
            f"deployment.highest_marking {chosen!r} is not a classification of the handling "
            f"scheme: use one of {', '.join(known)}"
        )
    return chosen


def deployment_version() -> str:
    """What the welcome page's footer names: the commit the deployment was built from, short, until
    stage B5's release tags exist."""
    from harness.render import git_sha

    return git_sha()[:7]


def organisation_label(config: OspreyConfig) -> str | None:
    """The organisation's provider as people know it (`sign_in.organisation.label`, kept as
    `governance.organisation_provider.label`), which the welcome page's button names: *Continue
    with <label>* (ADR-115 Amendment 5). None without organisation sign-in, or for an alias brokered
    by hand, which has no label; the button then keeps ADR-115 decision 3's words."""
    governance = config.governance
    if not governance.organisation_sign_in or governance.organisation_provider is None:
        return None
    return governance.organisation_provider.label.strip() or None


def render_glass_settings(config: OspreyConfig, *, entra: EntraSignInConfig | None = None) -> str:
    """What the Glass reads at start (`/deployment.json`): where its identity provider is, the
    marking it shows before any case data is on screen, the welcome page's settings and the
    deployment's appearance (ADR-132).

    **On Entra ID sign-in** (`entra`, the cloud-platform profile's `claims`; ADR-148 Amendment 8)
    the realm's address is replaced by `sign_in`: Entra's authority, the Glass's own app
    registration and the scope it asks the API for. Without it the file is byte for byte what it
    was."""
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
        # ADR-115 Amendment 5: the welcome page's button names the provider by its label.
        "organisation_label": organisation_label(config),
        "welcome": {"about": welcome.about, "links": links},
        # ADR-132: the deployment's brand and what its page title, GOV.UK footer and banner name.
        "appearance": config.appearance.told(),
        "version": deployment_version(),
    }
    if config.reporting.superset:
        # The owner's ruling of 13 November 2026 (Q2): where "Build a report" opens Superset, for a
        # holder of `manage_dashboards`; Superset gives them its builder's role (ADR-148 Amendment
        # 9).
        settings["reports_url"] = sites(config).dashboards
    if entra is not None:
        del settings["identity_provider"], settings["realm"]
        settings["sign_in"] = {
            "kind": "entra",
            "authority": f"https://login.microsoftonline.com/{entra.tenant_id}/v2.0",
            "client_id": entra.client_id,
            # `profile` for the names the Glass shows (`preferred_username`, `given_name`).
            "scope": f"openid profile {entra.id_uri}/{entra.scope}",
        }
    return json.dumps(settings, indent=2) + "\n"


_answered = False
#: ADR-114 Amendment 33 decision 2: the deployment's own names, answered on this server, by name.
_HERE: dict[str, str] = {}
#: Certificate files a host tool trusts beside the system's own (the deployment's, and its CA).
_TRUSTED: list[str] = []


def _answer_here() -> None:
    """For this process, `localhost` and every `*.localhost` name resolve to loopback (RFC 6761
    §6.3), and each name in `_HERE` to its address, whatever the operating system's resolver does
    with them — so a host tool reaches the proxy with the name intact in its request. Every other
    name resolves as before."""
    global _answered
    if _answered and getattr(socket.getaddrinfo, "_osprey_loopback", False):
        return
    underlying = socket.getaddrinfo

    def getaddrinfo(host: Any, port: Any, family: int = 0, type: int = 0, proto: int = 0,
                    flags: int = 0) -> Any:  # fmt: skip
        name = host.decode() if isinstance(host, bytes) else host
        bare = name.lower().rstrip(".") if isinstance(name, str) else ""
        address = _HERE.get(bare)
        if address is None and (bare == "localhost" or bare.endswith(".localhost")):
            address = "127.0.0.1"
        if address is not None:
            number = int(port) if str(port).isdigit() else 0
            kinds = [type] if type else [socket.SOCK_STREAM, socket.SOCK_DGRAM]
            return [(socket.AF_INET, kind, proto, "", (address, number)) for kind in kinds]
        return underlying(host, port, family, type, proto, flags)

    getaddrinfo._osprey_loopback = True  # type: ignore[attr-defined]
    socket.getaddrinfo = getaddrinfo
    _answered = True


def answer_localhost_with_loopback() -> None:
    """For this process, `localhost` and every `*.localhost` name resolve to loopback (RFC 6761
    §6.3), whatever the operating system's resolver does with them — so a host tool reaches the
    proxy with the name intact in its request. Every other name resolves as before."""
    _answer_here()


def _trust(files: list[str]) -> None:
    """Every TLS context this process makes trusts `files` beside the system's own store, and
    accepts a chain that ends at one of them (`VERIFY_X509_PARTIAL_CHAIN`), so the deployment's own
    certificate is trusted even when its root is in no trust store on this server."""
    for file in files:
        if file not in _TRUSTED:
            _TRUSTED.append(file)
    if getattr(ssl.create_default_context, "_osprey_trust", False):
        return
    underlying = ssl.create_default_context

    def create_default_context(*args: Any, **kwargs: Any) -> ssl.SSLContext:
        context = underlying(*args, **kwargs)
        if context.verify_mode != ssl.CERT_NONE:
            for trusted in _TRUSTED:
                context.load_verify_locations(cafile=trusted)
            context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        return context

    create_default_context._osprey_trust = True  # type: ignore[attr-defined]
    ssl.create_default_context = create_default_context
    # `urllib` reaches HTTPS through this one, bound when `ssl` was imported, and its default
    # opener keeps the context it was made with: dropped, so the next request makes a new one.
    ssl._create_default_https_context = create_default_context
    import urllib.request

    urllib.request.install_opener(None)


def answer_the_deployment_here(config: OspreyConfig) -> None:
    """ADR-114 Amendment 33 decision 2: on a Small with the organisation's own certificate, the
    tools run on the server (`harness.apply`, `harness.register_sign_in`) reach the deployment's
    names on this server — at `network.listen_address`, else loopback — before the organisation's
    DNS does, and trust its certificate (and `network.tls.ca`) without the server's own trust store
    knowing the organisation's CA. Nothing changes for any other deployment."""
    tls = config.network.tls
    if config.profile is not Profile.SMALL or tls is None:
        return
    host = sites(config).host.lower()
    address = config.network.listen_address or LOOPBACK
    for name in (host, f"id.{host}", f"bi.{host}"):
        _HERE[name] = address
    _answer_here()
    _trust([tls.certificate, *([tls.ca] if tls.ca else [])])


#: ADR-114 Amendment 41: each deployment name a tool on this server reaches with the pass, and the
#: deployment's folder its key file is read from (at each request, so a key set again mid-run is
#: followed).
_PASSES: dict[str, Path] = {}


def carry_the_pass(config: OspreyConfig, directory: Path) -> None:
    """The tools on the server (`harness.apply`, `harness.register_sign_in`, backup and restore)
    reach a deployment that asks for the shared key as a browser that has answered does: with the
    pass from its key file, which only the file's owner can read. On `urllib`'s requests to the
    deployment's three names alone, never elsewhere. Nothing for a deployment that does not ask."""
    if not config.network.access_key:
        return
    host = sites(config).host.lower()
    for name in (host, f"id.{host}", f"bi.{host}"):
        _PASSES[name] = directory
    import urllib.request

    handler = urllib.request.AbstractHTTPHandler
    if getattr(handler.do_request_, "_osprey_pass", False):
        return
    underlying = handler.do_request_

    def do_request_(self: Any, request: Any) -> Any:
        request = underlying(self, request)
        name = (urlparse(request.full_url).hostname or "").lower()
        directory = _PASSES.get(name)
        if directory is not None and not request.has_header("Cookie"):
            from harness.access_key import PASS_COOKIE, pass_token

            token = pass_token(directory)
            if token is not None:
                request.add_unredirected_header("Cookie", f"{PASS_COOKIE}={token}")
        return request

    do_request_._osprey_pass = True  # type: ignore[attr-defined]
    # `HTTPHandler.http_request` and `HTTPSHandler.https_request` are the function itself, bound
    # when `urllib.request` was imported, so each is replaced as well.
    handler.do_request_ = do_request_  # type: ignore[method-assign]
    urllib.request.HTTPHandler.http_request = do_request_  # type: ignore[method-assign]
    urllib.request.HTTPSHandler.https_request = do_request_  # type: ignore[method-assign]


def _installed(directory: Path) -> OspreyConfig | None:
    """The settings of the rendered deployment in `directory`, from the `osprey.yaml` copy its
    render writes beside `compose.yaml`; None when there is none."""
    path = directory / "osprey.yaml"
    if not path.is_file():
        return None
    import yaml

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return OspreyConfig.model_validate(loaded)


def carry_the_pass_in(directory: Path) -> None:
    """`carry_the_pass` for the rendered deployment in `directory`; nothing when it has no settings,
    they cannot be read, or it does not ask."""
    import yaml

    try:
        config = _installed(directory)
    except (OSError, ValueError, yaml.YAMLError):
        return
    if config is not None:
        carry_the_pass(config, directory)


def forget_the_passes() -> None:
    """For tests: no deployment's pass is carried any more."""
    _PASSES.clear()


def answer_the_deployment_in(directory: Path) -> None:
    """`answer_the_deployment_here` for the rendered deployment in `directory`, from the
    `osprey.yaml` copy its render writes beside `compose.yaml`; nothing when there is none."""
    config = _installed(directory)
    if config is not None:
        answer_the_deployment_here(config)


def deployment_origins(env_file: Path) -> tuple[str, str]:
    """`(glass, identity)` as a rendered deployment's `deployment.env` names them — what every tool
    on the host reaches the deployment at. A deployment rendered before B3 names neither, and is
    answered with its old published ports, so a tool still reaches it until it is reinstalled."""
    # ADR-114 Amendment 41: every tool on the host that reaches the deployment by these names
    # (backup, restore, the sign-in registration) does so with its pass, if it asks for the key.
    carry_the_pass_in(env_file.parent)
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
