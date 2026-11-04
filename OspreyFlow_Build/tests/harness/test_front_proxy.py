"""One address per app behind one front proxy (`06_DECISIONS.md` ADR-114 decision 6, Amendment 4).

Before B3 the browser used a port per app — the Glass on 8080, Keycloak on 8081, Superset on 8088 —
and the Glass found Keycloak by adding 8081 to its own host. Now Caddy routes by name: the Glass at
the base name, Keycloak at `id.`, Superset at `bi.`, every address derived from
`network.public_origin`, and nothing else published.

What a mistake would do, and the case that catches it:
- an app still published beside the proxy — `test_only_the_proxy_is_published`;
- a name routed to the wrong service, or to Superset when it is off —
  `test_each_name_reaches_its_service`;
- an address that disagrees with the origin's scheme or port —
  `test_every_address_derives_from_the_public_origin`;
- Keycloak naming the issuer after whichever door a request came in by —
  `test_keycloak_names_one_issuer`;
- the Glass's identity provider fixed at build time, or the file not mounted —
  `test_the_glass_learns_its_identity_provider_at_run_time`;
- Superset or the Conduit left on the old ports — `test_superset_origins_are_the_derived_names`;
- a host tool that needs the operating system to resolve `*.localhost` —
  `test_a_localhost_name_reaches_loopback_where_the_resolver_refuses_it`;
- a Lite port published on every network interface, so another machine on the network reaches the
  Glass in plain HTTP (GDS re-audit finding S10, the owner's ruling of 2 November 2026) —
  `test_no_lite_published_port_binds_every_interface`;
- Small or Enterprise moved onto loopback too, so nobody can reach them —
  `test_small_still_publishes_80_and_443_on_every_interface`.
"""

from __future__ import annotations

import json
import socket
from typing import Any

import pytest
import yaml
from harness import site
from harness.render import render

from schemas.deployment import OspreyConfig


def _resolver(_image: object) -> str:
    return "sha256:" + "0" * 64


def _render(origin: str = "http://ospreyflow.localhost", **extra: Any) -> dict[str, str]:
    raw: dict[str, Any] = {
        "network": {"public_origin": origin, **extra.pop("network", {})},
        "reporting": {"sync": True, "superset": True},
        **extra,
    }
    return render(OspreyConfig.model_validate(raw), resolver=_resolver).artefacts


def _compose(artefacts: dict[str, str]) -> dict[str, Any]:
    return yaml.safe_load(artefacts["compose.yaml"])["services"]


def _env(artefacts: dict[str, str]) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in artefacts["deployment.env"].splitlines()
        if "=" in line and not line.startswith("#")
    )


def test_only_the_proxy_is_published() -> None:
    services = _compose(_render())
    published = {name: s["ports"] for name, s in services.items() if s.get("ports")}
    # ADR-114 Amendment 7: the proxy alone publishes — the public origin, and the graph store's door
    # on this machine only (Amendment 4 decision 3), which the proxy now serves.
    # S10: on this computer only.
    assert published == {"proxy": ["127.0.0.1:80:8080", "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480"]}
    # The Conduit only when an operator opts in — through the proxy too.
    opted = _compose(_render(network={"expose_conduit": True}))
    assert {n for n, s in opted.items() if s.get("ports")} == {"proxy"}
    assert "127.0.0.1:${OSPREY_API_PORT:-8000}:8000" in opted["proxy"]["ports"]


#: Each Lite shape the renderer can be asked for: the default, a named deployment's own port
#: (ADR-138), an HTTPS `localhost` origin, the Conduit's door opened, and dashboards on.
_LITE_SHAPES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("http://ospreyflow.localhost", {}),
    ("http://alpha.localhost:8090", {"deployment": {"name": "alpha", "graph_port": 2503}}),
    ("https://osprey.localhost", {}),
    ("http://ospreyflow.localhost", {"network": {"expose_conduit": True}}),
)


def _bound_to_every_interface(mapping: str) -> bool:
    """A compose `ports` entry with no bind address (`HOST:CONTAINER`, its host side perhaps
    `${VAR:-n}`) or an explicit wildcard one: Docker publishes it on every interface."""
    if mapping.startswith(("0.0.0.0:", "[::]:", "::")):
        return True
    return not mapping.startswith(("127.0.0.1:", "[::1]:"))


@pytest.mark.parametrize(("origin", "extra"), _LITE_SHAPES)
def test_no_lite_published_port_binds_every_interface(origin: str, extra: dict[str, Any]) -> None:
    """S10 (GDS re-audit, the owner's ruling of 2 November 2026): Lite answers on this computer
    only. A bare `80:8080` let a machine on the same network send `Host: ospreyflow.localhost` and
    reach the Glass and sign-in in plain HTTP; so every port Lite publishes, the front proxy's and
    the Conduit's door included, is bound to `127.0.0.1`."""
    services = _compose(_render(origin, **{k: dict(v) for k, v in extra.items()}))
    published = [(name, str(m)) for name, s in services.items() for m in s.get("ports") or []]
    assert published, "the proxy publishes at least the origin's port"
    wide = [(name, m) for name, m in published if _bound_to_every_interface(m)]
    assert wide == [], f"published on every network interface: {wide}"


def test_small_still_publishes_80_and_443_on_every_interface() -> None:
    """Small is reached by other people over a network, so its front proxy must answer on every
    interface: 80 for the certificate's challenge and the move to HTTPS, 443 for the service."""
    services = _compose(_render("https://osprey.example.org", profile="small"))
    assert services["proxy"]["ports"][:2] == ["80:80", "443:443"]
    assert "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480" in services["proxy"]["ports"]


def test_each_name_reaches_its_service() -> None:
    caddyfile = _render()["Caddyfile"]
    routes = site.routes(caddyfile)
    assert routes == {
        "ospreyflow.localhost": "workspace:8080",
        "id.ospreyflow.localhost": "keycloak:8080",
        "bi.ospreyflow.localhost": "superset:8088",
    }
    assert "admin off" in caddyfile
    without = render(
        OspreyConfig.model_validate({"network": {"public_origin": "http://ospreyflow.localhost"}}),
        resolver=_resolver,
    ).artefacts
    assert "bi.ospreyflow.localhost" not in site.routes(without["Caddyfile"])


def test_every_address_derives_from_the_public_origin() -> None:
    names = site.sites(OspreyConfig.model_validate({"network": {"public_origin": "http://a.test:8443"}}))
    assert (names.glass, names.identity, names.dashboards) == (
        "http://a.test:8443", "http://id.a.test:8443", "http://bi.a.test:8443"
    )  # fmt: skip
    assert names.port == 8443
    assert _compose(_render("http://a.test:8443"))["proxy"]["ports"][0] == "127.0.0.1:8443:8080"
    secure = site.sites(OspreyConfig.model_validate({"network": {"public_origin": "https://osprey.example.org"}}))
    assert (secure.identity, secure.port) == ("https://id.osprey.example.org", 443)
    assert site.sites(OspreyConfig()).glass == "http://ospreyflow.localhost", "the Lite default"


def test_keycloak_names_one_issuer() -> None:
    environment = _compose(_render())["keycloak"]["environment"]
    assert environment["KC_HOSTNAME"] == "http://id.ospreyflow.localhost"
    assert environment["KC_HOSTNAME_BACKCHANNEL_DYNAMIC"] == "true"
    assert environment["KC_PROXY_HEADERS"] == "xforwarded"


def test_the_glass_learns_its_identity_provider_at_run_time() -> None:
    artefacts = _render("http://a.test:8443")
    assert json.loads(artefacts["glass.json"]) == {
        "identity_provider": "http://id.a.test:8443",
        "realm": "osprey",
        # ADR-115 decision 2: the marking a surface with no case data shows; the scheme's lowest
        # when the deployment names none.
        "marking": "PUBLIC",
        # ADR-115 decisions 3 and 8: no organisation sign-in until one is configured; About on, and
        # no footer link the deployment has not given.
        "organisation_sign_in": None,
        # ADR-115 Amendment 5: and so no provider's label for its button.
        "organisation_label": None,
        "welcome": {"about": True, "links": {}},
        # ADR-132: the OspreyFlow brand unless the deployment names another.
        "appearance": {
            "brand": "ospreyflow",
            "service_name": None,
            "organisation": None,
            "phase": "none",
        },
        "version": site.deployment_version(),
    }
    volumes = _compose(artefacts)["workspace"]["volumes"]
    assert "./glass.json:/usr/share/nginx/html/deployment.json:ro" in volumes


def test_the_marking_floor_is_the_deployments_own_and_one_its_scheme_knows() -> None:
    """ADR-115 decision 2: the welcome page, Home, the Studio and the Admin area show the deployment's
    marking; inside a case the strip shows that or the highest on screen, whichever is higher."""
    artefacts = _render(governance={"marking": "OFFICIAL"})
    assert json.loads(artefacts["glass.json"])["marking"] == "OFFICIAL"
    with pytest.raises(ValueError, match="TOP SECRET.*PUBLIC, OFFICIAL, OFFICIAL-SENSITIVE, SECRET"):
        _render(governance={"marking": "TOP SECRET"})


def test_the_welcome_page_learns_its_sign_in_about_and_links_from_the_deployment() -> None:
    """ADR-115 decisions 3 and 8: organisation sign-in appears only when a brokered provider is
    named; About can be switched off; each footer link appears only when its address is given."""
    settings = json.loads(
        _render(
            governance={"organisation_sign_in": "acme-entra"},
            welcome={"about": False, "account_help": "https://help.acme.test/osprey"},
        )["glass.json"]
    )
    assert settings["organisation_sign_in"] == "acme-entra"
    assert settings["welcome"] == {"about": False, "links": {"account_help": "https://help.acme.test/osprey"}}
    with pytest.raises(ValueError, match="privacy"):
        _render(welcome={"privacy": "javascript:alert(1)"})
    assert len(site.deployment_version()) >= 7


def test_superset_origins_are_the_derived_names() -> None:
    env = _env(_render())
    assert env["SUPERSET_PUBLIC_ORIGIN"] == "http://bi.ospreyflow.localhost"
    assert env["SUPERSET_IDP_PUBLIC"] == "http://id.ospreyflow.localhost/realms/osprey"
    assert env["SUPERSET_GLASS_ORIGIN"] == "http://ospreyflow.localhost"
    assert env["CORS_ALLOWED_ORIGINS"] == "http://ospreyflow.localhost"
    assert env["OSPREY_IDENTITY_ORIGIN"] == "http://id.ospreyflow.localhost"
    assert env["OSPREY_GLASS_ORIGIN"] == "http://ospreyflow.localhost"
    assert not any(key in env for key in ("OSPREY_KEYCLOAK_PORT", "OSPREY_WORKSPACE_PORT", "OSPREY_SUPERSET_PORT"))


def test_a_localhost_name_reaches_loopback_where_the_resolver_refuses_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fake resolver refuses every `*.localhost` name, as a resolver that does not special-case
    them does (Windows' is not measured); every other name it answers."""
    asked: list[str] = []

    def resolver(host: str, port: object, *args: object, **kwargs: object) -> list[Any]:
        asked.append(host)
        if str(host).endswith(".localhost"):
            raise socket.gaierror(socket.EAI_NONAME, "nodename nor servname provided")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.7", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("id.ospreyflow.localhost", 80)
    site.answer_localhost_with_loopback()
    answers = socket.getaddrinfo("id.ospreyflow.localhost", 80, type=socket.SOCK_STREAM)
    assert {a[4][0] for a in answers} <= {"127.0.0.1", "::1"} and answers
    assert socket.getaddrinfo("example.org", 80)[0][4][0] == "192.0.2.7", "other names untouched"
    site.answer_localhost_with_loopback()  # twice is harmless
    assert socket.getaddrinfo("LOCALHOST", 80, type=socket.SOCK_STREAM)[0][4][0] in ("127.0.0.1", "::1")


def test_the_glass_learns_the_deployments_appearance() -> None:
    """ADR-132: the brand, and what the page title, GOV.UK footer and phase banner name, travel in
    the same file as the identity provider, so the bundle stays the same for every deployment."""
    appearance = {
        "brand": "govuk",
        "service_name": "Prison Intelligence",
        "organisation": "Ministry of Examples",
        "phase": "beta",
    }
    assert json.loads(_render(appearance=appearance)["glass.json"])["appearance"] == appearance
    with pytest.raises(ValueError, match="brand"):
        _render(appearance={"brand": "gov.uk"})
    with pytest.raises(ValueError, match="phase"):
        _render(appearance={"phase": "gamma"})


# ---- ADR-114 Amendment 33 (drop 1): Small on a server of your own, its own certificate ----------

_OWN = {"certificate": "/etc/ospreyflow/tls/osprey.crt", "key": "/etc/ospreyflow/tls/osprey.key"}
_SERVER = "https://osprey.example.internal"


def _own(**network: Any) -> dict[str, str]:
    return _render(_SERVER, profile="small", network={"tls": _OWN, **network})


def test_a_small_with_its_own_certificate_publishes_443_alone_on_every_interface() -> None:
    """Decision 2: 443 on every interface, the graph store's door on loopback, and nothing else —
    no port 80 (the certificate is not obtained, so there is no challenge to answer)."""
    proxy = _compose(_own())["proxy"]
    wide = [m for m in proxy["ports"] if _bound_to_every_interface(m)]
    assert wide == ["443:8443"], proxy["ports"]
    assert not any(m.split(":")[-1] in ("80", "8080") for m in proxy["ports"])
    # One interface of a server with several, when asked.
    chosen = _compose(_own(listen_address="192.0.2.10"))["proxy"]["ports"]
    assert "192.0.2.10:443:8443" in chosen and "443:8443" not in chosen
    # An address on another port publishes that port.
    other = _render("https://osprey.example.internal:9443", profile="small",
                    network={"tls": _OWN})  # fmt: skip
    assert "9443:8443" in _compose(other)["proxy"]["ports"]


def test_port_80_is_published_only_to_redirect_when_asked() -> None:
    assert not any(":8080" in m for m in _compose(_own())["proxy"]["ports"])
    asked = _own(redirect_http=True)
    assert "80:8080" in _compose(asked)["proxy"]["ports"]
    caddyfile = asked["Caddyfile"]
    # Each name's plain-HTTP request is sent to its https:// address, and nothing more.
    for name in ("osprey.example.internal", "id.osprey.example.internal",
                 "bi.osprey.example.internal"):  # fmt: skip
        block = caddyfile.split(f"http://{name} {{", 1)[1].split("\n}", 1)[0]
        assert f"redir https://{name}{{uri}} 308" in block, block
        assert "reverse_proxy" not in block
    assert "http://osprey.example.internal {" not in _own()["Caddyfile"]


def test_the_conduits_door_is_on_loopback_on_a_self_contained_small() -> None:
    ports = _compose(_own(expose_conduit=True))["proxy"]["ports"]
    assert "127.0.0.1:${OSPREY_API_PORT:-8000}:8000" in ports, ports
    assert "${OSPREY_API_PORT:-8000}:8000" not in ports


def test_the_graph_stores_door_stays_on_loopback_on_a_self_contained_small() -> None:
    ports = _compose(_own())["proxy"]["ports"]
    assert "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480" in ports


def test_its_own_certificate_turns_acme_and_ocsp_stapling_off() -> None:
    caddyfile = _own()["Caddyfile"]
    globals_ = caddyfile.split("{", 1)[1].split("}", 1)[0]
    for option in ("admin off", "persist_config off", "auto_https off", "ocsp_stapling off",
                   "https_port 8443", "http_port 8080"):  # fmt: skip
        assert option in globals_, globals_
    compose = yaml.safe_load(_own()["compose.yaml"])
    assert "proxy-data" not in (compose.get("volumes") or {})
    assert not any("proxy-data" in str(v) for v in compose["services"]["proxy"].get("volumes", []))


def test_every_name_is_served_with_the_given_certificate() -> None:
    artefacts = _own()
    caddyfile = artefacts["Caddyfile"]
    for name in ("osprey.example.internal", "id.osprey.example.internal",
                 "bi.osprey.example.internal"):  # fmt: skip
        block = caddyfile.split(f"https://{name} {{", 1)[1]
        assert block.lstrip().startswith("tls /certs/cert.pem /certs/key.pem"), block[:120]
    volumes = _compose(artefacts)["proxy"]["volumes"]
    assert "/etc/ospreyflow/tls/osprey.crt:/certs/cert.pem:ro" in volumes
    assert "/etc/ospreyflow/tls/osprey.key:/certs/key.pem:ro" in volumes
    # The key is mounted from where it is, never copied into the deployment's folder.
    assert not any(name.endswith((".key", ".pem", ".crt")) for name in artefacts)


def test_the_proxy_runs_unprivileged_with_its_own_certificate() -> None:
    proxy = _compose(_own())["proxy"]
    assert proxy["user"] == "${OSPREY_PROXY_UID:?}:${OSPREY_PROXY_GID:?}"
    assert proxy["environment"]["XDG_DATA_HOME"].startswith("/tmp/")
    assert proxy["healthcheck"]["test"][-1] == "http://127.0.0.1:8080/healthz"
