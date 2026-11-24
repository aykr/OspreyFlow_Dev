"""The page service's addresses are derived in one place (build id PL7, slice PL7f; ADR-152
Amendment 3, decisions 4 and 7; the owner's rulings of 23 November 2026 and, on the table of cases,
of 24 November 2026: "the table is approved with three changes").

**What is asked, and which case fails if it is broken (rule 12).**

* `harness.page_addresses.derive(config)` returns the page service's issuer, public origin (default
  port removed), identity alias, identity listener's port, trust variable and three sign-in
  variables, or a refusal in plain words, for **every row of the table of cases**
  (`tests/fixtures/page_addresses_cases.json`, one row per case; case 14 refuses IP and bracketed
  origins outright, case 19 refuses an HTTPS origin on the proxy's plain-HTTP port, case 12
  covers every port the proxy publishes): `test_derive_returns_what_the_table_says`.
* **Every renderer reads it and computes none of it.** A refused row is refused by the render in
  the same words, by the same kind of error
  (`test_a_refused_case_is_refused_by_the_render_in_the_same_words`); a derived row renders exactly
  what was derived, in the service's environment, the proxy's alias, the Caddyfile's identity site
  and nowhere else (`test_a_derived_case_is_rendered_as_derived`); and the page service's own
  `config.ts`, run for real by node, starts on every environment the render gives it
  (`test_the_page_service_starts_on_every_derived_case`). No module but `page_addresses.py` holds
  a rule for any of them (`test_no_other_module_computes_an_address`).
* **A planted fault in what `derive` returns is red** at the shape the renderer sees (rule 15): an
  origin with its default port, no extra listener, an alias for the wrong name, a trust variable
  taken away, an issuer on another realm, a refusal that returns a value instead
  (`test_each_planted_fault_is_red`), and the round-9 port clash, which the pure model of Caddy's
  refusal finds here and the real Caddy finds in `test_page_addresses_caddy.py`
  (`test_the_clash_model_is_red_when_the_port_refusal_is_taken_out`). Each is shown clean first,
  red naming what is wrong, clean again.

**What this test walks and reads (the scan map's row is written from this).** It reads one file of
the table, `OspreyFlow_Build/tests/fixtures/page_addresses_cases.json`; it imports the renderers
(`OspreyFlow_Core/harness/`, `OspreyFlow_Core/packages/schemas/`) and `tools.reference_render`
(the helper whose configurations it starts from, with
`OspreyFlow_Build/tests/fixtures/cloud_platform/{development,poc}.yaml`); it runs
`OspreyFlow_Core/apps/pages/server/config.ts` through node; and
`test_no_other_module_computes_an_address` reads the top-level `*.py` files of
`OspreyFlow_Core/harness/` and `OspreyFlow_Core/harness/cloud_platform/__init__.py`, as text, with
no recursion. It writes only to `tmp_path`. It walks no other folder.
"""

from __future__ import annotations

import dataclasses
import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import urlsplit

import pytest
import yaml
from pydantic import ValidationError
from tools import reference_render as ref

from tests.harness.page_addresses_fixtures import (
    A_SECRET,
    BRANDS,
    DERIVED,
    IDS,
    PAGES_CONFIG_TS,
    REFUSED_BY_DERIVE,
    ROWS,
    SECRET_VARIABLE,
    caddyfile_of,
    clash_findings,
    config_of,
    explicit_https_ports,
    identity_site,
    pages_environment,
    render_of,
    resolved,
    tree_of,
)

# ---- what the page service's own config.ts says (run, never emulated) --------------------------

_NODE_ENTRY = """
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const { loadConfig } = await import(pathToFileURL(process.env.PAGES_CONFIG_TS).href);
const cases = JSON.parse(readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map((env) => {
  try { loadConfig(env); return null; } catch (error) { return String(error.message); }
})));
"""


def service_says(environments: list[dict[str, str]]) -> list[str | None]:
    """`loadConfig`'s verdict on each environment: None where the service starts, its own message
    where it throws. Where node cannot be had the test fails: it never passes without asking."""
    import os

    node = shutil.which("node")
    assert node is not None, (
        "node is needed: the page service's real config.ts is run, not emulated"
    )
    done = subprocess.run(
        [node, "--experimental-strip-types", "--input-type=module", "-e", _NODE_ENTRY],
        input=json.dumps(environments),
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PAGES_CONFIG_TS": str(PAGES_CONFIG_TS)},
        timeout=60,
    )
    assert done.returncode == 0, done.stderr
    verdicts: list[str | None] = json.loads(done.stdout)
    assert len(verdicts) == len(environments)
    return verdicts


def service_environment(env: dict[str, str]) -> dict[str, str]:
    """What the container is given beside the addresses: the session secret, made at run time."""
    return {
        **resolved(env),
        "OSPREY_PAGES_SESSION_SECRET": A_SECRET,
        "OSPREY_PAGES_CONDUIT_URL": "http://api:9001",
    }


# ---- 1. derive returns what the table says -----------------------------------------------------


def test_the_table_has_a_row_for_every_case_and_says_what_each_refusal_is() -> None:
    """The table is the owner's, read by three tests: every case 1 to 19 has a row, every row says
    either what is derived, what is refused or that nothing is (the setting off), and an id is used
    once."""
    assert {row["case"] for row in ROWS} >= set(range(1, 20))
    assert len(set(IDS)) == len(IDS)
    for row in ROWS:
        assert len(row["expect"]) >= 1 and set(row["expect"]) <= {"derived", "refuse", "off"}, row[
            "id"
        ]
        if "refuse" in row["expect"]:
            refusal = row["expect"]["refuse"]
            assert refusal["key"] and refusal["error"] and refusal["words"], row["id"]


@pytest.mark.parametrize("row", ROWS, ids=IDS)
def test_derive_returns_what_the_table_says(row: dict[str, Any]) -> None:
    from harness import page_addresses

    expect = row["expect"]
    if "refuse" in expect and expect["refuse"].get("by") == "schema":
        with pytest.raises(ValidationError) as refused:
            config_of(row)
        for word in expect["refuse"]["words"]:
            assert word in str(refused.value)
        return
    config = config_of(row)
    with tree_of(row):
        got = page_addresses.derive(config)
    if "off" in expect:
        assert got is None
        return
    if "refuse" in expect:
        refusal = expect["refuse"]
        assert isinstance(got, page_addresses.Refusal), got
        assert got.key == refusal["key"]
        for word in refusal["words"]:
            assert word in got.words, (word, got.words)
        assert ("pages.enabled" in got.words) is refusal["names_setting"], got.words
        assert type(got.error()).__name__ == refusal["error"]
        assert str(got.error()) == got.words
        return
    want = expect["derived"]
    assert isinstance(got, page_addresses.PageAddresses), got
    assert got.public_origin == want["public_origin"]
    assert got.identity == want["identity"]
    assert got.issuer == want["issuer"]
    assert got.identity_alias == want["identity_alias"]
    assert got.identity_port == want["identity_port"]
    assert got.extra_listener == want["extra_listener"]
    assert got.proxy_https_port == want["proxy_https_port"]
    assert got.trust == want["trust"]
    named = got.environment()
    assert {k: v for k, v in named.items() if k != SECRET_VARIABLE} == want["environment"]
    assert SECRET_VARIABLE in named and named[SECRET_VARIABLE].startswith("${")


def test_the_derived_origin_is_the_origin_the_service_wants() -> None:
    """The service refuses `raw !== new URL(raw).origin`: a default port, an upper-case letter. The
    table's derived origins are held to that here, in words, for every derived row, before node
    is asked (`test_the_page_service_starts_on_every_derived_case` asks it)."""
    for row in DERIVED:
        origin = row["expect"]["derived"]["public_origin"]
        url = urlsplit(origin)
        assert origin == f"{url.scheme}://{url.netloc}", row["id"]
        assert origin == origin.lower(), row["id"]
        assert not origin.endswith((":443", ":80")), row["id"]


def test_the_derive_of_a_setting_that_is_off_asks_nothing_of_the_address() -> None:
    """Off is the reference: a form the service would refuse is not this setting's business."""
    from harness import page_addresses

    [row] = [r for r in ROWS if r["id"] == "0-off"]
    assert page_addresses.derive(config_of(row)) is None
    assert page_addresses.require(config_of(row)) is None


# ---- 2. a refused case is refused by the render, in the same words ---------------------------


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("row", REFUSED_BY_DERIVE, ids=[r["id"] for r in REFUSED_BY_DERIVE])
def test_a_refused_case_is_refused_by_the_render_in_the_same_words(
    row: dict[str, Any], brand: str
) -> None:
    """The render raises the error `derive` names, with `derive`'s words, and writes nothing. (The
    cutover is a GOV.UK deployment by its own brand; the other rows run under both brands.)"""
    from harness import page_addresses

    if row["config"]["brand"] == "govuk" and brand != "govuk":
        pytest.skip("the cutover is a GOV.UK deployment's: it is run under that brand")
    config = config_of(row, brand)
    with tree_of(row):
        refusal = page_addresses.derive(config)
        assert isinstance(refusal, page_addresses.Refusal)
        with pytest.raises(ValueError) as refused:
            render_of(config)
    assert type(refused.value).__name__ == row["expect"]["refuse"]["error"]
    assert str(refused.value) == refusal.words


# ---- 3. a derived case is rendered as derived, and nowhere else ----------------------------------


def _inside_the_key(caddyfile: str, derived: dict[str, Any]) -> list[str]:
    """Where a deployment asks for the shared key: every handler of the page service's host is
    inside the key's `route` (a `handle` or `reverse_proxy` at one tab is outside it), and the
    identity site's open list names the issuer's discovery document, keys and token, built from
    the issuer derived."""
    found: list[str] = []
    host = urlsplit(derived["public_origin"]).hostname
    alias = derived["identity_alias"]
    for name in (host, alias):
        block = _block(caddyfile, name)
        if not block:
            found.append(f"no site block for {name}")
            continue
        if "\troute {" not in block:
            found.append(f"{name} has no route behind the key")
        for line in block.splitlines():
            if re.match(r"^\t(handle|reverse_proxy)\b", line):
                found.append(f"{name}: {line.strip()} is outside the key's route")
    realm = urlsplit(derived["issuer"]).path
    open_on_identity = _block(caddyfile, alias)
    for tail in ("/protocol/openid-connect/token", "/protocol/openid-connect/certs",
                 "/.well-known/openid-configuration"):  # fmt: skip
        if f'"{realm}{tail}"' not in open_on_identity:
            found.append(f"the issuer's {realm}{tail} is not on the key's open list")
    return found


def _block(caddyfile: str, name: str) -> str:
    lines = caddyfile.splitlines()
    for number, line in enumerate(lines):
        if line.endswith("{") and line != "{" and not line.startswith(("\t", " ", "#")):
            if any(urlsplit(a.strip()).hostname == name for a in line[:-1].split(",")):
                end = next(i for i in range(number, len(lines)) if lines[i] == "}")
                return "\n".join(lines[number : end + 1])
    return ""


def findings(row: dict[str, Any], config: Any, artefacts: dict[str, str]) -> list[str]:
    """What is wrong with a render of a derived row, read of its files alone and held to the table:
    the page service's variables, the proxy's alias, the Caddyfile's identity site and the ports it
    names, the key, the clash, and what the page service's real `config.ts` says to the
    environment."""
    want = row["expect"]["derived"]
    found: list[str] = []
    env = pages_environment(row, artefacts)
    if env is None:
        return ["no page service in the render"]
    for name, value in want["environment"].items():
        if env.get(name) != value:
            found.append(f"{name} is {env.get(name)!r}, derived {value!r}")
    held = {"OSPREY_PAGES_PUBLIC_ORIGIN", "OSPREY_PAGES_OIDC_ISSUER", "OSPREY_PAGES_CLIENT_ID",
            "OSPREY_PAGES_CLIENT_SECRET", "NODE_EXTRA_CA_CERTS"}  # fmt: skip
    extra = (set(env) & held) - set(want["environment"]) - {SECRET_VARIABLE}
    if extra:
        found.append(f"the service is given {sorted(extra)}, which nothing derived")
    if SECRET_VARIABLE not in env:
        found.append(f"{SECRET_VARIABLE} is not given")
    caddyfile = caddyfile_of(row, config, artefacts)
    alias = want["identity_alias"]
    site = identity_site(caddyfile, alias)
    wanted_site = want["identity_site"] or [f"https://{alias}"]
    if site != wanted_site:
        found.append(f"the identity site is {site}, derived {wanted_site}")
    named_ports = explicit_https_ports(caddyfile)
    allowed = {want["extra_listener"]} - {None}
    if named_ports - allowed:
        found.append(
            f"the Caddyfile names ports {sorted(named_ports - allowed)} that nothing derived"
        )
    if row["config"]["shape"] in ("local-lite", "small"):
        services = yaml.safe_load(artefacts["compose.yaml"])["services"]
        networks = services["proxy"].get("networks") or {}
        aliases = (
            (networks.get("osprey") or {}).get("aliases", []) if isinstance(networks, dict) else []
        )
        if aliases != [want["proxy_alias"]]:
            found.append(
                f"the proxy's aliases on osprey are {aliases}, derived {[want['proxy_alias']]}"
            )
    found += clash_findings(caddyfile)
    if want.get("behind_the_key"):
        found += _inside_the_key(caddyfile, want)
    [verdict] = service_says([service_environment(env)])
    if verdict is not None:
        found.append(f"the page service refuses what it is given: {verdict}")
    return found


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("row", DERIVED, ids=[r["id"] for r in DERIVED])
def test_a_derived_case_is_rendered_as_derived(row: dict[str, Any], brand: str) -> None:
    config = config_of(row, brand)
    assert findings(row, config, render_of(config)) == []


def test_the_derived_identity_is_the_address_the_deployment_already_names() -> None:
    """`harness.site.sites` names the deployment's addresses for every app (ADR-114 decision 6);
    the page service's identity address is the same string, compared as it is: no port is stripped
    from either side (PL7f round 2: the strip hid case 7, where Keycloak was given `:443` and the
    service was not)."""
    from harness.site import sites

    for row in DERIVED:
        want = row["expect"]["derived"]
        names = sites(config_of(row))
        assert names.identity == want["identity"], row["id"]
        assert names.glass == want["public_origin"], row["id"]
        assert names.identity_host == want["identity_alias"], row["id"]


@pytest.mark.parametrize("row", DERIVED, ids=[r["id"] for r in DERIVED])
def test_the_page_service_starts_on_every_derived_case(row: dict[str, Any]) -> None:
    """The table's own derived environment, run through the page service's real `loadConfig` (the
    same file the node test `pageAddresses.test.ts` calls): the service starts on each."""
    env = {**row["expect"]["derived"]["environment"], SECRET_VARIABLE: A_SECRET}
    [verdict] = service_says([service_environment(env)])
    assert verdict is None, verdict


# ---- 4. no other module computes an address ------------------------------------------------------

#: What only `page_addresses.py` may hold: the names of the service's address variables and what it
#: takes to make them (a URL parser, the `id.` prefix, the proxy's own ports, an IP check).
ADDRESS_VARIABLES = (
    "OSPREY_PAGES_OIDC_ISSUER",
    "OSPREY_PAGES_PUBLIC_ORIGIN",
    "NODE_EXTRA_CA_CERTS",
)
RULES_OF_ADDRESS = ("ipaddress", "urlsplit", "urlparse", 'f"id.', "id.{", "_INTERNAL_SUFFIXES")
#: What any module under `harness/` touches when it works an address out of the deployment's origin
#: (PL7f round 2: the realm's sign-in client read `network.public_origin` itself, and the proxy's
#: module wrote `id.<host>` itself, and the scan looked at neither): the raw setting, and the names
#: that the identity and dashboards sites are made of.
TOUCHES_THE_ORIGIN = (
    "network.public_origin",
    '"public_origin"',
    'f"id.',
    "id.{",
    'f"bi.',
    "bi.{",
    '"id."',
    '"bi."',
)
HARNESS = ref.CORE / "harness"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


#: A module that names a variable the page service is given but computes nothing from it: the
#: Dockerfile-side and apply-side modules that write secrets or list names (none today).
ALLOWED_VARIABLE_READERS: dict[str, tuple[str, ...]] = {}

#: Every other place under `harness/` that touches the origin or the identity name, each with the
#: reason it computes no address. (module path under `harness/`, text on the line) -> reason. A hit
#: not listed here fails; a listing that no longer matches a line fails (no entry outlives its hit).
ORIGIN_TOUCHES_ALLOWED: dict[tuple[str, str], str] = {
    ("webapp.py", '"public_origin": "https://preview.invalid"'): (
        "a fixed placeholder value the set-up page's preview is given, not an address made from a "
        "deployment's origin"
    ),
    ("cloud_platform/__init__.py", "config.network.public_origin.startswith("): (
        "a check that the shape's origin is https (the cloud platform has no proxy, no identity "
        "name and no page-service sign-in until PL7e); it makes no address"
    ),
    ("tls_check.py", 'f"id.osprey.example.internal. Ask the CA for'): (
        "advice in words for a person (an example name in a message), not an address made from a "
        "deployment's origin"
    ),
    ("site.py", "# Rendered from osprey.yaml's network.public_origin"): (
        "a line of text written into the Caddyfile's header, naming the setting; it computes nothing"
    ),
}


def test_no_other_module_computes_an_address() -> None:
    """No module under `harness/` but `page_addresses.py` makes any address of the page service or
    of the deployment's origin: not the page-service render module, not the proxy's, not the
    realm's sign-in clients, not the cloud-platform renderer. Read as text, every module under
    `harness/` (the folder and the ones inside it), so a rule added back anywhere fails here,
    naming the file and the line (rule 12: the sentence 'derive is the only place' is exercised by
    this scan). Every module that touches the origin or the identity name is either reading
    `page_addresses` or listed in `ORIGIN_TOUCHES_ALLOWED` with its reason."""
    problems = scan()
    assert problems == [], problems


def _code_lines(text: str) -> dict[int, str]:
    """The lines of a module's code, by number: comments and docstrings (a module's, a class's, a
    function's) are not code, and a rule written in prose is not a rule held there. A comment at
    the end of a code line is dropped from it (a `#` inside a string is kept: the line is cut at
    the first `#` that has an even number of quotes before it)."""
    import ast

    tree = ast.parse(text)
    prose: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    prose.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
    return {
        number: _without_comment(line)
        for number, line in enumerate(text.splitlines(), start=1)
        if number not in prose
    }


def _without_comment(line: str) -> str:
    for position, character in enumerate(line):
        if character == "#" and line[:position].count('"') % 2 == 0 and (
            line[:position].count("'") % 2 == 0
        ):  # fmt: skip
            return line[:position]
    return line


def _modules() -> list[Path]:
    return sorted(HARNESS.rglob("*.py"))


def scan(overrides: dict[str, str] | None = None) -> list[str]:
    """The findings in every module under `harness/` but `page_addresses.py`, with `overrides`
    (path under `harness/` -> text) standing for a module's content, for the planted cases below."""
    problems: list[str] = []
    matched: set[tuple[str, str]] = set()
    for path in _modules():
        relative = path.relative_to(HARNESS).as_posix()
        if relative == "page_addresses.py":
            continue
        text = (overrides or {}).get(relative) or _read(path)
        for number, code in _code_lines(text).items():
            for variable in ADDRESS_VARIABLES:
                if variable in code and path.name not in ALLOWED_VARIABLE_READERS.get(variable, ()):
                    problems.append(f"{relative}:{number} names {variable}: {code.strip()}")
            if path.name == "pages_service.py":
                for rule in RULES_OF_ADDRESS:
                    if rule in code:
                        problems.append(
                            f"{relative}:{number} holds a rule of address ({rule}): {code.strip()}"
                        )
            if any(touch in code for touch in TOUCHES_THE_ORIGIN):
                listed = [
                    key for key in ORIGIN_TOUCHES_ALLOWED if key[0] == relative and key[1] in code
                ]
                matched.update(listed)
                if not listed:
                    problems.append(
                        f"{relative}:{number} touches the origin or the identity name and neither "
                        f"reads page_addresses nor is listed with a reason: {code.strip()}"
                    )
    if overrides is None:
        problems += [
            f"ORIGIN_TOUCHES_ALLOWED lists {key} but no line matches it"
            for key in ORIGIN_TOUCHES_ALLOWED
            if key not in matched
        ]
    return problems


def test_the_scan_is_red_for_a_rule_put_back_in_the_page_service_module() -> None:
    """Rule 15: the scan finds the shape the old code had (`pages_service.py` working out the alias
    and the origin itself), not a hand-written approximation: the real round-9 lines, put back."""
    real = _read(HARNESS / "pages_service.py")
    planted = real + (
        "\n\ndef identity_alias(config):\n    from harness.site import sites\n"
        '    return f"id.{sites(config).host}"\n'
        "\n\ndef a_port(config):\n    from urllib.parse import urlsplit\n"
        "    return urlsplit(config.network.public_origin).port\n"
    )
    assert scan() == []
    found = scan({"pages_service.py": planted})
    assert any("holds a rule of address (urlsplit)" in line for line in found), found
    assert any("holds a rule of address" in line and "id." in line for line in found), found
    assert scan() == []


# ---- 5. a planted fault in what derive returns is red ---------------------------------------


def _alter(**changes: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """`derive`, as the renderers call it, with a field of the object it returns changed: the shape
    the code under test really sees (a `PageAddresses`), not a hand-written stand-in."""
    from harness import page_addresses

    def wrapper(real: Callable[..., Any]) -> Callable[..., Any]:
        def planted(config: Any, **kwargs: Any) -> Any:
            got = real(config, **kwargs)
            if not isinstance(got, page_addresses.PageAddresses):
                return got
            made = {k: (v(got) if callable(v) else v) for k, v in changes.items()}
            return dataclasses.replace(got, **made)

        return planted

    return wrapper


def _with_planted_derive(wrapper: Any) -> Any:
    from harness import page_addresses

    return mock.patch.object(page_addresses, "derive", wrapper(page_addresses.derive))


PLANTS: list[tuple[str, str, Any, str]] = [
    # (plant, the row it is made to, what changes in the returned object, what the finding says)
    ("a default port kept on the origin", "7-acme-explicit-443",
     {"public_origin": lambda got: got.public_origin + ":443"}, "must be the origin alone"),
    ("no extra listener where the alias needs one", "4-own-certificate-with-ca",
     {"extra_listener": None}, "the identity site is"),
    ("a listener on another port than the issuer's", "11-own-certificate-9443",
     {"extra_listener": 9999}, "the identity site is"),
    ("the alias for another name", "3-acme-default-port",
     {"identity_alias": "id.other.example.org"}, "the proxy's aliases on osprey"),
    ("the trust variable taken away", "4-own-certificate-with-ca",
     {"trust": None}, "NODE_EXTRA_CA_CERTS is None"),
    ("an issuer on another realm", "15-access-key-acme",
     {"issuer": lambda got: got.issuer.replace("/realms/osprey", "/realms/other")},
     "OSPREY_PAGES_OIDC_ISSUER is 'https://id.osprey.example.org/realms/other'"),
]  # fmt: skip


@pytest.mark.parametrize(("plant", "row_id", "changes", "says"), PLANTS, ids=[p[0] for p in PLANTS])
def test_each_planted_fault_is_red(plant: str, row_id: str, changes: Any, says: str) -> None:
    """Each fault is made in the object `derive` returns, which every renderer reads, so a renderer
    that computed any of it itself would not carry the fault and the check would not find it: clean
    first, red naming what is wrong, clean again."""
    [row] = [r for r in ROWS if r["id"] == row_id]
    config = config_of(row)
    assert findings(row, config, render_of(config)) == []
    with _with_planted_derive(_alter(**changes)):
        found = findings(row, config, render_of(config))
    assert any(says in line for line in found), f"{plant}: {found}"
    assert findings(row, config, render_of(config)) == []


@pytest.mark.parametrize(
    ("row_id", "says"),
    [
        ("1-lite-plain-http", "must be an https address"),
        ("8-lite-plain-http-explicit-80", "must be the origin alone"),
    ],
)
def test_a_refusal_that_returns_a_value_instead_is_red(row_id: str, says: str) -> None:
    """The plain-HTTP refusals planted as a pass: `derive` returns the values the deployment's own
    addresses make (`harness.site.sites`), so the page service is given an `http` issuer that is not
    loopback, or an origin with its default port, which its real check refuses. The refusal is
    the only thing between that deployment and a service that cannot start."""
    from harness import page_addresses
    from harness.site import sites

    [row] = [r for r in ROWS if r["id"] == row_id]
    config = config_of(row)

    def derive_a_pass(real: Callable[..., Any]) -> Callable[..., Any]:
        def planted(config: Any, **kwargs: Any) -> Any:
            got = real(config, **kwargs)
            if not isinstance(got, page_addresses.Refusal):
                return got
            names = sites(config)
            issuer = f"{names.identity}/realms/osprey"
            # The fault planted: the origin as the deployment wrote it, its default port kept.
            return page_addresses.PageAddresses(
                public_origin=config.network.public_origin.rstrip("/"),
                identity=names.identity,
                issuer=issuer,
                identity_alias=f"id.{names.host}",
                identity_port=names.port,
                extra_listener=None,
                proxy_https_port=None,
                trust=None,
            )

        return planted

    with pytest.raises(ValueError):
        render_of(config)
    with _with_planted_derive(derive_a_pass):
        artefacts = render_of(config)
    env = pages_environment(row, artefacts)
    assert env is not None
    [verdict] = service_says([service_environment(env)])
    assert verdict is not None and says in verdict, verdict
    with pytest.raises(ValueError):
        render_of(config)


#: The rows where the round-9 clash is real: the identity listener the render adds lands on a
#: port the same Caddyfile serves as plain HTTP.
CLASH_ROWS = [
    "9-own-certificate-8080",
    "12-own-certificate-graph-store-door",
    "12-own-certificate-conduit-door",
    "12-acme-plain-http-port",
    "12-acme-graph-store-door",
    "12-acme-conduit-door",
]


@pytest.mark.parametrize("row_id", CLASH_ROWS)
def test_the_clash_model_is_red_when_the_port_refusal_is_taken_out(row_id: str) -> None:
    """Round 9's fault at the shape the renderer writes it: `derive`'s port refusal replaced by a
    pass, so the identity site is given a second `https://` address on a port the same file serves
    as plain HTTP. The pure model finds the port; it is clean with the refusal back. (This is the
    fast check. The real Caddy is asked the same in `test_page_addresses_caddy.py`.)"""
    from harness import page_addresses

    [row] = [r for r in ROWS if r["id"] == row_id]
    config = config_of(row)
    with pytest.raises(ValueError):
        render_of(config)
    with mock.patch.object(page_addresses, "_port_taken", lambda *a, **k: None):
        caddyfile = render_of(config)["Caddyfile"]
    port = row["config"]["origin"].rsplit(":", 1)[1]
    assert f"https://id.osprey.example.org:{port}" in caddyfile
    found = clash_findings(caddyfile)
    assert any(f"port {port} is served as plain HTTP and as HTTPS" in line for line in found), found
    with pytest.raises(ValueError):
        render_of(config)


@pytest.mark.parametrize("tail", ["/token", "/certs", "/.well-known/openid-configuration"])
def test_the_key_check_is_red_when_the_issuers_fetch_is_not_on_the_open_list(tail: str) -> None:
    """The issuer's discovery document, keys and token are what the service fetches from its own
    origin, where no credential and no cookie is sent: each must be on the key's open list, or a
    deployment that asks for the key cannot sign anyone in. The open list taken out one path at a
    time, at the shape the renderer writes it (the constant `render_caddyfile` reads)."""
    from harness import site

    [row] = [r for r in ROWS if r["id"] == "15-access-key-acme"]
    config = config_of(row)
    assert findings(row, config, render_of(config)) == []
    listed = tuple(p for p in site.OPEN_ON_THE_IDENTITY_PROVIDER if not p.endswith(tail))
    assert len(listed) == len(site.OPEN_ON_THE_IDENTITY_PROVIDER) - 1
    with mock.patch.object(site, "OPEN_ON_THE_IDENTITY_PROVIDER", listed):
        found = findings(row, config, render_of(config))
    assert any(f"{tail}" in line and "is not on the key's open list" in line for line in found), found
    assert findings(row, config, render_of(config)) == []


def test_the_scan_is_red_for_the_lines_the_realm_and_the_proxy_module_held() -> None:
    """Rule 15, PL7f round 2: the two places the first scan did not look at. The lines put back are
    the real ones the verifier found: the realm's sign-in client reading the raw setting
    (`origin = config.network.public_origin`), and the proxy's module writing the identity name
    itself (`f"id.{names.host}"`). Each is found, naming its file; the real modules are clean."""
    realm = _read(HARNESS / "realm.py")
    site = _read(HARNESS / "site.py")
    assert scan() == []
    found = scan(
        {
            "realm.py": realm + "\n\ndef old(config):\n    origin = config.network.public_origin\n",
            "site.py": site
            + '\n\ndef old(names):\n    return [(names.host, 1), (f"id.{names.host}", "keycloak:8080")]\n',
        }
    )
    assert any(line.startswith("realm.py:") and "public_origin" in line for line in found), found
    assert any(line.startswith("site.py:") and "id." in line for line in found), found
    assert scan() == []


# ---- 6. Keycloak's issuer, the realm client's redirect and the service's settings are one string


def _compose_value(artefacts: dict[str, str], service: str, name: str) -> str | None:
    services = yaml.safe_load(artefacts["compose.yaml"])["services"]
    found = (services.get(service) or {}).get("environment", {}).get(name)
    return None if found is None else str(found)


def _env_file_value(artefacts: dict[str, str], name: str) -> str | None:
    for line in artefacts["deployment.env"].splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1]
    return None


def agreement_findings(
    row: dict[str, Any], config: Any, artefacts: dict[str, str], client: dict[str, Any]
) -> list[str]:
    """Where one deployment writes the same address in different places, the strings are equal:
    what the page service is given (origin and issuer), what Keycloak publishes (`KC_HOSTNAME` and
    the realm: the issuer; compose shapes, which run Keycloak), what the deployment's own address
    file says (`OSPREY_GLASS_ORIGIN`, `OSPREY_IDENTITY_ORIGIN`) and what the realm client registers
    (redirect, web origin and post-logout address). No comparison strips or changes a string."""
    env = pages_environment(row, artefacts)
    if env is None:
        return ["no page service in the render"]
    origin = env["OSPREY_PAGES_PUBLIC_ORIGIN"]
    issuer = env["OSPREY_PAGES_OIDC_ISSUER"]
    found: list[str] = []
    if client.get("redirectUris") != [f"{origin}/session/callback"]:
        found.append(
            f"the realm client's redirect is {client.get('redirectUris')}, the service sends "
            f"{origin}/session/callback"
        )
    if client.get("webOrigins") != [origin]:
        found.append(f"the realm client's web origin is {client.get('webOrigins')}, not {origin}")
    if client.get("attributes", {}).get("post.logout.redirect.uris") != f"{origin}/":
        found.append(f"the realm client's post-logout address is not {origin}/")
    if row["config"]["shape"] in ("local-lite", "small"):
        hostname = _compose_value(artefacts, "keycloak", "KC_HOSTNAME")
        if f"{hostname}/realms/osprey" != issuer:
            found.append(
                f"Keycloak publishes {hostname}/realms/osprey, the service is given {issuer}"
            )
        if _env_file_value(artefacts, "OSPREY_IDENTITY_ORIGIN") != hostname:
            found.append("OSPREY_IDENTITY_ORIGIN is not the identity address Keycloak is given")
        if _env_file_value(artefacts, "OSPREY_GLASS_ORIGIN") != origin:
            found.append(
                f"OSPREY_GLASS_ORIGIN is {_env_file_value(artefacts, 'OSPREY_GLASS_ORIGIN')}, "
                f"the service is given {origin}"
            )
    return found


def _client_of(config: Any) -> dict[str, Any]:
    from harness.realm import pages_client

    return pages_client(config)


@pytest.mark.parametrize("row", DERIVED, ids=[r["id"] for r in DERIVED])
def test_keycloaks_issuer_the_realm_client_and_the_service_agree(row: dict[str, Any]) -> None:
    """For every derived case: the issuer Keycloak will publish, the realm client's redirect, web
    origin and post-logout address, and the page service's origin and issuer are the same strings,
    compared as they are (rule 12: the sentence 'one place derives every address' was held by
    nothing that compared the realm's registration with the service's callback)."""
    config = config_of(row)
    assert agreement_findings(row, config, render_of(config), _client_of(config)) == []


def _row(row_id: str) -> dict[str, Any]:
    [row] = [r for r in ROWS if r["id"] == row_id]
    return row


def _the_client_as_it_was(config: Any) -> dict[str, Any]:
    """The client as the realm module made it before round 2: the origin as the deployment wrote it
    (`config.network.public_origin`, the real old line), in all three fields."""
    origin = config.network.public_origin
    client = dict(_client_of(config))
    client["redirectUris"] = [f"{origin}/session/callback"]
    client["webOrigins"] = [origin]
    client["attributes"] = {**client["attributes"], "post.logout.redirect.uris": f"{origin}/"}
    return client


@pytest.mark.parametrize(
    ("row_id", "says"),
    [
        ("7-acme-explicit-443", "the realm client's redirect is"),
        ("7-own-certificate-explicit-443", "the realm client's redirect is"),
        ("14-upper-case-host", "the realm client's web origin is"),
    ],
)
def test_the_verifiers_cases_7_and_14_are_red_for_the_client_as_it_was(
    row_id: str, says: str
) -> None:
    """Rule 15: the verifier's two worked cases, at the shape the old code produced: case 7 has the
    realm register `:443` the service never sends, case 14 an upper-case origin. Clean first, red
    naming the mismatch, clean again."""
    row = _row(row_id)
    config = config_of(row)
    artefacts = render_of(config)
    assert agreement_findings(row, config, artefacts, _client_of(config)) == []
    found = agreement_findings(row, config, artefacts, _the_client_as_it_was(config))
    assert any(says in line for line in found), found
    assert agreement_findings(row, config, artefacts, _client_of(config)) == []


def test_keycloak_given_the_port_the_service_is_not_is_red() -> None:
    """The other half of the strip the first version of this test hid: Keycloak's `KC_HOSTNAME` as
    the old `sites()` wrote it for case 7 (the address with `:443`, the real old shape) against the
    issuer the service is given."""
    row = _row("7-acme-explicit-443")
    config = config_of(row)
    artefacts = render_of(config)
    assert "KC_HOSTNAME: https://id.osprey.example.org\n" in artefacts["compose.yaml"]
    planted = dict(artefacts)
    planted["compose.yaml"] = artefacts["compose.yaml"].replace(
        "KC_HOSTNAME: https://id.osprey.example.org\n",
        "KC_HOSTNAME: https://id.osprey.example.org:443\n",
    )
    found = agreement_findings(row, config, planted, _client_of(config))
    assert any(line.startswith("Keycloak publishes") for line in found), found
    assert agreement_findings(row, config, artefacts, _client_of(config)) == []


@pytest.mark.parametrize(
    ("row_id", "change"),
    [
        ("3-acme-default-port", lambda got: got.public_origin.upper()),
        ("7-acme-explicit-443", lambda got: got.public_origin + ":443"),
        ("14-upper-case-host", lambda got: got.public_origin + ":8443"),
    ],
    ids=["upper case", "a default port", "another port"],
)
def test_a_planted_change_to_derives_public_origin_turns_a_case_red(
    row_id: str, change: Callable[[Any], str]
) -> None:
    """A change to what `derive` returns as the public origin reaches the service's settings and
    the realm client (both read it) and not the deployment's own address file or Keycloak: the case
    goes red, so a place that stopped reading `derive` would be found by the other places that
    still do. Made in the object `derive` returns, the shape every reader sees."""
    row = _row(row_id)
    config = config_of(row)
    assert agreement_findings(row, config, render_of(config), _client_of(config)) == []
    with _with_planted_derive(_alter(public_origin=change)):
        planted_client = _client_of(config)
        found = agreement_findings(row, config, render_of(config), planted_client)
    assert any("OSPREY_GLASS_ORIGIN" in line for line in found), found
    assert agreement_findings(row, config, render_of(config), _client_of(config)) == []


def test_the_realm_client_reads_derive_where_the_service_is_on() -> None:
    """The realm client's origin is `derive`'s where the setting is on: a changed `derive` changes
    the client (a client that worked the origin out for itself would not move)."""
    row = _row("3-acme-default-port")
    config = config_of(row)
    with _with_planted_derive(_alter(public_origin="https://planted.example.org")):
        client = _client_of(config)
    assert client["redirectUris"] == ["https://planted.example.org/session/callback"]
    assert client["webOrigins"] == ["https://planted.example.org"]
    assert client["attributes"]["post.logout.redirect.uris"] == "https://planted.example.org/"
