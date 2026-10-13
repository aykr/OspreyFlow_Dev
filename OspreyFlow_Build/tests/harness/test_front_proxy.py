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
  `test_a_localhost_name_reaches_loopback_where_the_resolver_refuses_it`.
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
    assert published == {"proxy": ["80:8080", "127.0.0.1:${OSPREY_ARCADEDB_PORT:-2480}:2480"]}
    # The Conduit only when an operator opts in — through the proxy too.
    opted = _compose(_render(network={"expose_conduit": True}))
    assert {n for n, s in opted.items() if s.get("ports")} == {"proxy"}
    assert "${OSPREY_API_PORT:-8000}:8000" in opted["proxy"]["ports"]


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
    assert _compose(_render("http://a.test:8443"))["proxy"]["ports"][0] == "8443:8080"
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
        "welcome": {"about": True, "links": {}},
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
