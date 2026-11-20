"""No address outside the deployment in what the deployment serves (build id SE6, slice a, pure).

What is proved here, and what is not (rule 12; the owner's order of 20 November 2026, after DOC1a):

- **Superset's content-security policy names no host outside the deployment** in any directive. The
  policy is loaded as Superset loads it (`deploy/superset/superset_config.py`, with Superset and
  Flask-AppBuilder stubbed, from the environment the render writes), so a host added to a directive
  on the way to the browser turns this red. The two outside hosts the file carried until SE6
  (Scarf's image hosts, Mapbox's connection hosts) are each planted back, in the directive they
  were in, and found.
- **The built policy replaces the shipped one.** `from superset_config import *` rebinds the name
  `TALISMAN_CONFIG`; Superset 6.1.0 does not merge the two dictionaries (read in the pinned image,
  `superset/initialization/__init__.py` line 894: it takes `TALISMAN_DEV_CONFIG` when Flask's debug
  or `DEBUG` is on, otherwise `TALISMAN_CONFIG`). The shipped policy of that version names Scarf,
  Mapbox, Terrestris, Document360, OpenStreetMap, OpenStreetMap Switzerland, Carto and the font
  domains. Because debug mode would take the shipped *development* policy, this file's own
  development policy is checked as well.
- **No Mapbox key is set**, in the loaded configuration or in either profile's rendered environment.
- **The Glass's and the pages service's served source files name no outside host**: the pages
  service's views and `headers.ts`, the Glass's `index.html` and its static pages.

**What this cannot show, so SE6b exists.** A static scan reads files; it does not see what a built
page asks for. `test_workspace_bundle.py` records that the built Glass bundle legitimately holds
absolute tile and documentation URLs, so no scan of the bundle can stand in for a browser, and a
scan of the inputs cannot see a request made by code the inputs import. The request-level proof (a
signed-in browser that records every request and every `securitypolicyviolation` event on every
page a person can reach) is SE6b's, under `apps/workspace/live`.

**What this slice did not do, and why (the pinned image): a decision owed.** Brief item 1 (set the
usage-tracking switch-off in both profiles' rendered environment, and test it) cannot be done as
written, because Superset 6.1.0 has no runtime switch. Measured on the image the Dockerfile pins
(`apache/superset@sha256:16b50bbe...`, the same digest), 20 November 2026:

- `grep -rn scarf -i /app/superset --include=*.py --include=*.html` finds only the two policy hosts
  in `superset/config.py` (lines 2127 to 2128 and 2167 to 2168); `SCARF_ANALYTICS` is in no Python
  file, no shell file and no bundle (`grep -c SCARF_ANALYTICS` on the bundle: 0), and the bundle
  reads no `process.env` at all. The variable the documentation names is read by the `@scarf/scarf`
  npm package while Superset is *built* (`package.json` carries its `scarfSettings`), not by the
  running server.
- The pixel is component `A` in `static/assets/8085.4bc9b7059e85ba458bcb.entry.js`:
  `let A=({version:e,sha:a,build:t})=>{let l=`https://apachesuperset.gateway.scarf.sh/pixel/<id>/${e}/${a}/${t}`;
  return(0,n.Y)("img",{referrerPolicy:"no-referrer-when-downgrade",src:l,width:0,height:0,alt:""})}`,
  drawn with no condition after the navigation bar's "Login" link: `...,(0,n.Y)(A,{version:t.version_string,
  sha:t.version_sha,build:t.build_number})]})`.

So the only thing that stops that request is the policy's `img-src`, which this slice made name no
outside host: the browser refuses the image before any request leaves, and says so with a
`securitypolicyviolation` event. **That makes the policy the whole protection, so the policy being
sent is tested here** (`TALISMAN_ENABLED` pinned on in the file, so the environment cannot turn it
off, and absent from both renders). No switch-off line is rendered: a variable the image never reads
would claim a protection the product does not have. Whether this stands in place of item 1 is the
conductor's or the owner's to rule, not this test's.

The planted violations take the shape the code under test receives at its real call site (rule 15):
the real loaded policy with one source appended, never a hand-written dictionary; the real
`layout.njk` with one element added; the real `headers.ts` with one source added. Each plant is
asserted to have changed the text it plants into, so a plant that matched nothing cannot pass.

Synthetic names only (rule 9): `example.test` addresses stand for "somewhere else".
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest
from harness.reporting import reporting_env

from schemas.deployment import OspreyConfig
from tests.harness.test_cloud_platform_render import _config as _cloud_config
from tests.harness.test_cloud_platform_render import _values as _cloud_values
from tests.harness.test_superset_entra_sign_in import _superset

CORE = Path(__file__).resolve().parents[3] / "OspreyFlow_Core"
PAGES_SERVER = CORE / "apps" / "pages" / "server"
WORKSPACE = CORE / "apps" / "workspace"

# --- the policy ---------------------------------------------------------------------------------

#: Words a policy source may be, none of which is an address.
KEYWORDS = frozenset(
    {
        "'self'",
        "'none'",
        "'unsafe-inline'",
        "'unsafe-eval'",
        "'strict-dynamic'",
        "'wasm-unsafe-eval'",
    }  # fmt: skip
)
#: Schemes that carry no address: the page's own memory.
LOCAL_SCHEMES = frozenset({"blob:", "data:"})
#: A nonce or a hash names no address either.
_NONCE_OR_HASH = re.compile(r"^'(?:nonce|sha256|sha384|sha512)-[A-Za-z0-9+/=_-]+'$")


def _host_of(source: str) -> str:
    """The host a CSP source names: `https://a.example/x` and the bare `a.example:8443` alike (the
    pinned Superset ships both shapes, `https://api.mapbox.com` and `ows.terrestris.de`)."""
    text = source.strip()
    if "://" in text:
        return (urlsplit(text).hostname or "").lower()
    return text.split("/")[0].rsplit("@", 1)[-1].split(":")[0].lower()


def sources_outside(
    policy: Mapping[str, Any], own_hosts: Iterable[str] = ()
) -> list[tuple[str, str]]:
    """Each (directive, source) that names anything but `'self'`, a keyword, a nonce, an in-memory
    scheme or one of the deployment's own hosts. `*`, `https:` and `*.host` are outside."""
    own = {host.lower() for host in own_hosts}
    found: list[tuple[str, str]] = []
    for directive, value in policy.items():
        sources = [value] if isinstance(value, str) else list(value)
        for source in sources:
            text = source.strip()
            if text.lower() in KEYWORDS or text.lower() in LOCAL_SCHEMES:
                continue
            if _NONCE_OR_HASH.match(text):
                continue
            if _host_of(text) in own and not text.startswith("*"):
                continue
            found.append((directive, source))
    return found


@pytest.fixture
def rendered() -> list[str]:
    """What the render writes for a deployment with the reporting components on."""
    config = OspreyConfig.model_validate(
        {
            "network": {"public_origin": "http://localhost:8080"},
            "reporting": {"sync": True, "superset": True},
        }  # fmt: skip
    )
    return reporting_env(config)


def _env(lines: Iterable[str]) -> dict[str, str]:
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def _own_hosts(env: Mapping[str, str]) -> set[str]:
    """The deployment's own names: the origins the render gives Superset to know itself by."""
    origins = [env["SUPERSET_PUBLIC_ORIGIN"], env["SUPERSET_GLASS_ORIGIN"]]
    return {urlsplit(origin).hostname or "" for origin in origins}


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch, rendered: list[str]) -> Any:
    """`superset_config.py` loaded from the rendered environment, as the container loads it."""
    return _superset(monkeypatch, _env(rendered))


@pytest.fixture
def own(rendered: list[str]) -> set[str]:
    return _own_hosts(_env(rendered))


def _policies(config: Any) -> dict[str, dict[str, Any]]:
    """Both policies this file sets: Superset takes the development one when debug is on."""
    return {
        "TALISMAN_CONFIG": config.TALISMAN_CONFIG["content_security_policy"],
        "TALISMAN_DEV_CONFIG": config.TALISMAN_DEV_CONFIG["content_security_policy"],
    }


@pytest.mark.parametrize("name", ["TALISMAN_CONFIG", "TALISMAN_DEV_CONFIG"])
def test_the_loaded_policy_names_no_host_outside_the_deployment(
    config: Any, own: set[str], name: str
) -> None:
    policy = _policies(config)[name]
    assert sources_outside(policy, own) == []
    # Not vacuous: the policy is the one that frames Superset in the Glass, and names that origin.
    assert any(_host_of(source) in own for source in policy["frame-ancestors"]), (
        "the Glass's own origin is the one outside-looking name the policy keeps"
    )
    assert "'self'" in policy["img-src"] and "'self'" in policy["connect-src"]


def test_the_policy_does_not_depend_on_which_dictionary_superset_picks(config: Any) -> None:
    """Debug mode takes `TALISMAN_DEV_CONFIG`; every directive but the script source is the same."""
    live = copy.deepcopy(config.TALISMAN_CONFIG["content_security_policy"])
    dev = copy.deepcopy(config.TALISMAN_DEV_CONFIG["content_security_policy"])
    live.pop("script-src"), dev.pop("script-src")
    assert live == dev


# --- the policy is sent ------------------------------------------------------------------------
# The policy is the only thing that stops Superset's tracking pixel (see the header), and Flask-
# Talisman sends no policy header at all when `TALISMAN_ENABLED` is false. Both dictionaries above
# are unchanged when it is, so none of the tests above would notice.


def talisman_is_on(config: Any) -> bool:
    """What Superset reads (`superset/initialization/__init__.py`: `config["TALISMAN_ENABLED"]`)."""
    return config.TALISMAN_ENABLED is True


def test_the_policy_is_sent_talisman_is_on(config: Any) -> None:
    assert talisman_is_on(config)


@pytest.mark.parametrize("value", ["false", "False", "0", "no"])
def test_the_environment_cannot_turn_the_policy_off(
    monkeypatch: pytest.MonkeyPatch, rendered: list[str], value: str
) -> None:
    """The shipped file reads `TALISMAN_ENABLED` from the environment; this file's own value wins."""
    loaded = _superset(monkeypatch, {**_env(rendered), "TALISMAN_ENABLED": value})
    assert talisman_is_on(loaded)


def test_the_check_is_red_when_the_policy_is_switched_off(config: Any) -> None:
    """Planted at the call site: the real loaded config with the one attribute changed."""
    assert talisman_is_on(config)
    config.TALISMAN_ENABLED = False
    assert not talisman_is_on(config)
    del config.TALISMAN_ENABLED
    with pytest.raises(AttributeError):  # a file that stops pinning it is red, not skipped
        talisman_is_on(config)


def test_neither_profiles_render_switches_the_policy_off(rendered: list[str]) -> None:
    assert "TALISMAN_ENABLED" not in _env(rendered)
    cloud = _cloud_values(_cloud_config())["environment"]
    assert "TALISMAN_ENABLED" not in cloud
    # The check can fail: the same lookups on a render that sets one.
    assert "TALISMAN_ENABLED" in _env([*rendered, "TALISMAN_ENABLED=false"])


@pytest.mark.parametrize(
    ("directive", "host"),
    [
        ("img-src", "https://apachesuperset.gateway.scarf.sh"),
        ("img-src", "https://static.scarf.sh/"),
        ("connect-src", "https://api.mapbox.com"),
        ("connect-src", "https://events.mapbox.com"),
    ],
)
@pytest.mark.parametrize("name", ["TALISMAN_CONFIG", "TALISMAN_DEV_CONFIG"])
def test_each_address_the_file_used_to_carry_is_red_when_put_back(
    config: Any, own: set[str], name: str, directive: str, host: str
) -> None:
    policy = copy.deepcopy(_policies(config)[name])
    before = list(policy[directive])
    policy[directive] = [*before, host]
    assert policy[directive] != before
    assert sources_outside(policy, own) == [(directive, host)]


@pytest.mark.parametrize(
    "source",
    ["ows.terrestris.de", "https://cdn.document360.io", "https://*.example.test", "*", "https:",
     "http://example.test:8443", "wss://example.test"],
)  # fmt: skip
def test_the_detector_finds_every_shape_a_source_can_take(
    config: Any, own: set[str], source: str
) -> None:
    """The shapes the pinned Superset ships (a bare host, a full address) and the wide ones."""
    policy = copy.deepcopy(config.TALISMAN_CONFIG["content_security_policy"])
    policy["connect-src"] = [*policy["connect-src"], source]
    assert sources_outside(policy, own) == [("connect-src", source)]


def test_a_directive_written_as_text_not_a_list_is_read_too(own: set[str]) -> None:
    assert sources_outside({"object-src": "'none'"}, own) == []
    assert sources_outside({"object-src": "https://example.test"}, own) == [
        ("object-src", "https://example.test")
    ]


def test_the_deployments_own_origin_is_not_flagged_but_a_lookalike_is(own: set[str]) -> None:
    [host, *_] = sorted(own)
    assert sources_outside({"img-src": [f"https://{host}"]}, own) == []
    assert sources_outside({"img-src": [f"https://{host}.example.test"]}, own) != []
    assert sources_outside({"img-src": [f"https://{host}@example.test/"]}, own) != []


# --- no map key ---------------------------------------------------------------------------------


def test_no_map_key_is_set_in_the_configuration_or_in_either_profiles_render(
    config: Any, rendered: list[str]
) -> None:
    assert not hasattr(config, "MAPBOX_API_KEY")
    assert "MAPBOX_API_KEY" not in _env(rendered)
    cloud = _cloud_values(_cloud_config())["environment"]
    assert "MAPBOX_API_KEY" not in cloud
    # The check can fail: the same lookups on a render that sets one.
    assert "MAPBOX_API_KEY" in _env([*rendered, "MAPBOX_API_KEY=a-synthetic-value"])


# --- the served source files --------------------------------------------------------------------

#: An absolute address, or a protocol-relative one with a dotted host.
_ADDRESS = re.compile(
    r"(?:\b(?:https?|wss?|ftp)://[^\s\"'<>)\\]+)|(?<![:\w])//[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+[^\s\"'<>)\\]*"
)
#: A link is navigation, not a load: the browser requests nothing until a person follows it. The
#: opening tag is removed before the scan, so a documentation link may name its address.
_ANCHOR_OPEN = re.compile(r"<a\b[^>]*>", re.IGNORECASE | re.DOTALL)

#: Absolute addresses a served file may name, as (path under the Core folder, host): why.
#: Empty today. The two kinds this slice's brief allows are (1) a documentation link, which is an
#: `<a>` and is exempt by construction above, and (2) the address of an organisation sign-in an
#: administrator enabled (named in configuration at run time, never in a served file). A third
#: kind needs the owner's word and an entry here with its reason.
ALLOWED: dict[tuple[str, str], str] = {}


def _host_in(address: str) -> str:
    return (urlsplit(address if "://" in address else "https:" + address).hostname or "").lower()


def addresses_in_markup(path: str, text: str) -> list[str]:
    """Each outside host a markup or style file names outside a link, bar the written exceptions."""
    without_links = _ANCHOR_OPEN.sub("", text)
    hosts = (_host_in(m.group(0)) for m in _ADDRESS.finditer(without_links))
    return sorted(h for h in hosts if (path, h) not in ALLOWED)


_DIRECTIVE_LINE = re.compile(r'"([a-z-]+)":\s*\[([^\]]*)\]')


def addresses_in_headers(text: str) -> list[tuple[str, str]]:
    """The pages service's policy, read from `headers.ts`: every directive's string sources must be
    a keyword or an in-memory scheme (the page names no other address, not even its own)."""
    policy: dict[str, list[str]] = {}
    for directive, body in _DIRECTIVE_LINE.findall(text):
        policy[directive] = re.findall(r'"([^"]*)"', body)
    return sources_outside(policy)


def _served_files() -> dict[str, Path]:
    views = sorted((PAGES_SERVER / "views").glob("*.njk"))
    static = sorted((WORKSPACE / "public").glob("*.html"))
    files = [*views, PAGES_SERVER / "headers.ts", WORKSPACE / "index.html", *static]
    return {str(f.relative_to(CORE)): f for f in files}


def test_the_scan_reads_the_files_it_claims_to() -> None:
    """A moved folder must not turn this into a scan of nothing (rule 12)."""
    names = set(_served_files())
    assert {
        "apps/pages/server/views/layout.njk",
        "apps/pages/server/views/home.njk",
        "apps/pages/server/views/error.njk",
        "apps/pages/server/headers.ts",
        "apps/workspace/index.html",
    } <= names
    assert all(path.read_text(encoding="utf-8").strip() for path in _served_files().values())


def test_no_served_source_file_names_an_outside_host() -> None:
    found: dict[str, Any] = {}
    for name, path in _served_files().items():
        text = path.read_text(encoding="utf-8")
        is_headers = name.endswith("headers.ts")
        hits: Any = addresses_in_headers(text) if is_headers else addresses_in_markup(name, text)
        if hits:
            found[name] = hits
    assert found == {}


@pytest.mark.parametrize(
    "plant",
    [
        '<img src="https://pixel.example.test/a.gif" alt="">',
        '<link rel="stylesheet" href="//fonts.example.test/css">',
        '<script src="https://cdn.example.test/lib.js"></script>',
        '<style>@import url("https://css.example.test/x.css");</style>',
        '<div style="background: url(https://img.example.test/b.png)"></div>',
        '<form method="post" action="https://collect.example.test/f"></form>',
    ],
    ids=["img", "stylesheet", "script", "import", "css-url", "form-action"],
)
def test_an_outside_load_planted_in_a_pages_view_is_red(plant: str) -> None:
    name = "apps/pages/server/views/layout.njk"
    real = (CORE / name).read_text(encoding="utf-8")
    planted = real.replace("</body>", f"{plant}\n</body>")
    assert planted != real
    assert addresses_in_markup(name, real) == []
    assert addresses_in_markup(name, planted) != []


def test_an_outside_image_planted_in_the_glass_index_is_red() -> None:
    name = "apps/workspace/index.html"
    real = (CORE / name).read_text(encoding="utf-8")
    planted = real.replace("</body>", '<img src="https://pixel.example.test/a.gif"></body>')
    assert planted != real
    assert addresses_in_markup(name, planted) == ["pixel.example.test"]


def test_a_documentation_link_is_a_link_not_a_load() -> None:
    """The exemption's other side: the same address as a link is not found, as a load it is."""
    link = '<a href="https://docs.example.test/guide">Guide</a>'
    assert addresses_in_markup("x.njk", link) == []
    assert addresses_in_markup("x.njk", link.replace("<a ", "<img ").replace("href", "src")) == [
        "docs.example.test"
    ]


def test_a_written_exception_is_honoured_for_its_file_and_host_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text = '<script src="https://sign-in.example.test/a.js"></script>'
    assert addresses_in_markup("a.njk", text) == ["sign-in.example.test"]
    monkeypatch.setitem(ALLOWED, ("a.njk", "sign-in.example.test"), "an administrator's sign-in")
    assert addresses_in_markup("a.njk", text) == []
    assert addresses_in_markup("b.njk", text) == ["sign-in.example.test"]


@pytest.mark.parametrize("directive", ["img-src", "connect-src", "script-src"])
def test_an_outside_source_planted_in_the_pages_policy_is_red(directive: str) -> None:
    real = (PAGES_SERVER / "headers.ts").read_text(encoding="utf-8")
    assert addresses_in_headers(real) == []
    opening = f'"{directive}": ["\'self\''
    planted = real.replace(opening, f'"{directive}": ["https://outside.example.test", "\'self\'', 1)
    assert planted != real
    assert addresses_in_headers(planted) == [(directive, "https://outside.example.test")]
