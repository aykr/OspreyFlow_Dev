"""The page service in a deployment is a deployment setting, off by default: the renderers read
`pages.enabled`; off renders exactly the reference, on adds the service (build id PL7, slice
PL7a2b; ADR-152 Amendment 3, items 1 to 5; decision 7's route table and `OSPREY_PAGES_TREE`;
invariant I22; the owner's rulings of 21 and 23 November 2026).

**What is asked, and which case fails if it is broken (rule 12).**

* The setting is a boolean, default `false`, and a value that is not `true` or `false` is refused in
  words, naming `pages.enabled`, by the settings validation and by the loader the renderers read
  `osprey.yaml` with (`test_a_value_that_is_not_true_or_false_is_refused_*`).
* **Off or absent is the reference, byte for byte, in every shape under each brand**
  (`test_off_*`): with the setting not written, and with `enabled: false` written. The page
  service's two secrets, minted by `apply` since PL9a, stay in `deployment.env` exactly as the
  reference pins them, off or on (`test_the_two_minted_secrets_are_the_same_off_and_on`): this
  slice adds no secret and no `OSPREY_PAGES_*` variable while the setting is off.
* **On adds the service, its route and its variables, and nothing else** (`test_on_*`), in the
  compose shapes (local-lite, small) and the Helm ones (cluster, cloud-platform, and the
  cloud-platform proof of concept): the `pages` service, the route table for the brand (the
  Studio's paths on the default theme; `pages`' own paths on both), its variables with
  `OSPREY_PAGES_TREE` from `appearance.brand` (`default` or `govuk`), and, for a chart, the value
  `pages.enabled: true`.
* **A fault in each is shown red, in the shape the renderer writes it (rule 15).** Four plants, each
  made by calling the real renderer through a patched function (the renderers' files are never
  edited): a `pages` service block in the compose file (a workload in a chart's values), a studio
  handle in the front proxy's configuration (the Caddyfile, or the platform Ingress's path on
  cloud-platform), a chart value, and an `OSPREY_PAGES_*` variable. Each **fails the off case**
  (`test_a_*_planted_while_off_is_red`), and **the same four missing fail the on case**
  (`test_a_*_missing_while_on_is_red`): each is shown clean first, then red naming what is wrong.
* **The cutover (item 4).** A GOV.UK deployment whose derived tree state is complete
  (`scripts.tree_parity.govuk_tree_state`, the one function: the tests point it at a complete tree
  by the three files it reads) with the setting off is refused in the words of the amendment, in
  every shape; with it on, it renders with no workspace service and no route to one (I22)
  (`test_the_complete_govuk_tree_*`). A complete tree under the default brand, or a partial one
  under GOV.UK, changes nothing.

**What this test walks and reads.** It reads `OspreyFlow_Build/tests/fixtures/reference_render/`
(through `tools.reference_render`, whose `differences` read each shape's stored folder and
`MANIFEST.json`, a recursion over that folder only), the chart `OspreyFlow_Core/deploy/helm/
ospreyflow/` (the same helper's one recursion over its files, for the Helm shapes' chart view), the
cloud-platform fixtures `OspreyFlow_Build/tests/fixtures/cloud_platform/{development,poc}.yaml` (the
helper reads them; and the platform settings they name, through the renderer), and, by importing
the renderers, `OspreyFlow_Core/harness/` and `OspreyFlow_Core/packages/schemas/`. It writes only to
`tmp_path` (a complete GOV.UK tree of two small files, and the `osprey.yaml` it loads). It walks
no other folder; the render helpers it imports glob only what is named here.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml
from pydantic import ValidationError
from tools import reference_render as ref

BRANDS = ref.BRANDS
SHAPES = ref.SHAPES
#: The compose shapes (a compose file and a Caddyfile) and the Helm ones (a chart's values).
COMPOSE = ("local-lite", "small")
HELM = ("cluster", "cloud-platform", "cloud-platform-poc")
ON = {"pages": {"enabled": True}}
OFF = {"pages": {"enabled": False}}
#: Local-lite cannot be turned on at all: its address is plain HTTP, or HTTPS on a `.localhost` name
#: whose certificate is Caddy's own internal CA's, and the page service accepts neither as its
#: issuer (plain HTTP: `apps/pages/server/config.ts`; Caddy's CA: node does not trust it, and a
#: trust path would take the CA's root out of the proxy's data volume, where its private key is).
#: The render refuses, in words, both ways (`test_turning_the_service_on_over_plain_http_is_*`,
#: `test_local_lite_over_https_is_*`), so every case that needs the service *on* is one of
#: `ON_SHAPES`, and local-lite's "on" is that refusal.
#: The cloud platform (development and the proof of concept) is refused too: the page service has no
#: sign-in there yet (the owner's ruling of 23 November 2026, case C: ADR-148 Amendment 23 item 1
#: needs the chart's egress to the identity provider and the page service's own Entra registration,
#: a part of its own). `test_turning_the_service_on_for_the_cloud_platform_is_refused_in_words`.
ON_SHAPES = ("small", "cluster")
CLOUD_SHAPES = ("cloud-platform", "cloud-platform-poc")
ON_COMPOSE = ("small",)


def _on(shape: str) -> dict[str, Any]:
    """The settings of a shape with the page service on: `pages.enabled`, and nothing else."""
    assert shape in ON_SHAPES, f"{shape} cannot be turned on: the render refuses it"
    return ON


def _baseline(shape: str, brand: str) -> dict[str, bytes]:
    """What `_on(shape)` is compared with: the reference's stored folder."""
    return ref.read_folder(ref.REFERENCE / ref.folder_name(shape, brand))


#: `OSPREY_PAGES_TREE`, from `appearance.brand` (ADR-152 decision 7).
TREE = {"ospreyflow": "default", "govuk": "govuk"}
#: Where `pages` listens (`apps/pages/server/config.ts`'s default `OSPREY_PAGES_PORT`).
PAGES_PORT = "8090"
#: The paths decision 7 sends to `pages` while a GOV.UK tree is not complete: its own on both
#: themes, and the Studio's on the default theme.
OWN_PATHS = {"/session", "/assets/pages"}
STUDIO_PATHS = {"/studio"}
THE_WORDS = (
    "the GOV.UK tree is complete, so the workspace would be removed, and the page service is "
    "not enabled for this deployment"
)
SHAPE_BRANDS = [(shape, brand) for shape in SHAPES for brand in BRANDS]
IDS = [f"{shape}-{brand}" for shape, brand in SHAPE_BRANDS]
ON_SHAPE_BRANDS = [(shape, brand) for shape in ON_SHAPES for brand in BRANDS]
ON_IDS = [f"{shape}-{brand}" for shape, brand in ON_SHAPE_BRANDS]


def _render(shape: str, brand: str, **settings: Any) -> dict[str, bytes]:
    return ref.render_shape(shape, brand, **settings)


def _off_as_written(shape: str, files: dict[str, bytes]) -> dict[str, bytes]:
    """A render of a file that wrote `pages: {enabled: false}`, with the chart's copy of that
    section taken out of the copy of `osprey.yaml` inside its values (a quoted scalar, where the
    line breaks are the two characters `\\n`): the input, copied, is the one place it shows."""
    if shape not in HELM:
        return files
    text = files["values.yaml"].decode("utf-8")
    written = "pages:\\n  enabled: false\\n"
    assert written in text, "the copy of osprey.yaml does not carry what the file wrote"
    return {**files, "values.yaml": text.replace(written, "", 1).encode("utf-8")}


# ---- reading what a render wrote -------------------------------------------------------------


def _values(files: dict[str, bytes]) -> dict[str, Any]:
    loaded = yaml.safe_load(files["values.yaml"].decode("utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _named(entries: Any) -> dict[str, str]:
    """A chart workload's `env` list as `name -> value or reference`."""
    named: dict[str, str] = {}
    for entry in entries or []:
        if "value" in entry:
            named[entry["name"]] = str(entry["value"])
        elif "secret" in entry:
            named[entry["name"]] = f"secret:{entry['secret']}"
        else:
            named[entry["name"]] = f"config:{entry.get('config')}"
    return named


def pages_service(shape: str, files: dict[str, bytes]) -> dict[str, Any] | None:
    """The `pages` service of a render: its image, its variables by name, and whether it reads the
    deployment's whole env file; `None` when the render has none."""
    if shape in COMPOSE:
        services = yaml.safe_load(files["compose.yaml"].decode("utf-8"))["services"]
        found = services.get("pages")
        if found is None:
            return None
        return {
            "image": found["image"],
            "env": {k: str(v) for k, v in (found.get("environment") or {}).items()},
            "env_file": "env_file" in found,
            "egress": "egress" in found.get("networks", []),
            "volumes": list(found.get("volumes", [])),
        }
    workloads = {w["name"]: w for w in _values(files).get("workloads", [])}
    found = workloads.get("pages")
    if found is None:
        return None
    return {
        "image": found["image"],
        "env": _named(found.get("env")),
        "env_file": bool(found.get("envFrom")),
        "egress": bool(found.get("egress")),
        "volumes": [],
        "ports": [p["port"] for p in found.get("ports", [])],
    }


def _normal(path: str) -> str:
    return path.removesuffix("*").removesuffix("/") or "/"


def _caddy_pages_paths(text: str) -> set[str]:
    """The paths a Caddyfile sends to `pages`: a named `path` matcher whose `handle` proxies to
    `pages:8090`, or a bare `handle` that does (every path)."""
    matchers = {m[1]: m[2].split() for m in re.finditer(r"(?m)^\s*@(\w+) path (.+)$", text)}
    found: set[str] = set()
    block = rf"(?m)^\s*handle(?: @(\w+))? \{{\n\s*reverse_proxy pages:{PAGES_PORT}\n\s*\}}"
    for match in re.finditer(block, text):
        if match[1] is None:
            found.add("/")
        else:
            found |= {_normal(path) for path in matchers[match[1]]}
    return found


def pages_paths(shape: str, files: dict[str, bytes]) -> set[str]:
    """The paths the deployment's front door sends to `pages`: the Caddyfile's (compose, and the
    cluster's, which carries it in its values), or the platform Ingress's (cloud-platform)."""
    if shape in COMPOSE:
        return _caddy_pages_paths(files["Caddyfile"].decode("utf-8"))
    values = _values(files)
    if shape == "cluster":
        return _caddy_pages_paths(values["files"]["Caddyfile"])
    return {
        _normal(path["path"])
        for rule in values["ingress"]["rules"]
        for path in rule["paths"]
        if path["service"] == "pages"
    }


def has_a_workspace(shape: str, files: dict[str, bytes]) -> bool:
    """A `workspace` service or workload, or a route to `workspace:` (I22)."""
    if shape in COMPOSE:
        services = yaml.safe_load(files["compose.yaml"].decode("utf-8"))["services"]
        return "workspace" in services or "workspace:" in files["Caddyfile"].decode("utf-8")
    values = _values(files)
    if any(w["name"] == "workspace" for w in values.get("workloads", [])):
        return True
    if shape == "cluster":
        return "workspace:" in values["files"]["Caddyfile"]
    return any(
        path["service"] == "workspace"
        for rule in values["ingress"]["rules"]
        for path in rule["paths"]
    )


def on_findings(shape: str, brand: str, files: dict[str, bytes], config: Any = None) -> list[str]:
    """What is wrong with a render that should hold the page service (ADR-152 Amendment 3 item 3):
    each line names the thing missing or wrong. Empty is a render that holds all of it."""
    found: list[str] = []
    service = pages_service(shape, files)
    if service is None:
        found.append("no pages service")
    else:
        env = service["env"]
        if env.get("OSPREY_PAGES_TREE") != TREE[brand]:
            found.append(
                f"OSPREY_PAGES_TREE is {env.get('OSPREY_PAGES_TREE')!r}, not {TREE[brand]!r}"
            )
        for name in ("OSPREY_PAGES_PORT", "OSPREY_PAGES_PUBLIC_ORIGIN", "OSPREY_PAGES_CONDUIT_URL"):
            if name not in env:
                found.append(f"pages has no {name}")
        if env.get("OSPREY_PAGES_PORT", PAGES_PORT) != PAGES_PORT:
            found.append("pages is not on its port")
        if "OSPREY_PAGES_SESSION_SECRET" not in env:
            found.append("pages is not given its session secret")
        if service["env_file"]:
            found.append("pages reads the whole env file (it needs two secrets, not all of them)")
    wanted = set(OWN_PATHS) | (STUDIO_PATHS if brand == "ospreyflow" else set())
    routed = pages_paths(shape, files)
    # Every path goes to `pages` once a GOV.UK tree is complete (`/`), which covers the rest.
    found += [f"no route {path} to pages" for path in sorted(wanted - routed) if "/" not in routed]
    if shape in HELM and _values(files).get("pages") != {"enabled": True}:
        found.append("no chart value pages.enabled: true")
    return found


# ---- the plants: a real renderer, called through a patched function ----------------------------

#: The three renderers' own functions a plant wraps. The names are looked up when the render runs
#: (`harness.render`'s module globals; the chart renderers are imported in `render`), so a patch
#: on the module reaches the render.


def _helm_renderer(shape: str) -> tuple[str, str]:
    if shape == "cluster":
        return "harness.cluster", "render_cluster"
    return "harness.cloud_platform", "render_cloud_platform"


def _patched(target: str, name: str, wrapper: Callable[[Any], Callable[..., Any]]) -> Any:
    module = __import__(target, fromlist=[name])
    real = getattr(module, name)
    return mock.patch.object(module, name, wrapper(real))


def _a_pages_service(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, images: Any) -> dict[str, Any]:
        services = real(config, images)
        services["pages"] = {
            "image": "docker.io/ospreyflow/pages:pinned",
            "restart": "unless-stopped",
            "networks": ["osprey"],
            "environment": {"OSPREY_PAGES_PORT": PAGES_PORT},
            "healthcheck": {"test": ["CMD", "true"], "interval": "10s"},
        }
        return services

    return planted


def _no_pages_service(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, images: Any) -> dict[str, Any]:
        services = real(config, images)
        services.pop("pages", None)
        return services

    return planted


#: The text the renderer writes for the route, in the form it writes it (a named matcher and a
#: `handle` that proxies to `pages`), and what stands in its place without it.
STUDIO_HANDLE = (
    "\t@pages path /studio /studio/*\n\thandle @pages {\n\t\treverse_proxy pages:8090\n\t}\n"
)


def _a_studio_handle(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, **kwargs: Any) -> str:
        text: str = real(config, **kwargs)
        upstream = "\treverse_proxy workspace:8080\n"
        assert upstream in text, "the real Caddyfile has no workspace route to plant beside"
        return text.replace(upstream, STUDIO_HANDLE + "\thandle {\n\t" + upstream + "\t}\n", 1)

    return planted


def _no_pages_handle(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, **kwargs: Any) -> str:
        text: str = real(config, **kwargs)
        return re.sub(
            r"(?m)^\t@pages path .*\n\thandle @pages \{\n\t\treverse_proxy pages:\d+\n\t\}\n",
            "",
            text,
        )

    return planted


def _a_studio_path(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(*args: Any, **kwargs: Any) -> dict[str, Any]:
        ingress: dict[str, Any] = real(*args, **kwargs)
        ingress["rules"][0]["paths"].insert(
            0, {"path": "/studio", "service": "pages", "port": 8090}
        )
        return ingress

    return planted


def _no_pages_path(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(*args: Any, **kwargs: Any) -> dict[str, Any]:
        ingress: dict[str, Any] = real(*args, **kwargs)
        for rule in ingress["rules"]:
            rule["paths"] = [p for p in rule["paths"] if p["service"] != "pages"]
        return ingress

    return planted


def _a_chart_value(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(*args: Any, **kwargs: Any) -> dict[str, str]:
        artefacts: dict[str, str] = dict(real(*args, **kwargs))
        artefacts["values.yaml"] += "pages:\n  enabled: true\n"
        return artefacts

    return planted


def _no_chart_value(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(*args: Any, **kwargs: Any) -> dict[str, str]:
        artefacts: dict[str, str] = dict(real(*args, **kwargs))
        text = artefacts["values.yaml"]
        assert "\npages:\n  enabled: true\n" in text, "the render has no chart value to take out"
        artefacts["values.yaml"] = text.replace("\npages:\n  enabled: true\n", "\n", 1)
        return artefacts

    return planted


def _a_variable(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any) -> str:
        return str(real(config)) + "OSPREY_PAGES_TREE=default\n"

    return planted


def _no_variable(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, images: Any) -> dict[str, Any]:
        services = real(config, images)
        service = services.get("pages")
        assert service is not None, "the render has no pages service to take a variable from"
        service["environment"] = {
            k: v for k, v in service["environment"].items() if k != "OSPREY_PAGES_TREE"
        }
        return services

    return planted


class Plant:
    """One fault: the patch that plants it while off (`planted`), the patch that takes the same
    thing out while on (`taken_out`), the shapes it can be in, and what the red message names."""

    def __init__(
        self,
        name: str,
        planted: Callable[[str], Any],
        taken_out: Callable[[str], Any],
        shapes: tuple[str, ...],
        names: str,
        missing: str,
    ) -> None:
        self.name, self.planted, self.taken_out = name, planted, taken_out
        self.shapes, self.names, self.missing = shapes, names, missing


def _route_patch(wrapper_for_caddy: Any, wrapper_for_ingress: Any) -> Callable[[str], Any]:
    def patch(shape: str) -> Any:
        if shape in HELM and shape != "cluster":
            return _patched("harness.cloud_platform", "_ingress", wrapper_for_ingress)
        if shape == "cluster":
            return _patched("harness.site", "render_caddyfile", wrapper_for_caddy)
        return _patched("harness.render", "render_caddyfile", wrapper_for_caddy)

    return patch


def _helm_patch(wrapper: Any) -> Callable[[str], Any]:
    return lambda shape: _patched(*_helm_renderer(shape), wrapper)


PLANTS = [
    Plant(
        "service",
        lambda shape: _patched("harness.render", "compose_services", _a_pages_service),
        lambda shape: _patched("harness.render", "compose_services", _no_pages_service),
        SHAPES,
        names="pages",
        missing="no pages service",
    ),
    Plant(
        "handle",
        _route_patch(_a_studio_handle, _a_studio_path),
        _route_patch(_no_pages_handle, _no_pages_path),
        SHAPES,
        names="/studio",
        missing="no route",
    ),
    Plant(
        "chart value",
        _helm_patch(_a_chart_value),
        _helm_patch(_no_chart_value),
        HELM,
        names="pages",
        missing="no chart value pages.enabled",
    ),
    Plant(
        "variable",
        lambda shape: _patched("harness.render", "_render_env", _a_variable),
        lambda shape: _patched("harness.render", "compose_services", _no_variable),
        SHAPES,
        names="OSPREY_PAGES_TREE",
        missing="OSPREY_PAGES_TREE",
    ),
]
PLANT_CASES = [
    pytest.param(plant, shape, brand, id=f"{plant.name}-{shape}-{brand}")
    for plant in PLANTS
    for shape in plant.shapes
    for brand in BRANDS
]
#: The same plants, for the cases that need the service on (local-lite cannot be: `ON_SHAPES`).
ON_PLANT_CASES = [case for case in PLANT_CASES if case.values[1] in ON_SHAPES]


# ---- 1. the setting ---------------------------------------------------------------------------


def test_the_setting_is_off_by_default_and_belongs_to_the_one_settings_validation() -> None:
    """`pages.enabled` is a section of `OspreyConfig`, the model that refuses an unknown
    `appearance.brand`; it is off when the file omits it and nothing else turns it on."""
    from schemas.deployment import OspreyConfig

    assert OspreyConfig().pages.enabled is False
    for shape, brand in SHAPE_BRANDS:
        assert ref.config_for(shape, brand).pages.enabled is False
    with pytest.raises(ValidationError, match="brand"):
        OspreyConfig.model_validate({"appearance": {"brand": "other"}})


@pytest.mark.parametrize("value", ["yes", "'yes'", "'true'", "1", "on", "null", "[]", "TRUE1"])
def test_a_value_that_is_not_true_or_false_is_refused_where_the_renderers_load_the_file(
    value: str, tmp_path: Path
) -> None:
    """In words, naming the setting, by the loader every renderer reads `osprey.yaml` with
    (`harness.render.load_config`), the unquoted spellings YAML 1.1 reads as a boolean included."""
    from harness.render import load_config

    path = tmp_path / "osprey.yaml"
    path.write_text(f"pages:\n  enabled: {value}\n", encoding="utf-8")
    with pytest.raises(ValidationError, match=r"pages\.enabled must be true or false"):
        load_config(path)


@pytest.mark.parametrize(("value", "expected"), [("true", True), ("false", False)])
def test_true_and_false_are_read_as_written(value: str, expected: bool, tmp_path: Path) -> None:
    from harness.render import load_config

    path = tmp_path / "osprey.yaml"
    path.write_text(f"pages:\n  enabled: {value}\n", encoding="utf-8")
    assert load_config(path).pages.enabled is expected


# ---- 2. off or absent is the reference ---------------------------------------------------------


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_off_with_the_setting_absent_is_the_reference(shape: str, brand: str) -> None:
    """The invariant (`test_reference_render.py` holds it too): no `pages` written, the stored
    reference, file by file."""
    config = ref.config_for(shape, brand)
    assert "pages" not in config.model_fields_set
    assert ref.differences(shape, brand, ref.render_files(config)) == []


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_off_with_enabled_false_written_is_the_reference(shape: str, brand: str) -> None:
    """A deployment that writes `enabled: false` renders what one that writes nothing does. The
    one place the written line can show is a chart's copy of the deployment's own `osprey.yaml`
    (the input, copied: the dump keeps what the file names); that copy's two lines are all that
    is taken out before the comparison."""
    assert ref.differences(shape, brand, _off_as_written(shape, _render(shape, brand, **OFF))) == []


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_off_holds_no_pages_service_route_variable_or_chart_value(shape: str, brand: str) -> None:
    """The amendment's list, read of the render itself: no `pages` service, no route to it, no
    `OSPREY_PAGES_*` variable in the service files (the two secrets `apply` has minted since
    PL9a are in `deployment.env` and nowhere else), no value in the chart."""
    for settings in ({}, OFF):
        files = _render(shape, brand, **settings)
        assert pages_service(shape, files) is None
        assert pages_paths(shape, files) == set()
        for name, data in files.items():
            if name == "deployment.env":
                continue
            assert b"OSPREY_PAGES_" not in data, f"{shape}-{brand}/{name} names a pages variable"
        if shape in HELM:
            assert "pages" not in _values(files)


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ON_COMPOSE)
def test_the_two_minted_secrets_are_the_same_off_and_on(shape: str, brand: str) -> None:
    """The conductor's reading of the amendment (the brief of PL7a2b): the two secrets `apply` has
    minted since PL9a stay as the reference pins them, off or on. `deployment.env` is the
    reference's, byte for byte, with the setting on: the setting adds no secret, and takes none
    away."""
    on = _render(shape, brand, **_on(shape))
    stored = _baseline(shape, brand)
    assert on["deployment.env"] == stored["deployment.env"]
    for name in ("OSPREY_PAGES_CLIENT_SECRET", "OSPREY_PAGES_SESSION_SECRET"):
        assert re.search(rf"(?m)^{name}=PINNED_\d+$", on["deployment.env"].decode("utf-8"))


# ---- 3. on adds the service, its route and its variables, and only that -------------------------


@pytest.mark.parametrize(("shape", "brand"), ON_SHAPE_BRANDS, ids=ON_IDS)
def test_on_holds_the_service_the_route_and_the_variables(shape: str, brand: str) -> None:
    files = _render(shape, brand, **_on(shape))
    assert on_findings(shape, brand, files) == []


@pytest.mark.parametrize(("shape", "brand"), ON_SHAPE_BRANDS, ids=ON_IDS)
def test_on_reaches_the_service_by_its_own_variables_and_by_name(shape: str, brand: str) -> None:
    """The variables are the ones `apps/pages/server/config.ts` reads, with the secrets by
    reference to the env file's two names and no value (a compose file or a chart's values holds no
    secret), and the public origin as the deployment's own."""
    from harness.site import sites

    files = _render(shape, brand, **_on(shape))
    service = pages_service(shape, files)
    assert service is not None
    env = service["env"]
    assert env["OSPREY_PAGES_TREE"] == TREE[brand]
    assert env["OSPREY_PAGES_PORT"] == PAGES_PORT
    assert (
        env["OSPREY_PAGES_PUBLIC_ORIGIN"] == sites(ref.config_for(shape, brand, **_on(shape))).glass
    )
    assert env["OSPREY_PAGES_CONDUIT_URL"] == "http://api:8000"
    secret = env["OSPREY_PAGES_SESSION_SECRET"]
    assert "PINNED_" not in secret and "token" not in secret.lower()
    if shape in COMPOSE:
        assert secret.startswith("${OSPREY_PAGES_SESSION_SECRET:?"), secret
        assert env["OSPREY_PAGES_CLIENT_SECRET"].startswith("${OSPREY_PAGES_CLIENT_SECRET:?")
        assert env["OSPREY_PAGES_OIDC_ISSUER"].endswith("/realms/osprey")
    else:
        assert secret == "secret:OSPREY_PAGES_SESSION_SECRET", secret


@pytest.mark.parametrize(("shape", "brand"), ON_SHAPE_BRANDS, ids=ON_IDS)
def test_on_changes_only_the_files_that_name_the_service(shape: str, brand: str) -> None:
    """On adds what decision 7 describes and only that: the files that differ from the reference
    are the ones that carry a service, a route, or the lock of the images; nothing else moves."""
    on = _render(shape, brand, **_on(shape))
    stored = _baseline(shape, brand)
    chart = {name for name in set(on) | set(stored) if name.startswith(ref.CHART_PREFIX)}
    moved = {name for name in (set(on) | set(stored)) - chart if on.get(name) != stored.get(name)}
    allowed = {
        "compose.yaml", "Caddyfile", "versions.lock", "RUNBOOK.md",
        "values.yaml", "images.yaml",
        # The cloud platform's Terraform: the registry for the image, and the session secret.
        "terraform/ecr.tf", "terraform/secrets.tf",
        # The proof of concept's runbooks list the workloads they install.
        "INSTALL.md", "DECOMMISSION.md",
    }  # fmt: skip
    assert moved <= allowed, f"on moved {sorted(moved - allowed)}"
    assert moved & {"compose.yaml", "values.yaml"}, "on moved neither the compose file nor values"
    assert "versions.lock" in moved, "the lock does not name the page service's image"
    assert all(on[name] == stored[name] for name in chart), "on moved a chart file (off view)"


@pytest.mark.parametrize("shape", ("cluster",))
def test_on_writes_the_chart_value_and_the_chart_carries_none_by_default(shape: str) -> None:
    """The chart's own defaults say nothing of the page service (a chart installed from them
    renders none, and the reference's view of them is what it was: a `pages:` section added to the
    defaults would be a second one beside the reference's own plant, `test_reference_render.py`'s
    `values off`), and the renderer's values hold `pages.enabled: true` with the setting on."""
    default = yaml.safe_load((ref.CHART / "values.yaml").read_text(encoding="utf-8"))
    assert "pages" not in default
    assert _values(_render(shape, "ospreyflow", **_on(shape)))["pages"] == {"enabled": True}
    assert "pages" not in _values(_render(shape, "ospreyflow"))


# ---- 4. a fault in each, in the shape the renderer writes, red while off and red while on --------


@pytest.mark.parametrize(("plant", "shape", "brand"), PLANT_CASES)
def test_a_planted_fault_while_off_is_red(plant: Plant, shape: str, brand: str) -> None:
    """Off is the reference; the plant (a `pages` service, a studio handle, a chart value, or an
    `OSPREY_PAGES_*` variable, written where the renderer would write it) makes the render differ,
    naming the file and the line. Clean first; clean again after."""
    assert ref.differences(shape, brand, _render(shape, brand)) == [], "not clean first"
    with plant.planted(shape):
        found = ref.differences(shape, brand, _render(shape, brand, **OFF))
        found_absent = ref.differences(shape, brand, _render(shape, brand))
    message = "\n".join(found)
    assert found and found_absent, f"{plant.name} in {shape}-{brand}: the plant was not seen"
    assert f"{shape}-{brand}" in message and plant.names in message, message
    assert ref.differences(shape, brand, _render(shape, brand)) == [], "not clean after"


@pytest.mark.parametrize(("plant", "shape", "brand"), ON_PLANT_CASES)
def test_the_same_thing_missing_while_on_is_red(plant: Plant, shape: str, brand: str) -> None:
    """On holds the service, the route, the variable and the chart value: with the one the plant
    names taken out, the on checks fail, naming it. Clean first (the on render holds all of it),
    red with the thing out, clean again after."""
    assert on_findings(shape, brand, _render(shape, brand, **_on(shape))) == [], "not clean first"
    with plant.taken_out(shape):
        found = on_findings(shape, brand, _render(shape, brand, **_on(shape)))
    assert found, f"{plant.name} in {shape}-{brand}: taking it out was not seen"
    assert any(plant.missing in line for line in found), f"red for another reason: {found}"
    assert on_findings(shape, brand, _render(shape, brand, **_on(shape))) == [], "not clean after"


# ---- 5. the cutover ---------------------------------------------------------------------------


@contextlib.contextmanager
def a_complete_govuk_tree(root: Path) -> Iterator[None]:
    """`scripts.tree_parity.govuk_tree_state()` reading a tree where every function has its page:
    the three files it reads, in `root`, set where it looks them up (its own documented seam)."""
    from scripts import tree_parity

    (root / "FUNCTIONS.yaml").write_text(
        "functions:\n  - id: example\n    route: /studio/example\n    status: planned\n",
        encoding="utf-8",
    )
    (root / "routes.yaml").write_text("routes:\n  - /studio/example\n", encoding="utf-8")
    with (
        mock.patch.object(tree_parity, "FUNCTIONS", root / "FUNCTIONS.yaml"),
        mock.patch.object(tree_parity, "ROUTE_LIST", root / "routes.yaml"),
        mock.patch.object(tree_parity, "EXCEPTIONS", root / "PARITY_EXCEPTIONS.yaml"),
    ):
        assert tree_parity.govuk_tree_state() == tree_parity.COMPLETE
        yield


@pytest.mark.parametrize("shape", SHAPES)
def test_the_complete_govuk_tree_with_the_setting_off_is_refused_in_the_amendments_words(
    shape: str, tmp_path: Path
) -> None:
    """Absent and written `false` alike. Rendered through the renderer's own entry, the one every
    shape goes through, and through the reference's staged render for the compose shapes."""
    from harness.render import render

    with a_complete_govuk_tree(tmp_path):
        for settings in ({}, OFF):
            config = ref.config_for(shape, "govuk", **settings)
            with pytest.raises(ValueError, match=re.escape(THE_WORDS)):
                render(config, resolver=ref.resolver)
            with pytest.raises(Exception, match=re.escape(THE_WORDS)):
                ref.render_files(config)


@pytest.mark.parametrize("shape", SHAPES)
def test_the_refusal_is_for_the_complete_tree_alone(shape: str, tmp_path: Path) -> None:
    """Not a refusal of GOV.UK with the setting off (the reference renders), nor of the default
    brand beside a complete tree: only the tree complete, GOV.UK, and the setting off."""
    assert ref.differences(shape, "govuk", _render(shape, "govuk")) == []
    with a_complete_govuk_tree(tmp_path):
        assert ref.differences(shape, "ospreyflow", _render(shape, "ospreyflow")) == []
        off = _off_as_written(shape, _render(shape, "ospreyflow", **OFF))
        assert ref.differences(shape, "ospreyflow", off) == []


@pytest.mark.parametrize("shape", ON_SHAPES)
def test_the_complete_govuk_tree_with_the_setting_on_renders_without_the_workspace(
    shape: str, tmp_path: Path
) -> None:
    """I22: no workspace service and no route to one; every path goes to `pages`. And the workspace
    is there while the tree is partial (the default of the repository today), setting on."""
    partial = _render(shape, "govuk", **_on(shape))
    assert has_a_workspace(shape, partial), "the workspace is gone while the tree is partial"
    assert "/" not in pages_paths(shape, partial)
    with a_complete_govuk_tree(tmp_path):
        files = _render(shape, "govuk", **_on(shape))
    assert not has_a_workspace(shape, files)
    assert pages_paths(shape, files) >= {"/"}, "not every path goes to pages"
    assert on_findings(shape, "govuk", files) == []


def test_the_complete_tree_check_is_the_one_function(tmp_path: Path) -> None:
    """The renderer asks `scripts.tree_parity.govuk_tree_state` (PL7a1's), not a check of its own:
    with it patched to say complete, the same refusal; to say partial, the reference."""
    from scripts import tree_parity

    config = ref.config_for("small", "govuk")
    with mock.patch.object(tree_parity, "govuk_tree_state", lambda *a, **k: "complete"):
        with pytest.raises(Exception, match=re.escape(THE_WORDS)):
            ref.render_files(config)
    with mock.patch.object(tree_parity, "govuk_tree_state", lambda *a, **k: "partial"):
        assert ref.differences("small", "govuk", ref.render_files(config)) == []


# ---- 6. what the page service refuses at start-up (rule 15: the fake must refuse what it does) ----

#: A secret as long as the service wants (`MIN_SECRET_LENGTH`, 32): a stand-in for what `deployment.env`
#: or the cluster's Secret holds, which the render only ever refers to.
A_SECRET = "s" * 40


def _resolved(shape: str, env: dict[str, str]) -> dict[str, str]:
    """The variables as the container would see them: a compose `${NAME:?…}` is the env file's value,
    `${NAME:-default}` its default; a chart's secret reference is the cluster's Secret's value."""
    seen: dict[str, str] = {}
    for name, value in env.items():
        if value.startswith("secret:"):
            seen[name] = A_SECRET
        elif value.startswith("config:"):
            continue  # a chart's config reference: the Valkey address, which this does not check
        elif name.endswith("_SECRET") and value.startswith("${"):
            seen[name] = A_SECRET
        elif value.startswith("${"):
            seen[name] = (
                re.sub(r"^\$\{\w+:-(.*)\}$", r"\1", value) if ":-" in value else "valkey.internal"
            )
        else:
            seen[name] = value
    return seen


#: The service's own settings code, run as it is (round 9: the owner's instruction that the part's
#: tests run the page service's real check, not a stand-in; round 8's fault got through because a
#: Python stand-in compared `url.netloc` and accepted `:443`, which the real check refuses).
PAGES_CONFIG_TS = ref.CORE / "apps" / "pages" / "server" / "config.ts"
#: A small node entry: reads a JSON list of environments on stdin, calls the service's real
#: `loadConfig` with each (it takes the environment it is given, and reads no other), and prints the
#: message of the error it throws, or null. Node strips the types itself (`--experimental-strip-types`).
_NODE_ENTRY = """
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
const { loadConfig } = await import(pathToFileURL(process.env.PAGES_CONFIG_TS).href);
const cases = JSON.parse(readFileSync(0, "utf8"));
const verdicts = cases.map((env) => {
  try {
    loadConfig(env);
    return null;
  } catch (error) {
    return String(error.message);
  }
});
console.log(JSON.stringify(verdicts));
"""


def _real_start_up_check(environments: list[dict[str, str]]) -> list[str | None]:
    """What `apps/pages/server/config.ts`'s `loadConfig` says to each environment: `None` where the
    service starts, its own message where it throws. It is run, never emulated; where node is not
    to be had the test fails (it never passes without having asked the service)."""
    import json
    import os
    import shutil
    import subprocess

    node = shutil.which("node")
    assert node is not None, (
        "node is needed: these tests run the page service's real config.ts (round 9), not a stand-in"
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
    verdicts = json.loads(done.stdout)
    assert len(verdicts) == len(environments)
    return verdicts


def _page_service_refuses(shape: str, files: dict[str, bytes]) -> list[str]:
    """What the page service's real `loadConfig` throws for the environment this render gives it, as
    the container would see it: empty is an environment the service starts with."""
    service = pages_service(shape, files)
    assert service is not None
    [verdict] = _real_start_up_check([_resolved(shape, service["env"])])
    return [] if verdict is None else [verdict]


@pytest.mark.parametrize(("shape", "brand"), ON_SHAPE_BRANDS, ids=ON_IDS)
def test_on_is_an_environment_the_page_service_starts_with(shape: str, brand: str) -> None:
    """The values, not only the names: with the setting on, what each shape renders for the service
    passes the refusals of its own `loadConfig` (an `http` issuer that is not loopback, an origin
    with a path, a short or missing secret). Local-lite on plain HTTP, the demo's own address form,
    is the shape this caught: the service refuses its issuer, so the render refuses to turn the
    service on there (`test_turning_the_service_on_over_plain_http_is_refused_in_words`)."""
    assert _page_service_refuses(shape, _render(shape, brand, **_on(shape))) == []


# ---- 6a. plain HTTP: the render refuses, in words, rather than leave sign-in out ---------------
#
# The owner's ruling of 23 November 2026: the page service's issuer check is not weakened, and the
# fix is in the render: an address the service accepts, or a refusal to turn the service on where
# HTTPS is not available, said in plain words. On local-lite over plain HTTP the identity address is
# `http://id.<name>.localhost:<port>`: not https, and not loopback by the service's own rule, so
# there is no address to give it, and the render refuses.

THE_HTTPS_WORDS = (
    "pages.enabled is on, but the identity address {identity} is neither https nor a loopback "
    "address, and the page service does not sign people in over plain HTTP: serve the identity "
    "address over HTTPS with a certificate the page service trusts, or leave pages.enabled off"
)
THE_TRUST_WORDS = (
    "pages.enabled is on, but the identity address {identity} is served with a certificate from "
    "the front proxy's own internal authority, which the page service does not trust, so people "
    "could not sign in: give the deployment an address with a certificate the page service trusts "
    "(a public name, or network.tls on a Small), or leave pages.enabled off"
)
THE_CA_WORDS = (
    "pages.enabled is on, but the identity address {identity} is served with the deployment's own "
    "certificate (network.tls), which names no CA, so the page service cannot tell which root to "
    "trust for it and people could not sign in: give network.tls a ca (the root certificate that "
    "signed it; a public authority's root will do), or leave pages.enabled off"
)
LOCAL_LITE_HTTPS = {"network": {"public_origin": "https://reference.ospreyflow.localhost:8443"}}
HTTPS_IDENTITY = "https://id.reference.ospreyflow.localhost:8443"
PLAIN_HTTP_IDENTITY = "http://id.reference.ospreyflow.localhost:8081"
SIGN_IN_VARIABLES = (
    "OSPREY_PAGES_OIDC_ISSUER",
    "OSPREY_PAGES_CLIENT_ID",
    "OSPREY_PAGES_CLIENT_SECRET",
)


@pytest.mark.parametrize("brand", BRANDS)
def test_turning_the_service_on_over_plain_http_is_refused_in_words(brand: str) -> None:
    """Local-lite at the reference's own `http://` address with the setting on: refused, in exactly
    these words (the setting, the address, what to do), by an error that is a plain `ValueError`
    like every other refusal of the renderers. Nothing is rendered."""
    config = ref.config_for("local-lite", brand, **ON)
    with pytest.raises(ValueError) as refused:
        ref.render_files(config)
    assert str(refused.value) == THE_HTTPS_WORDS.format(identity=PLAIN_HTTP_IDENTITY)
    assert type(refused.value).__name__ == "PageServiceNeedsHttps"


@pytest.mark.parametrize("brand", BRANDS)
def test_the_refusal_is_for_plain_http_with_the_setting_on_alone(brand: str) -> None:
    """Off over plain HTTP is the reference (nothing is refused, nothing changes); the same address
    with the setting on is refused. The refusal is not a general dislike of local-lite."""
    assert ref.differences("local-lite", brand, _render("local-lite", brand, **OFF)) == []
    assert ref.differences("local-lite", brand, _render("local-lite", brand)) == []
    with pytest.raises(ValueError, match="neither https nor a loopback"):
        _render("local-lite", brand, **ON)


# ---- 6a'. HTTPS the service cannot trust: the render refuses, in words (round 5, case B) ---------
#
# On local-lite over HTTPS on a `.localhost` name there is no `network.tls` (a Small's alone), so
# the front proxy's automatic HTTPS signs the identity name's certificate with Caddy's own internal
# authority, which node does not trust: the service's discovery fetch would fail verification and
# the sign-in would be lost, at sign-in time rather than at render time. The service's certificate
# check is not weakened and not disabled; a trust path would take the authority's root out of the
# proxy's data volume, which also holds the authority's private key. So the render refuses, in
# words, where no trust for the identity name's certificate exists: Caddy's own rule for the names
# it signs itself (`localhost`, `*.localhost`, `*.local`, `*.internal`, `*.home.arpa`, an IP
# address) with no certificate of the organisation's given. A public name, or `network.tls`, is
# trusted (its CA mounted where there is one).


@pytest.mark.parametrize("brand", BRANDS)
def test_local_lite_over_https_is_refused_in_words(brand: str) -> None:
    """HTTPS on a `.localhost` name, setting on: refused in exactly these words, by a `ValueError`
    of its own kind. Off, at the same address, is the reference's twin: nothing is refused."""
    config = ref.config_for("local-lite", brand, **ON, **LOCAL_LITE_HTTPS)
    with pytest.raises(ValueError) as refused:
        ref.render_files(config)
    assert str(refused.value) == THE_TRUST_WORDS.format(identity=HTTPS_IDENTITY)
    assert type(refused.value).__name__ == "PageServiceNeedsTrust"
    assert _render("local-lite", brand, **OFF, **LOCAL_LITE_HTTPS)


def _small(
    brand: str,
    origin: str,
    own: dict[str, str] | None = None,
    *,
    access_key: bool = False,
    pages: bool = True,
) -> Any:
    """A small deployment at `origin`, the page service on, with the organisation's own certificate
    when `own` is given (its optional `ca` in it), and the shared key (`network.access_key`) when
    asked: its configuration."""
    from schemas.deployment import OspreyConfig

    raw = ref.raw_config("small")
    raw["network"]["public_origin"] = origin
    if own is not None:
        raw["network"]["tls"] = {
            "certificate": "/etc/ospreyflow/tls/osprey.crt",
            "key": "/etc/ospreyflow/tls/osprey.key",
            **own,
        }
    if access_key:
        raw["network"]["access_key"] = True
    raw["appearance"] = {**raw.get("appearance", {}), "brand": brand}
    raw["pages"] = {"enabled": pages}
    return OspreyConfig.model_validate(raw)


def _compose_files(config: Any) -> dict[str, bytes]:
    """A compose render's artefacts, rendered directly (nothing staged, no key read)."""
    from harness.render import render

    return {
        name: text.encode("utf-8") if isinstance(text, str) else text
        for name, text in render(config, resolver=ref.resolver).artefacts.items()
    }


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize(
    "origin",
    [
        "https://osprey.internal",
        "https://osprey.local:9443",
        "https://localhost",
        "https://10.1.2.3",
        "https://osprey.home.arpa",
    ],
)
def test_a_small_on_a_name_the_proxy_signs_itself_is_refused_without_a_certificate_of_its_own(
    origin: str, brand: str
) -> None:
    """The refusal is Caddy's own rule for a name it signs itself, not local-lite alone: a Small at
    such a name with no `network.tls` is refused too, in the same words."""
    with pytest.raises(ValueError, match="front proxy's own internal authority") as refused:
        _compose_files(_small(brand, origin))
    assert type(refused.value).__name__ == "PageServiceNeedsTrust"


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize(
    ("origin", "own"),
    [
        ("https://osprey.example.org", None),
        ("https://osprey.example.org:9443", None),
        ("https://osprey.internal", {"ca": "/etc/ospreyflow/tls/org-root.pem"}),
        ("https://osprey.example.org", {"ca": "/etc/ospreyflow/tls/org-root.pem"}),
        ("https://osprey.intra.example.gov.uk", {"ca": "/etc/ospreyflow/tls/org-root.pem"}),
    ],
    ids=[
        "public",
        "public-port",
        "own-with-ca",
        "public-name-own-with-ca",
        "private-name-own-with-ca",
    ],
)
def test_a_name_with_a_certificate_the_service_trusts_is_rendered(
    origin: str, own: dict[str, str] | None, brand: str
) -> None:
    """A public name (Caddy asks a public authority), or the organisation's own certificate
    (`network.tls`) with its CA given, mounted into the service: not refused. The organisation's own
    certificate with no CA is refused, on any name (`test_a_small_with_its_own_certificate_*`)."""
    files = _compose_files(_small(brand, origin, own))
    assert pages_service("small", files) is not None
    assert _trust_findings(files) == []


def _trust_findings(files: dict[str, bytes]) -> list[str]:
    """What is wrong with the service's trust for the certificate its issuer's name is served with,
    read of the rendered files alone: the identity site of the Caddyfile with no `tls` line (the
    proxy signs it, by a public authority or, for the names Caddy keeps for itself, its own
    internal one) on such a name is a certificate the service cannot verify; one with the
    organisation's `tls` line and no CA named for the service is a certificate it cannot be told
    to trust, whatever the name."""
    service = pages_service("small", files)
    if service is None or "OSPREY_PAGES_OIDC_ISSUER" not in service["env"]:
        return []
    from urllib.parse import urlsplit

    host = urlsplit(service["env"]["OSPREY_PAGES_OIDC_ISSUER"]).hostname or ""
    internal = (
        host == "localhost"
        or host.endswith((".localhost", ".local", ".internal", ".home.arpa"))
        or re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host) is not None
    )
    block = _site_block(files["Caddyfile"].decode("utf-8"), host)
    given = "\ttls /certs/" in block
    if internal and not given:
        return [
            f"{host} is signed by the proxy's own internal authority, "
            "which the service does not trust"
        ]
    if given and "NODE_EXTRA_CA_CERTS" not in service["env"]:
        # The organisation's own certificate, on any name: the render cannot tell a public root
        # from a private one, and node trusts a private one only where NODE_EXTRA_CA_CERTS names it.
        return [
            f"{host} is served with the organisation's own certificate "
            "and the service is given no CA for it"
        ]
    return []


@pytest.mark.parametrize("brand", BRANDS)
def test_the_trust_check_is_red_for_a_service_given_the_proxys_own_authority(brand: str) -> None:
    """The planted fault takes the shape the renderer writes: the trust refusal taken out, so a
    Small on an `.internal` name with no certificate of its own is rendered with the sign-in the
    proxy's internal authority signs for. The trust check reads the files, names it, and is clean
    for the same Small with a certificate of its own."""
    config = _small(brand, "https://osprey.internal")
    with _patched("harness.pages_service", "refuse_sign_in_without_trust", _no_trust_refusal):
        found = _trust_findings(_compose_files(config))
    assert any("internal authority" in line for line in found), found
    own = _small(brand, "https://osprey.internal", {"ca": "/etc/ospreyflow/tls/org-root.pem"})
    assert _trust_findings(_compose_files(own)) == []


INTERNAL_NAMES = [
    "https://osprey.internal",
    "https://osprey.local:9443",
    "https://localhost",
    "https://10.1.2.3",
    "https://osprey.home.arpa",
]
#: Every name an organisation's own certificate may be given on: the ones Caddy signs itself, and
#: the rest, which the render cannot tell from a name a public authority signs for (a private
#: authority's name outside the suffixes Caddy knows: round 8's finding).
OWN_CERTIFICATE_NAMES = [
    *INTERNAL_NAMES,
    "https://osprey.intra.example.gov.uk",
    "https://osprey.example.org",
    "https://osprey.example.org:9443",
]


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("origin", OWN_CERTIFICATE_NAMES)
def test_a_small_with_its_own_certificate_and_no_ca_is_refused(origin: str, brand: str) -> None:
    """The organisation's certificate may come from a private root, which node trusts only where
    `NODE_EXTRA_CA_CERTS` names it, and the render cannot tell a private root from a public one by
    the name (an internal suffix is only the names Caddy signs itself: `osprey.intra.example.gov.uk`
    is outside them and may be a private authority's): with `network.tls` and no `ca` the sign-in
    could fail at sign-in time, so it is refused at render time in exactly these words, by a
    `ValueError` of its own kind, on any name. With a `ca` it renders (the next test and
    `test_a_name_with_a_certificate_the_service_trusts_is_rendered`); off it is the reference (the
    setting is off in the reference's own cases)."""
    from urllib.parse import urlsplit

    own = {"ca": "/etc/ospreyflow/tls/org-root.pem"}
    with pytest.raises(ValueError) as refused:
        _compose_files(_small(brand, origin, {}))
    parts = urlsplit(origin)
    identity = f"https://id.{parts.hostname}" + (f":{parts.port}" if parts.port else "")
    assert str(refused.value) == THE_CA_WORDS.format(identity=identity)
    assert type(refused.value).__name__ == "PageServiceNeedsCa"
    if origin == "https://10.1.2.3":
        # With a CA given, an IP address is still no name for the identity provider: the service's
        # own parser refuses `id.10.1.2.3` (round 9: `test_every_origin_form_*`, the `ipv4` row).
        with pytest.raises(ValueError, match="ends in a number") as no_name:
            _compose_files(_small(brand, origin, own))
        assert type(no_name.value).__name__ == "PageServiceNeedsAnOrigin"
        return
    assert pages_service("small", _compose_files(_small(brand, origin, own))) is not None


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize(
    "origin", ["https://osprey.internal", "https://osprey.intra.example.gov.uk"]
)
def test_the_ca_trust_check_is_red_for_an_own_certificate_with_no_ca(
    origin: str, brand: str
) -> None:
    """The planted fault takes the shape the renderer writes: the refusal taken out, so a Small
    with `network.tls` and no `ca` is rendered with the issuer, the proxy's `tls /certs/` line and
    no `NODE_EXTRA_CA_CERTS`, on a name inside Caddy's internal suffixes and on one outside them. The
    check reads the files and names it; it is clean for the same Small with a `ca`."""
    config = _small(brand, origin, {})
    with _patched("harness.pages_service", "refuse_sign_in_without_ca", _no_trust_refusal):
        files = _compose_files(config)
    found = _trust_findings(files)
    assert any("no CA for it" in line for line in found), found
    assert "\ttls /certs/" in files["Caddyfile"].decode("utf-8")
    own = _small(brand, origin, {"ca": "/etc/ospreyflow/tls/org-root.pem"})
    assert _trust_findings(_compose_files(own)) == []


def _no_trust_refusal(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any) -> None:
        return None

    return planted


def _no_refusal_for_plain_http(real: Callable[..., Any]) -> Callable[..., Any]:
    """The renderer without its refusal: nothing says no, and the service is given the issuer the
    deployment has, `http://id.<name>` (what the render wrote before round 2)."""

    def planted(config: Any) -> None:
        return None

    return planted


@pytest.mark.parametrize("brand", BRANDS)
def test_the_start_up_check_is_red_for_an_http_issuer_that_is_not_loopback(brand: str) -> None:
    """The planted fault takes the shape the renderer writes: the refusal taken out, so
    `http://id.<host>/realms/osprey` is written into the service's environment in local-lite. The
    service's own start-up refusal (emulated from `config.ts`) is clean first, red with it, naming
    the rule, and clean again."""
    clean = _page_service_refuses("small", _render("small", brand, **_on("small")))
    assert clean == []
    with _patched(
        "harness.pages_service", "refuse_sign_in_without_https", _no_refusal_for_plain_http
    ):
        found = _page_service_refuses("local-lite", _render("local-lite", brand, **ON))
    assert any("OSPREY_PAGES_OIDC_ISSUER must be an https address" in line for line in found), found
    assert _page_service_refuses("small", _render("small", brand, **_on("small"))) == []


#: A valid environment for the service, bar what a case changes: every value a case does not name
#: is one the service accepts (shown by `test_the_real_check_accepts_a_clean_environment_and_says_why`).
CLEAN_ENVIRONMENT = {
    "OSPREY_PAGES_SESSION_SECRET": A_SECRET,
    "OSPREY_PAGES_PUBLIC_ORIGIN": "https://osprey.example.org",
    "OSPREY_PAGES_OIDC_ISSUER": "https://id.osprey.example.org/realms/osprey",
    "OSPREY_PAGES_CLIENT_ID": "osprey-pages",
    "OSPREY_PAGES_CLIENT_SECRET": A_SECRET,
}


def _real_accepts_issuers(issuers: list[str]) -> list[bool]:
    verdicts = _real_start_up_check(
        [{**CLEAN_ENVIRONMENT, "OSPREY_PAGES_OIDC_ISSUER": issuer} for issuer in issuers]
    )
    return [verdict is None for verdict in verdicts]


#: (issuer, whether the service accepts it, whether the render's own rule is exactly as strict).
#: `127.1` is the one the render is stricter on: the service's URL parser turns it into 127.0.0.1.
ISSUERS = [
    ("https://id.osprey.example.org/realms/osprey", True, True),
    ("HTTPS://ID.OSPREY.EXAMPLE.ORG/realms/osprey", True, True),
    ("https://id.osprey.example.org:9443/realms/osprey", True, True),
    ("http://localhost:8081/realms/osprey", True, True),
    ("http://LOCALHOST:8081/realms/osprey", True, True),
    ("http://127.0.0.1:8081/realms/osprey", True, True),
    ("http://127.1.2.3/realms/osprey", True, True),
    ("http://[::1]:8081/realms/osprey", True, True),
    ("http://127.1/realms/osprey", True, False),
    ("http://id.reference.ospreyflow.localhost:8081/realms/osprey", False, True),
    ("http://keycloak:8080/realms/osprey", False, True),
    ("http://127.0.0.1.example.org/realms/osprey", False, True),
    ("http://[::2]/realms/osprey", False, True),
    ("http://10.0.0.1/realms/osprey", False, True),
    ("ftp://id.osprey.example.org/realms/osprey", False, True),
    ("id.osprey.example.org/realms/osprey", False, True),
]


@pytest.mark.parametrize(("issuer", "accepted", "same"), ISSUERS)
def test_the_rule_the_render_applies_is_the_services_own(
    issuer: str, accepted: bool, same: bool
) -> None:
    """Held to what `apps/pages/server/config.ts` really does with each address (round 9: run, not
    emulated): the render's rule never accepts an address the service refuses, and is exactly as
    strict everywhere but the one form its parser widens. A loopback look-alike host is not one."""
    import harness.pages_service as the_service

    [real] = _real_accepts_issuers([issuer])
    assert real is accepted
    rule = the_service.service_accepts_issuer(issuer)
    assert not (rule and not real), "the render accepts an issuer the service refuses"
    if same:
        assert rule is accepted


def _drop_the_sign_in(real: Callable[..., Any]) -> Callable[..., Any]:
    """The round-2 renderer, as it wrote it: the three sign-in variables left out, nothing said."""

    def planted(config: Any, *, with_sign_in: bool) -> dict[str, str]:
        environment: dict[str, str] = real(config, with_sign_in=with_sign_in)
        for name in (*SIGN_IN_VARIABLES, "NODE_EXTRA_CA_CERTS"):
            environment.pop(name, None)
        return environment

    return planted


def _sign_in_variable_findings(shape: str, files: dict[str, bytes]) -> list[str]:
    """No render of the page service in a shape that runs the identity provider holds fewer than the
    three sign-in variables (the service refuses one without the others, and with none its sign-in
    answers 503). Asked of every shape, the cloud platform's two included: a render of the page
    service there with fewer than three is the finding (it is refused instead:
    `test_turning_the_service_on_for_the_cloud_platform_is_refused_in_words`)."""
    service = pages_service(shape, files)
    if service is None:
        return []
    held = [name for name in SIGN_IN_VARIABLES if name in service["env"]]
    if len(held) == len(SIGN_IN_VARIABLES):
        return []
    return [
        f"the page service holds {len(held)} of the three sign-in variables "
        f"(missing {', '.join(n for n in SIGN_IN_VARIABLES if n not in held)})"
    ]


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ("small", "cluster"))
def test_every_render_of_the_service_holds_all_three_sign_in_variables(
    shape: str, brand: str
) -> None:
    assert _sign_in_variable_findings(shape, _render(shape, brand, **_on(shape))) == []


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ("small", "cluster"))
def test_the_sign_in_variables_check_is_red_for_a_service_given_none(
    shape: str, brand: str
) -> None:
    with _patched("harness.pages_service", "service_environment", _drop_the_sign_in):
        found = _sign_in_variable_findings(shape, _render(shape, brand, **_on(shape)))
    assert found and "0 of the three sign-in variables" in found[0], found
    assert _sign_in_variable_findings(shape, _render(shape, brand, **_on(shape))) == []


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ("small", "cluster"))
def test_an_https_deployment_is_given_its_sign_in(shape: str, brand: str) -> None:
    """Where the issuer is an https address the service accepts, the three sign-in variables are
    written, the secret by reference and never a value, in the compose shape and the cluster's
    chart alike. (The cloud platform has no sign-in for the page service yet, and is refused.)"""
    env = (pages_service(shape, _render(shape, brand, **_on(shape))) or {})["env"]
    assert env["OSPREY_PAGES_OIDC_ISSUER"] == "https://id.osprey.example.org/realms/osprey"
    assert env["OSPREY_PAGES_CLIENT_ID"] == "osprey-pages"
    reference = env["OSPREY_PAGES_CLIENT_SECRET"]
    assert reference in (
        "secret:OSPREY_PAGES_CLIENT_SECRET",
        "${OSPREY_PAGES_CLIENT_SECRET:?set in the deployment env file}",
    ), reference


THE_CLOUD_WORDS = (
    "pages.enabled is on, but the page service cannot run on the cloud-platform shape yet: people "
    "would have no way to sign in to it there (the chart gives it no egress to the identity "
    "provider, and it has no registration with the organisation's Entra ID: ADR-148 Amendment 23). "
    "Leave pages.enabled off for this deployment until the page service is offered on the "
    "cloud-platform shape"
)


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", CLOUD_SHAPES)
def test_turning_the_service_on_for_the_cloud_platform_is_refused_in_words(
    shape: str, brand: str
) -> None:
    """The owner's ruling of 23 November 2026 (case C, option A): the cloud platform, development
    and the proof of concept, with the setting on, is refused in exactly these words (the setting,
    the shape, why, what to do), by a `ValueError` of its own kind. Nothing is rendered: no page
    service without its three sign-in variables, in any shape."""
    config = ref.config_for(shape, brand, **ON)
    with pytest.raises(ValueError) as refused:
        ref.render_files(config)
    assert str(refused.value) == THE_CLOUD_WORDS
    assert type(refused.value).__name__ == "PageServiceNotOnThisShape"


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", CLOUD_SHAPES)
def test_the_cloud_refusal_is_for_the_setting_on_alone(shape: str, brand: str) -> None:
    """Off, written or absent, is the reference (nothing is refused); the refusal is not a general
    dislike of the shape."""
    written = _off_as_written(shape, _render(shape, brand, **OFF))
    assert ref.differences(shape, brand, written) == []
    assert ref.differences(shape, brand, _render(shape, brand)) == []


def _no_cloud_refusal(real: Callable[..., Any]) -> Callable[..., Any]:
    """The round-5 renderer, as it wrote it: the cloud platform rendered with the page service on
    and nothing said (the refusal taken out; the render is the renderer's own)."""

    def planted(config: Any) -> None:
        return None

    return planted


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", CLOUD_SHAPES)
def test_the_cloud_check_is_red_for_a_render_that_holds_a_service_without_its_sign_in(
    shape: str, brand: str
) -> None:
    """With the refusal taken out the cloud platform renders the page service with none of the three
    sign-in variables (the chart has no identity provider of ours and no egress to Entra ID), which
    the same sign-in check every other shape is held to reports; with the refusal in, there is no
    render to hold at all."""
    with _patched("harness.pages_service", "refuse_on_cloud_platform", _no_cloud_refusal):
        found = _sign_in_variable_findings(shape, _render(shape, brand, **ON))
    assert found and "0 of the three sign-in variables" in found[0], found
    with pytest.raises(ValueError, match="cannot run on the cloud-platform shape"):
        _render(shape, brand, **ON)


# ---- 6b. the sign-in it is given is reached without a route out ---------------------------------
#
# The service fetches its issuer itself, at sign-in (`apps/pages/server/oidc.ts`: `discovery`), and
# the issuer is the public identity name (`https://id.<host>/realms/osprey`: openid-client checks
# the discovery document's `issuer` against the address it asked, so the internal Keycloak address
# the Conduit uses is not one the service can be given). The owner's ruling of 23 November 2026:
# the page service is on the internal network `osprey` alone (ADR-114 Amendment 7: no route out;
# `egress_needs` is not widened for it), and reaches the identity name through **a network alias for
# that name on the proxy, inside `osprey`**.


def _identity_alias(config: Any) -> str:
    from harness.site import sites

    return f"id.{sites(config).host}"


def _networks(service: dict[str, Any]) -> dict[str, Any]:
    """A compose service's `networks`, list or mapping, as a mapping of name to its settings."""
    given = service.get("networks") or {}
    return {name: {} for name in given} if isinstance(given, list) else dict(given)


def _labels(caddyfile: str) -> list[tuple[int, list[str]]]:
    """Each site block's line number and address list: a line at the margin that ends in `{`, other
    than the global block's own (`{` alone), its addresses split on the commas."""
    found = []
    for number, line in enumerate(caddyfile.splitlines()):
        if line.endswith("{") and line != "{" and not line.startswith(("\t", " ", "#")):
            found.append((number, [a.strip() for a in line[:-1].split(",")]))
    return found


def _site_block(caddyfile: str, host: str) -> str:
    """The text of the site block whose address list names `host` (empty when none does)."""
    from urllib.parse import urlsplit

    lines = caddyfile.splitlines()
    for number, addresses in _labels(caddyfile):
        if any(urlsplit(address).hostname == host for address in addresses):
            end = next(i for i in range(number, len(lines)) if lines[i] == "}")
            return "\n".join(lines[number : end + 1])
    return ""


def _proxy_listens_on(caddyfile: str, host: str) -> set[int]:
    """The ports Caddy listens on, inside the container, for the `https://` addresses of `host`: an
    address's own port, else the global `https_port` (443 where none is written)."""
    from urllib.parse import urlsplit

    written = re.search(r"(?m)^\thttps_port (\d+)$", caddyfile)
    default = int(written[1]) if written else 443
    ports = set()
    for _number, addresses in _labels(caddyfile):
        for address in addresses:
            url = urlsplit(address)
            if url.scheme == "https" and url.hostname == host:
                ports.add(url.port or default)
    return ports


def _reach_findings(files: dict[str, bytes]) -> list[str]:
    """Whether the issuer can be reached, read of the rendered files alone: the alias takes the
    service to the proxy's container, where a connection to the issuer's port needs a listener. The
    issuer carries the origin's port (Keycloak reports its issuer as the public address, and the
    service checks the discovery document against the address it asked), which is not the proxy's
    own in-container one (Small's own certificate: 8443; a published `P:443` for a port that is not
    443), so the proxy must listen on it for that name too."""
    service = pages_service("small", files)
    if service is None or "OSPREY_PAGES_OIDC_ISSUER" not in service["env"]:
        return []
    from urllib.parse import urlsplit

    issuer = urlsplit(service["env"]["OSPREY_PAGES_OIDC_ISSUER"])
    port = issuer.port or 443
    listening = _proxy_listens_on(files["Caddyfile"].decode("utf-8"), issuer.hostname or "")
    if port in listening:
        return []
    return [
        f"the issuer {issuer.hostname}:{port} is not a port the proxy listens on inside the "
        f"container for that name (it listens on {sorted(listening) or 'none'})"
    ]


def _network_findings(shape: str, brand: str, files: dict[str, bytes]) -> list[str]:
    """What is wrong with the page service's reach to its issuer in a compose render that holds it:
    the service on `osprey` alone, and the proxy answering to the identity name on `osprey`."""
    services = yaml.safe_load(files["compose.yaml"].decode("utf-8"))["services"]
    pages = services.get("pages")
    if pages is None or "OSPREY_PAGES_OIDC_ISSUER" not in pages.get("environment", {}):
        return []
    found: list[str] = _reach_findings(files) + _trust_findings(files)
    if _networks(pages) != {"osprey": {}}:
        found.append(f"pages is on {sorted(_networks(pages))}, not the internal network alone")
    config = ref.config_for(shape, brand, **_on(shape))
    wanted = _identity_alias(config)
    proxy = _networks(services["proxy"])
    if wanted not in (proxy.get("osprey") or {}).get("aliases", []):
        found.append(f"the proxy has no alias {wanted} on the internal network osprey")
    for name, settings in proxy.items():
        if name != "osprey" and wanted in (settings or {}).get("aliases", []):
            found.append(f"the proxy has the alias {wanted} on {name}, which reaches out")
    return found


def _pages_also_on_egress(real: Callable[..., Any]) -> Callable[..., Any]:
    """The round-3 renderer, as it wrote it: `networks: [osprey, egress]` for `pages`."""

    def planted(config: Any, services: dict[str, Any]) -> None:
        real(config, services)
        services["pages"]["networks"] = ["osprey", "egress"]

    return planted


def _proxy_without_the_alias(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, services: dict[str, Any]) -> None:
        real(config, services)
        services["proxy"]["networks"] = ["osprey", "egress"]

    return planted


def _proxy_alias_on_egress(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, services: dict[str, Any]) -> None:
        real(config, services)
        services["proxy"]["networks"] = {
            "osprey": {},
            "egress": {"aliases": [_identity_alias(config)]},
        }

    return planted


def _proxy_alias_for_the_wrong_name(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, services: dict[str, Any]) -> None:
        from harness.site import sites

        real(config, services)
        services["proxy"]["networks"] = {
            "osprey": {"aliases": [sites(config).host]},
            "egress": {},
        }

    return planted


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ON_COMPOSE)
def test_the_page_service_is_on_the_internal_network_alone_with_the_alias_on_the_proxy(
    shape: str, brand: str
) -> None:
    files = _render(shape, brand, **_on(shape))
    services = yaml.safe_load(files["compose.yaml"].decode("utf-8"))["services"]
    assert services["pages"]["networks"] == ["osprey"]
    assert services["proxy"]["networks"] == {
        "osprey": {"aliases": [_identity_alias(ref.config_for(shape, brand, **_on(shape)))]},
        "egress": {},
    }
    assert _network_findings(shape, brand, files) == []
    assert all(name in services["pages"]["environment"] for name in SIGN_IN_VARIABLES)


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ON_COMPOSE)
def test_the_alias_widens_nothing_the_deployment_reaches_out_to(shape: str, brand: str) -> None:
    """`egress_needs` is not widened for the page service: the services on `egress` are the ones the
    reference has (the proxy and the two model fetchers), and no other."""
    on = yaml.safe_load(_render(shape, brand, **_on(shape))["compose.yaml"].decode("utf-8"))
    base = yaml.safe_load(_baseline(shape, brand)["compose.yaml"].decode("utf-8"))

    def reaching_out(document: dict[str, Any]) -> set[str]:
        return {n for n, s in document["services"].items() if "egress" in _networks(s)}

    assert reaching_out(on) == reaching_out(base)
    assert "pages" not in reaching_out(on)


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ("cluster",))
def test_the_page_service_in_a_chart_is_given_no_route_out_but_the_managed_cache(
    shape: str, brand: str
) -> None:
    """A chart's page service is on `egress` for the one feature the deployment configures that
    needs it: the managed Valkey outside the cluster (`egress_needs`, the one line that names the
    service), which every chart shape has (the cloud platform's derived cluster configuration
    names its ElastiCache). Its issuer is not a reason (the compose shapes, which have no managed
    cache, hold it off `egress`: `test_the_alias_widens_nothing_the_deployment_reaches_out_to`).
    The cloud platform's per-workload policy is not touched by this slice."""
    service = pages_service(shape, _render(shape, brand, **_on(shape)))
    assert service is not None
    if shape == "cluster":
        assert ref.config_for(shape, brand, **_on(shape)).external.valkey is not None
    assert service["egress"] is True


NETWORK_PLANTS = [
    ("on egress", _pages_also_on_egress, "not the internal network alone"),
    ("no alias", _proxy_without_the_alias, "no alias"),
    ("alias on egress", _proxy_alias_on_egress, "reaches out"),
    ("wrong name", _proxy_alias_for_the_wrong_name, "no alias"),
]

#: Faults in the proxy's configuration, in the shape the renderer writes it (the identity site's
#: address line), planted through `render_caddyfile` as the compose renderer calls it.


def _identity_on_another_port(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any, **kwargs: Any) -> str:
        text: str = real(config, **kwargs)
        changed = re.sub(
            r"(?m)^(https://id\.[^\s,{:]+)(?:, https://id\.[^\s,{]+)? \{$", r"\1:9999 {", text
        )
        assert changed != text, "the real Caddyfile has no identity site to move"
        return changed

    return planted


def _without_the_extra_address(real: Callable[..., Any]) -> Callable[..., Any]:
    """The round-4 renderer, as it wrote it: the identity site on the one address, the proxy's own
    in-container port alone."""

    def planted(config: Any, **kwargs: Any) -> str:
        text: str = real(config, **kwargs)
        changed = re.sub(r"(?m)^(https://id\.[^\s,{]+), https://id\.[^\s,{]+ \{$", r"\1 {", text)
        assert changed != text, "the real Caddyfile has no extra identity address to take out"
        return changed

    return planted


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ON_COMPOSE)
@pytest.mark.parametrize(
    ("plant", "wrapper", "says"), NETWORK_PLANTS, ids=[plant[0] for plant in NETWORK_PLANTS]
)
def test_the_network_check_is_red_for_each_fault_in_the_shape_the_renderer_writes(
    plant: str, wrapper: Any, says: str, shape: str, brand: str
) -> None:
    assert _network_findings(shape, brand, _render(shape, brand, **_on(shape))) == []
    with _patched("harness.render", "_place_on_networks", wrapper):
        found = _network_findings(shape, brand, _render(shape, brand, **_on(shape)))
    assert any(says in line for line in found), f"{plant}: {found}"
    assert _network_findings(shape, brand, _render(shape, brand, **_on(shape))) == []


# ---- 6b'. the issuer's port is one the proxy listens on inside the container (round 5, case A) ---
#
# The alias takes the service to the proxy's container, and the issuer is the public identity name
# *with the origin's port*: Keycloak reports its issuer as `KC_HOSTNAME` (the public address)
# whichever door a request came through, and the service checks the discovery document's `issuer`
# against the address it asked, so an issuer carrying the proxy's in-container port would be
# refused. The
# service therefore connects to the origin's port in the proxy's container. A Small on its own
# certificate listens on 8443 there (the host's published 443 is mapped to it, which the internal
# network does not use), and any Small at a port that is not 443 is published `P:443`. So with the
# service on, the identity site is also given an address at the origin's port: one more listener for
# that name, inside the container, on the internal network. Nothing is published that was not, no
# network is added, and nothing the service checks is touched.
#
# Measured, 23 November 2026, on a throwaway Caddy 2.11.4 on its own network, as the account the
# own-certificate proxy runs as (65534): with `https://id.<host>` alone the alias answers on 8443
# and refuses on 443 ("Connection refused": the fault); with `https://id.<host>,
# https://id.<host>:443` it answers on both (Docker lets a container's own processes bind a low
# port).

CA_ON_THE_HOST = "/etc/ospreyflow/tls/org-root.pem"
LISTENER_CASES = {
    "public-name": ("https://osprey.example.org", None, False),
    "public-name-port": ("https://osprey.example.org:9443", None, True),
    "own-certificate": ("https://osprey.example.org", {"ca": CA_ON_THE_HOST}, True),
    "own-certificate-port": ("https://osprey.example.org:9443", {"ca": CA_ON_THE_HOST}, True),
    "own-certificate-8443": ("https://osprey.example.org:8443", {"ca": CA_ON_THE_HOST}, False),
}


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("case", LISTENER_CASES)
def test_the_issuers_port_is_one_the_proxy_listens_on_inside_the_container(
    case: str, brand: str
) -> None:
    origin, own, extra = LISTENER_CASES[case]
    files = _compose_files(_small(brand, origin, own))
    assert _reach_findings(files) == []
    config = _small(brand, origin, own)
    names = _identity_host(config)
    caddyfile = files["Caddyfile"].decode("utf-8")
    port = int(re.search(r":(\d+)$", origin).group(1)) if re.search(r":\d+$", origin) else 443
    assert port in _proxy_listens_on(caddyfile, names)
    # The extra address is written where the origin's port is not the proxy's own, and nowhere else.
    block = [addresses for _n, addresses in _labels(caddyfile) if f"https://{names}" in addresses]
    assert (len(block[0]) == 2) is extra, block


def _identity_host(config: Any) -> str:
    from harness.site import sites

    return f"id.{sites(config).host}"


def test_the_routes_reader_names_a_site_with_two_addresses() -> None:
    """`harness.site.routes` (what `status` and the front-proxy tests read) takes a site block whose
    address line holds two addresses, as the identity site now can: it is named by its first."""
    from harness import site

    config = _small("ospreyflow", "https://osprey.example.org:9443", {"ca": CA_ON_THE_HOST})
    text = _compose_files(config)["Caddyfile"].decode("utf-8")
    assert "https://id.osprey.example.org, https://id.osprey.example.org:9443 {" in text
    assert site.routes(text)["id.osprey.example.org"] == "keycloak:8080"


def test_a_cluster_proxy_is_given_no_extra_address() -> None:
    """The cluster has no alias, so its Caddyfile (rendered `doors=False`) has the one address."""
    from harness.site import render_caddyfile

    config = ref.config_for("cluster", "govuk", **ON)
    text = render_caddyfile(config, doors=False)
    assert [a for _n, a in _labels(text) if "https://id.osprey.example.org" in a] == [
        ["https://id.osprey.example.org"]
    ]


FAULTS_IN_THE_LISTENER = [
    ("no extra address", _without_the_extra_address, "not a port the proxy listens on"),
    ("another port", _identity_on_another_port, "not a port the proxy listens on"),
]


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize(
    "case", [name for name, (_o, _t, extra) in LISTENER_CASES.items() if extra]
)
def test_the_listener_check_is_red_when_the_extra_address_is_taken_out(
    case: str, brand: str
) -> None:
    """The round-4 renderer's Caddyfile for exactly the setups it failed (an own certificate; a port
    that is not 443): the identity site on its one address. Clean first, red naming the port, clean
    after."""
    origin, own, _extra = LISTENER_CASES[case]
    assert _reach_findings(_compose_files(_small(brand, origin, own))) == []
    with _patched("harness.render", "render_caddyfile", _without_the_extra_address):
        found = _reach_findings(_compose_files(_small(brand, origin, own)))
    assert any("not a port the proxy listens on" in line for line in found), found
    assert _reach_findings(_compose_files(_small(brand, origin, own))) == []


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("case", LISTENER_CASES)
def test_the_listener_check_is_red_when_the_identity_site_is_on_another_port(
    case: str, brand: str
) -> None:
    origin, own, _extra = LISTENER_CASES[case]
    with _patched("harness.render", "render_caddyfile", _identity_on_another_port):
        found = _reach_findings(_compose_files(_small(brand, origin, own)))
    assert any("not a port the proxy listens on" in line for line in found), found


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("case", LISTENER_CASES)
def test_the_extra_listener_publishes_nothing_and_adds_no_network(case: str, brand: str) -> None:
    """The proxy's published ports, its networks (bar the alias, which is round 4's), and every
    other service of the compose file are what they are with the setting off at the same address:
    the listener is inside the container, on `osprey`, and widens nothing."""
    origin, own, _extra = LISTENER_CASES[case]
    on = yaml.safe_load(_compose_files(_small(brand, origin, own))["compose.yaml"])["services"]
    config = _small(brand, origin, own)
    raw = config.model_dump(mode="json", exclude_unset=True)
    raw["pages"] = {"enabled": False}
    from harness.render import render

    from schemas.deployment import OspreyConfig

    off_files = render(OspreyConfig.model_validate(raw), resolver=ref.resolver).artefacts
    off = yaml.safe_load(off_files["compose.yaml"])["services"]
    assert on["proxy"]["ports"] == off["proxy"]["ports"]
    assert {k: v for k, v in on["proxy"].items() if k != "networks"} == {
        k: v for k, v in off["proxy"].items() if k != "networks"
    }
    assert set(on) - set(off) == {"pages"}
    assert _networks(on["pages"]) == {"osprey": {}}


def _small_with_its_own_certificate(brand: str, **tls: str) -> dict[str, Any]:
    """The `pages` service of a small deployment on the organisation's own certificate, rendered
    directly (nothing staged, no key read)."""
    from harness.render import render

    from schemas.deployment import OspreyConfig

    raw = ref.raw_config("small")
    raw["network"]["tls"] = {
        "certificate": "/etc/ospreyflow/tls/osprey.crt",
        "key": "/etc/ospreyflow/tls/osprey.key",
        **tls,
    }
    raw["pages"] = {"enabled": True}
    config = OspreyConfig.model_validate(raw)
    compose = yaml.safe_load(render(config, resolver=ref.resolver).artefacts["compose.yaml"])
    return dict(compose["services"]["pages"])


def _ca_findings(service: dict[str, Any]) -> list[str]:
    """Where the organisation's CA is mounted into `pages` and where node is told to read it."""
    from harness import pages_service as service_module

    mounted = [v for v in service.get("volumes", []) if v.startswith(f"{CA_ON_THE_HOST}:")]
    named = service["environment"].get("NODE_EXTRA_CA_CERTS")
    wanted = service_module.CA_IN_SERVICE
    found = []
    if mounted != [f"{CA_ON_THE_HOST}:{wanted}:ro"]:
        found.append(f"the organisation's CA is not mounted read-only at {wanted}")
    if named != wanted:
        found.append("NODE_EXTRA_CA_CERTS does not name the mounted CA")
    return found


@pytest.mark.parametrize("brand", BRANDS)
def test_the_service_trusts_the_organisations_ca_it_signs_in_through(brand: str) -> None:
    """As Keycloak's truststore is given `network.tls.ca` (ADR-114 Amendment 33 decision 4): the
    service's own discovery, keys and token request go to the identity name, whose certificate is
    the organisation's. Without a CA there is nothing to trust it by: refused (round 8)."""
    assert _ca_findings(_small_with_its_own_certificate(brand, ca=CA_ON_THE_HOST)) == []
    with pytest.raises(ValueError, match="names no CA"):
        _small_with_its_own_certificate(brand)


def test_the_ca_check_is_red_for_a_service_that_is_not_told_to_read_it() -> None:
    from harness import pages_service as service_module

    def without_the_variable(real: Callable[..., Any]) -> Callable[..., Any]:
        def planted(config: Any, **kwargs: Any) -> dict[str, str]:
            environment: dict[str, str] = real(config, **kwargs)
            environment.pop("NODE_EXTRA_CA_CERTS", None)
            return environment

        return planted

    with _patched("harness.pages_service", "service_environment", without_the_variable):
        found = _ca_findings(_small_with_its_own_certificate("govuk", ca=CA_ON_THE_HOST))
    # The mount follows the variable (both are written, or neither), so both findings are reported.
    assert "NODE_EXTRA_CA_CERTS does not name the mounted CA" in found, found
    assert service_module.CA_IN_SERVICE


# ---- 6b'''. the shared key (`network.access_key`, ADR-114 Amendment 41) with the service on (round 8) --
#
# A Small that asks for the shared key puts every route to the Glass behind it: the Caddyfile's
# `route { basic_auth ... }`, in which each name's handlers sit. The page service's routes (the
# matcher `@pages` and the `handle @pages` that sends it to `pages`, or every path once a GOV.UK
# tree is complete) are added to that site, and a handler written outside the `route`, or ahead of
# `basic_auth`, would serve the page service's paths (`/session`, `/assets/pages`, `/studio`, or
# everything) without the key. A security rule: nothing here is accepted narrower. The service's
# own server-side requests to the identity name, through the alias, carry no pass, so each must be
# on the key's open list (the three the Glass asks from its own origin: discovery, keys, token).
#
# Caddy is not on the path of this test (it runs where `NEEDS_CADDY` is satisfied,
# `test_access_key_proxy.py`): the Caddyfile is read here as the tree of blocks it is, so a missing
# or extra brace, a matcher used and never declared, and a handler outside the key's `route` are
# each found by reading it.

#: What the page service asks the identity provider itself, from the proxy's alias: `openid-client`'s
#: discovery (`.well-known/openid-configuration`), the key set the discovery names (`certs`, read by
#: `createRemoteJWKSet`) and the token request of the code grant (`token`, the client's secret in the
#: body: `ClientSecretPost`, which is the library's default). `apps/pages/server/oidc.ts` makes no
#: other call to it from the service (the authorisation address is the person's browser's).
THE_SERVICES_OWN_REQUESTS = (
    "/realms/osprey/.well-known/openid-configuration",
    "/realms/osprey/protocol/openid-connect/certs",
    "/realms/osprey/protocol/openid-connect/token",
)
KEY_ORIGIN = "https://osprey.example.org"


class _Block:
    """One `label {` of a Caddyfile and what is in it: leaf lines (`str`) and nested blocks."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.children: list[_Block | str] = []

    def text(self) -> str:
        return "\n".join(
            [self.label, *(c if isinstance(c, str) else c.text() for c in self.children)]
        )


def _parse_caddyfile(text: str) -> list[_Block]:
    """The top-level blocks (the global options and each site) of a Caddyfile; refuses braces that
    do not match, as Caddy does."""
    top: list[_Block] = []
    stack: list[_Block] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "}":
            if not stack:
                raise ValueError(f"line {number}: a closing brace with nothing open")
            stack.pop()
        elif line.endswith("{"):
            block = _Block(line[:-1].strip())
            (stack[-1].children if stack else top).append(block)
            stack.append(block)
        elif stack:
            stack[-1].children.append(line)
        elif line.startswith("import "):
            continue  # the key file's three snippets, imported at the top
        else:
            raise ValueError(f"line {number}: {line!r} outside every block")
    if stack:
        raise ValueError(f"{stack[-1].label!r} is never closed")
    return top


def _key_findings(files: dict[str, bytes]) -> list[str]:
    """What is wrong with the front proxy's configuration of a Small that asks for the shared key,
    with the page service on, read of the rendered Caddyfile alone."""
    try:
        sites = [b for b in _parse_caddyfile(files["Caddyfile"].decode("utf-8")) if b.label]
    except ValueError as refused:
        return [f"the Caddyfile is not well formed: {refused}"]
    found: list[str] = []
    for site in sites:
        if not site.label.startswith("https://"):
            continue
        route = next(
            (c for c in site.children if isinstance(c, _Block) and c.label == "route"), None
        )
        for child in site.children:
            if child is route:
                continue
            leaf = child if isinstance(child, str) else child.text()
            if "pages:" in leaf or (not leaf.startswith("@pages ") and "@pages" in leaf):
                found.append(f"{site.label}: the page service's route is outside the key's route")
        uses = route is not None and "handle @pages" in route.text()
        if uses and not any(isinstance(c, str) and c.startswith("@pages ") for c in site.children):
            found.append(f"{site.label}: @pages is used and never declared in the site")
        if route is not None:
            order = [c if isinstance(c, str) else c.label for c in route.children]
            asked = next((i for i, c in enumerate(order) if c.startswith("basic_auth ")), None)
            served = next(
                (
                    i
                    for i, c in enumerate(route.children)
                    if "pages:" in (c if isinstance(c, str) else c.text())
                ),
                None,
            )
            if served is not None and (asked is None or served < asked):
                found.append(f"{site.label}: the page service is served before the key is asked")
        if site.label.startswith("https://id."):
            locked = next(
                (c for c in site.children if isinstance(c, _Block) and c.label == "@osprey_locked"),
                None,
            )
            listed = locked.text() if locked else ""
            for path in THE_SERVICES_OWN_REQUESTS:
                if f'"{path}"' not in listed:
                    found.append(f"{site.label}: {path} is not on the key's open list")
    return found


def _with_key(brand: str) -> dict[str, bytes]:
    return _compose_files(_small(brand, KEY_ORIGIN, access_key=True))


def _pages_handled_ahead_of_the_key(real: Callable[..., Any]) -> Callable[..., Any]:
    """The renderer with the page service's `handle @pages` written ahead of the key's `route`, at
    the site (the shape a change that emits it before wrapping the rest would write)."""

    def planted(host: str, *, identity: bool, handlers: list[str]) -> list[str]:
        if handlers[:1] == ["\thandle @pages {"]:
            return [*handlers[:3], *real(host, identity=identity, handlers=handlers[3:])]
        return list(real(host, identity=identity, handlers=handlers))

    return planted


def _every_path_served_with_no_key(real: Callable[..., Any]) -> Callable[..., Any]:
    """The complete tree's `handle { reverse_proxy pages:8090 }` written with no `route` at all."""

    def planted(host: str, *, identity: bool, handlers: list[str]) -> list[str]:
        if any("pages:" in line for line in handlers):
            return list(handlers)
        return list(real(host, identity=identity, handlers=handlers))

    return planted


def _route_never_closed(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(host: str, *, identity: bool, handlers: list[str]) -> list[str]:
        return list(real(host, identity=identity, handlers=handlers))[:-1]

    return planted


def _without_the_matcher(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(paths: list[str]) -> str:
        return ""

    return planted


def _open_list_without(path_end: str) -> Callable[[Any], Any]:
    def narrowed(real: tuple[str, ...]) -> Any:
        return tuple(p for p in real if not p.endswith(path_end))

    return narrowed


@pytest.mark.parametrize("brand", BRANDS)
def test_with_the_shared_key_every_route_to_the_page_service_is_behind_it(brand: str) -> None:
    """A Small that asks for the key, the service on: the Caddyfile is well formed, `@pages` is
    declared in the site and used inside the key's `route` after `basic_auth`, no handler sends a
    path to `pages` outside it, and the three requests the service itself makes to the identity name
    are on the open list."""
    files = _with_key(brand)
    assert _key_findings(files) == []
    caddyfile = files["Caddyfile"].decode("utf-8")
    assert "\t\tbasic_auth @osprey_locked bcrypt OspreyFlow {" in caddyfile
    assert "reverse_proxy pages:8090" in caddyfile, "the page service is not routed at all"
    assert pages_service("small", files)["env"]["OSPREY_PAGES_OIDC_ISSUER"].endswith(
        "/realms/osprey"
    )


def test_with_the_shared_key_a_complete_govuk_tree_is_served_from_inside_the_key(
    tmp_path: Path,
) -> None:
    """I22 with the key: every path goes to `pages`, and every one is behind the key."""
    with a_complete_govuk_tree(tmp_path):
        files = _with_key("govuk")
    caddyfile = files["Caddyfile"].decode("utf-8")
    assert "reverse_proxy pages:8090" in caddyfile and "@pages" not in caddyfile
    assert not has_a_workspace("small", files)
    assert _key_findings(files) == []


@pytest.mark.parametrize("brand", BRANDS)
def test_the_key_check_is_red_for_the_page_service_ahead_of_the_key(brand: str) -> None:
    """Clean, then red with the handler written outside the route (the finding of round 8), then
    clean."""
    assert _key_findings(_with_key(brand)) == []
    with _patched("harness.site", "_behind_the_key", _pages_handled_ahead_of_the_key):
        found = _key_findings(_with_key(brand))
    assert any("outside the key's route" in line for line in found), found
    assert _key_findings(_with_key(brand)) == []


def test_the_key_check_is_red_for_every_path_served_with_no_key(tmp_path: Path) -> None:
    with a_complete_govuk_tree(tmp_path):
        assert _key_findings(_with_key("govuk")) == []
        with _patched("harness.site", "_behind_the_key", _every_path_served_with_no_key):
            found = _key_findings(_with_key("govuk"))
    assert any("outside the key's route" in line for line in found), found


@pytest.mark.parametrize("brand", BRANDS)
def test_the_key_check_is_red_for_a_caddyfile_that_is_not_well_formed(brand: str) -> None:
    with _patched("harness.site", "_behind_the_key", _route_never_closed):
        found = _key_findings(_with_key(brand))
    assert any("not well formed" in line for line in found), found
    with _patched("harness.pages_service", "caddy_matcher", _without_the_matcher):
        found = _key_findings(_with_key(brand))
    assert any("never declared" in line for line in found), found


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("path_end", ["/.well-known/openid-configuration", "/certs", "/token"])
def test_the_key_check_is_red_when_a_request_the_service_makes_is_not_on_the_open_list(
    path_end: str, brand: str
) -> None:
    with _patched("harness.site", "OPEN_ON_THE_IDENTITY_PROVIDER", _open_list_without(path_end)):
        found = _key_findings(_with_key(brand))
    assert any(f"{path_end} is not on the key's open list" in line for line in found), found


# ---- 6c. the cluster's install makes the secrets the pod names --------------------------------


def _chart(brand: str, **settings: Any) -> tuple[Any, dict[str, Any]]:
    """The cluster's configuration and its rendered chart values (rendered before any plant, so a
    plant in the install's own code is not also a plant in the chart)."""
    return ref.config_for("cluster", brand, **settings), _values(
        _render("cluster", brand, **settings)
    )


def _install(config: Any, values: dict[str, Any], kept: dict[str, str] | None = None) -> Any:
    """The cluster install's Secret for the chart's own `secrets` section
    (`harness.cluster_install.secret_values`, which the installer writes through)."""
    from harness import cluster_install

    return cluster_install.secret_values(
        config,
        values=values,
        environ={"OSPREY_POSTGRES_PASSWORD": "given-for-the-managed-server"},
        kept=kept or {},
    )


PAGES_SECRETS = ("OSPREY_PAGES_CLIENT_SECRET", "OSPREY_PAGES_SESSION_SECRET")


@pytest.mark.parametrize("brand", BRANDS)
def test_a_cluster_install_with_the_setting_on_makes_every_secret_the_pod_names(brand: str) -> None:
    config, values = _chart(brand, **ON)
    pairs = _install(config, values)
    named = {
        entry["secret"]
        for workload in values["workloads"]
        if workload["name"] == "pages"
        for entry in workload["env"]
        if "secret" in entry
    }
    assert set(PAGES_SECRETS) <= named
    assert named <= set(pairs), sorted(named - set(pairs))
    first, second = (pairs[name] for name in PAGES_SECRETS)
    # The service refuses a session secret under 32 characters; each is made as `apply` makes Lite's.
    assert len(first) >= 32 and len(second) >= 32 and first != second


@pytest.mark.parametrize("brand", BRANDS)
def test_a_secret_the_cluster_already_holds_is_kept(brand: str) -> None:
    held = {name: f"held-{name.lower()}-" + "x" * 30 for name in PAGES_SECRETS}
    config, values = _chart(brand, **ON)
    pairs = _install(config, values, held)
    assert {name: pairs[name] for name in PAGES_SECRETS} == held


@pytest.mark.parametrize("brand", BRANDS)
def test_a_cluster_install_with_the_setting_off_makes_neither(brand: str) -> None:
    config, values = _chart(brand)
    pairs = _install(config, values)
    assert not [name for name in PAGES_SECRETS if name in pairs]
    assert not [name for name in PAGES_SECRETS if name in values["secrets"]["keys"]]


def test_the_cluster_install_check_is_red_when_the_two_are_not_minted() -> None:
    """The planted fault takes the shape the install wrote: `pages_secret_lines` giving no line, so
    the Secret lacks what the chart names, and the install says so in words."""
    from harness.cluster_install import ClusterInstallFailed

    config, values = _chart("govuk", **ON)
    _install(config, values)
    with mock.patch("harness.apply.pages_secret_lines", lambda: ""):
        with pytest.raises(ClusterInstallFailed, match="OSPREY_PAGES_CLIENT_SECRET"):
            _install(config, values)
    _install(config, values)


def test_the_cluster_install_check_is_red_when_the_condition_is_the_wrong_way_round() -> None:
    """With the condition inverted, the setting on makes none (the install fails) and the setting
    off makes both (a Secret holding what no chart names): each shown."""
    from harness import pages_service as service_module
    from harness.cluster_install import ClusterInstallFailed

    on_config, on_values = _chart("govuk", **ON)
    off_config, off_values = _chart("govuk")
    real = service_module.enabled
    with mock.patch.object(service_module, "enabled", lambda config: not real(config)):
        with pytest.raises(ClusterInstallFailed, match="OSPREY_PAGES_"):
            _install(on_config, on_values)
        pairs = _install(off_config, off_values)
    assert [name for name in PAGES_SECRETS if name in pairs] == list(PAGES_SECRETS)


# ---- 7. a GOV.UK function's path goes to `pages` once the tree has it (decision 7) --------------


@contextlib.contextmanager
def a_partial_govuk_tree(root: Path, routes: list[str]) -> Iterator[None]:
    """A tree of two functions with a page for each route in `routes` (the one function that has
    no route yet keeps it partial)."""
    from scripts import tree_parity

    (root / "FUNCTIONS.yaml").write_text(
        "functions:\n"
        "  - id: example\n    route: /studio/example\n    status: planned\n"
        "  - id: pending\n    route: ''\n    status: planned\n",
        encoding="utf-8",
    )
    listed = "".join(f"  - {route}\n" for route in routes)
    (root / "routes.yaml").write_text(f"routes:\n{listed}", encoding="utf-8")
    with (
        mock.patch.object(tree_parity, "FUNCTIONS", root / "FUNCTIONS.yaml"),
        mock.patch.object(tree_parity, "ROUTE_LIST", root / "routes.yaml"),
        mock.patch.object(tree_parity, "EXCEPTIONS", root / "PARITY_EXCEPTIONS.yaml"),
    ):
        assert tree_parity.govuk_tree_state() == tree_parity.PARTIAL
        yield


@pytest.mark.parametrize("shape", ON_SHAPES)
def test_a_govuk_function_with_its_page_is_routed_to_pages_and_the_rest_stays(
    shape: str, tmp_path: Path
) -> None:
    """Partial tree with one route listed, setting on: that path goes to `pages` (the Caddyfile's
    matcher, or the Ingress's path) beside the service's own; the workspace is still there; and
    the same tree with the setting off is the reference."""
    with a_partial_govuk_tree(tmp_path, ["/studio/example"]):
        files = _render(shape, "govuk", **_on(shape))
        routed = pages_paths(shape, files)
        assert routed >= {"/studio/example"} | OWN_PATHS, routed
        assert "/" not in routed and has_a_workspace(shape, files)
        assert on_findings(shape, "govuk", files) == []
        assert ref.differences(shape, "govuk", _render(shape, "govuk")) == []


@pytest.mark.parametrize("shape", ON_SHAPES)
def test_with_no_function_page_yet_only_the_services_own_paths_go_to_pages(shape: str) -> None:
    """The tree as the repository has it today (no route list): `pages`' own paths and nothing else."""
    assert pages_paths(shape, _render(shape, "govuk", **_on(shape))) == OWN_PATHS


@pytest.mark.parametrize("shape", ON_SHAPES)
def test_the_default_brand_reads_no_govuk_route_list(shape: str, tmp_path: Path) -> None:
    """The route list is the GOV.UK tree's: the default theme's table is the Studio's and the
    service's own, whatever that list holds."""
    with a_partial_govuk_tree(tmp_path, ["/studio/example"]):
        routed = pages_paths(shape, _render(shape, "ospreyflow", **_on(shape)))
    assert routed == OWN_PATHS | STUDIO_PATHS


@pytest.mark.parametrize("shape", ON_SHAPES)
def test_the_route_check_is_red_when_the_listed_path_stays_with_the_workspace(
    shape: str, tmp_path: Path
) -> None:
    """The fault named: the table as it was written before it read the tree's list (own paths
    only). The same case, with that table planted, fails naming the path."""
    from harness import pages_service as service

    def own_only(config: Any) -> list[str]:
        return list(service.OWN_PATHS) if service.enabled(config) else []

    with a_partial_govuk_tree(tmp_path, ["/studio/example"]):
        with mock.patch.object(service, "route_paths", own_only):
            routed = pages_paths(shape, _render(shape, "govuk", **_on(shape)))
    assert "/studio/example" not in routed


# ---- 11. Round 9: the page service's real start-up check, and every value the render passes ------
#
# The owner's three instructions of 23 November 2026, for the last round of "sign-in cannot work and
# the render does not say so":
#
# 1. every origin form `config.ts` refuses gets a case, rendered, red first and then green;
# 2. the tests run the service's real check (`_real_start_up_check`: node runs `config.ts` itself),
#    so a value the real check refuses cannot be accepted by a Python stand-in: the stand-in that
#    compared `url.netloc` is gone, and the render's own rule is held to the real one below;
# 3. every value the render passes is checked against every check `config.ts` makes
#    (`VALUES`, and `test_every_variable_the_render_passes_has_a_row`).

ORG_CA = "/etc/ospreyflow/tls/org-root.pem"
#: The words every origin refusal starts with and ends with: the setting, the address, the way out.
THE_ORIGIN_WORDS = re.compile(
    r"^pages\.enabled is on, but network\.public_origin .+ so people could not sign in: .+, "
    r"or leave pages\.enabled off$"
)


def test_the_real_check_accepts_a_clean_environment_and_says_why() -> None:
    """The entry is shown to work both ways before anything is concluded from it (rule 15): a clean
    environment starts, and the one thing wrong in each of these is named by the service itself."""
    wrong = [
        {**CLEAN_ENVIRONMENT, "OSPREY_PAGES_PUBLIC_ORIGIN": "https://osprey.example.org:443"},
        {**CLEAN_ENVIRONMENT, "OSPREY_PAGES_SESSION_SECRET": "short"},
        {**CLEAN_ENVIRONMENT, "OSPREY_PAGES_OIDC_ISSUER": "http://id.osprey.example.org/realms/o"},
    ]
    clean, port, short, http = _real_start_up_check([CLEAN_ENVIRONMENT, *wrong])
    assert clean is None
    assert port is not None and "must be the origin alone" in port
    assert short is not None and "at least 32 characters" in short
    assert http is not None and "must be an https address" in http


#: `OSPREY_PAGES_PUBLIC_ORIGIN` as written, each against what `publicOrigin()` and `addressSetting`
#: really do: (form, the real check refuses it, the words it says). The forms a deployment's
#: `network.public_origin` can come to as the render writes them are the rows of `ORIGIN_FORMS`.
RAW_ORIGINS = [
    ("https://osprey.example.org", False, ""),
    ("https://osprey.example.org:9443", False, ""),
    ("http://localhost:8080", False, ""),
    ("https://[::1]:8443", False, ""),
    ("https://osprey.example.org:443", True, "must be the origin alone"),
    ("http://osprey.example.org:80", True, "must be the origin alone"),
    ("https://osprey.example.org/", True, "must be the origin alone"),
    ("https://osprey.example.org/app", True, "must be the origin alone"),
    ("https://osprey.example.org?x=1", True, "must not carry a query or a fragment"),
    ("https://osprey.example.org#x", True, "must not carry a query or a fragment"),
    ("https://osprey.example.org?", True, "must not carry a query or a fragment"),
    ("https://user:pw@osprey.example.org", True, "must not carry a user name or password"),
    ("https://Osprey.Example.org", True, "must be the origin alone"),
    ("HTTPS://osprey.example.org", True, "must be the origin alone"),
    ("https://::1:8443", True, "must be an address such as"),
    ("https://id.10.1.2.3", True, "must be an address such as"),
    ("https://id.0x7f.1", True, "must be an address such as"),
    ("https://bücher.example", True, "must be the origin alone"),
    ("https://exa%6dple.org", True, "must be the origin alone"),
    ("https://osprey.example.org:99999", True, "must be an address such as"),
    ("https://osprey.example.org:https", True, "must be an address such as"),
    ("https://os prey.example.org", True, "must be an address such as"),
    ("ftp://osprey.example.org", True, "must begin with http:// or https://"),
    ("osprey.example.org", True, "must be an address such as"),
    ("https://", True, "must be an address such as"),
]


@pytest.mark.parametrize(("raw", "refused", "words"), RAW_ORIGINS)
def test_the_real_check_refuses_each_origin_form_it_is_said_to(
    raw: str, refused: bool, words: str
) -> None:
    """The list of what `config.ts` refuses in an origin, run against `config.ts` itself: this is
    the table the render's cases are drawn from, and a row that is wrong fails here, not silently."""
    [verdict] = _real_start_up_check([{**CLEAN_ENVIRONMENT, "OSPREY_PAGES_PUBLIC_ORIGIN": raw}])
    assert (verdict is not None) is refused, verdict
    if refused:
        assert verdict is not None and words in verdict


#: What a `network.public_origin` can be written as, and what the render does with it with the page
#: service on, in a Small with the organisation's own certificate and its CA (so that no trust refusal
#: is the answer): (id, origin, outcome, the origin the service is given, whether the service itself
#: would refuse the value the render passes unguarded).
#:
#: * "rendered": the render writes the origin as the service's own `URL.origin` writes it, and the
#:   real check accepts it (the host is lower-cased, and a path, query, fragment or user name is not
#:   part of an origin, so it is not written: `harness.site.sites`).
#: * "refused": the render refuses, in words, naming `network.public_origin` and the way out: the
#:   service would not start on it (or, where marked, the render is stricter than the service needs).
#: * "elsewhere": refused before the page service by the settings validation or by `sites`, with
#:   the setting off as well (not this slice's, and unchanged).
ORIGIN_FORMS = [
    ("plain", "https://osprey.example.org", "rendered", "https://osprey.example.org", False),
    (
        "port",
        "https://osprey.example.org:9443",
        "rendered",
        "https://osprey.example.org:9443",
        False,
    ),
    ("one-label", "https://osprey", "rendered", "https://osprey", False),
    ("empty-port", "https://osprey.example.org:", "rendered", "https://osprey.example.org", False),
    ("port-zero", "https://osprey.example.org:0", "rendered", "https://osprey.example.org", False),
    (
        "port-zeros",
        "https://osprey.example.org:09443",
        "rendered",
        "https://osprey.example.org:9443",
        False,
    ),
    ("upper-host", "https://OSPREY.Example.ORG", "rendered", "https://osprey.example.org", False),
    (
        "userinfo",
        "https://user:pw@osprey.example.org",
        "rendered",
        "https://osprey.example.org",
        False,
    ),
    ("path", "https://osprey.example.org/app", "rendered", "https://osprey.example.org", False),
    ("query", "https://osprey.example.org?x=1", "rendered", "https://osprey.example.org", False),
    ("fragment", "https://osprey.example.org#x", "rendered", "https://osprey.example.org", False),
    ("default-port", "https://osprey.example.org:443", "refused", None, True),
    ("default-port-zeros", "https://osprey.example.org:0443", "refused", None, True),
    ("default-port-userinfo", "https://user:pw@osprey.example.org:443", "refused", None, True),
    ("ipv4", "https://10.1.2.3", "refused", None, True),
    ("ipv4-port", "https://10.1.2.3:9443", "refused", None, True),
    ("ipv4-decimal", "https://2130706433", "refused", None, True),
    ("ipv4-hex", "https://0x7f.1", "refused", None, True),
    ("ipv6", "https://[::1]:8443", "refused", None, True),
    ("ipv6-plain", "https://[2001:db8::1]", "refused", None, True),
    ("non-ascii", "https://bücher.example", "refused", None, True),
    ("percent", "https://exa%6dple.org", "refused", None, True),
    ("number-last", "https://osprey.example.123", "refused", None, True),
    ("hex-last", "https://osprey.0x1", "refused", None, True),
    ("space", "https://os prey.example.org", "refused", None, True),
    ("backslash", "https://osprey.example.org\\app", "refused", None, True),
    ("punycode", "https://xn--bcher-kva.example", "refused", None, False),
    ("trailing-dot", "https://osprey.example.org.", "refused", None, False),
    ("empty-label", "https://osprey..example.org", "refused", None, False),
    ("underscore", "https://my_host.example.org", "refused", None, False),
    ("trailing-slash", "https://osprey.example.org/", "elsewhere", None, False),
    ("port-too-big", "https://osprey.example.org:65536", "elsewhere", None, False),
    ("port-text", "https://osprey.example.org:https", "elsewhere", None, False),
    ("port-sign", "https://osprey.example.org:-1", "elsewhere", None, False),
    ("upper-scheme", "HTTPS://osprey.example.org", "elsewhere", None, False),
    ("other-scheme", "ftp://osprey.example.org", "elsewhere", None, False),
    ("no-scheme", "osprey.example.org", "elsewhere", None, False),
]
ORIGIN_IDS = [form[0] for form in ORIGIN_FORMS]
REFUSED_FORMS = [form for form in ORIGIN_FORMS if form[2] == "refused"]


def _small_files(brand: str, origin: str, *, pages: bool) -> dict[str, bytes] | ValueError:
    """The small deployment at `origin`, rendered; the refusal itself where it is refused."""
    try:
        return _compose_files(_small(brand, origin, {"ca": ORG_CA}, pages=pages))
    except ValueError as refused:
        return refused


def _cluster_files(origin: str, *, pages: bool) -> dict[str, bytes] | ValueError:
    from harness.render import render

    from schemas.deployment import OspreyConfig

    raw = ref.raw_config("cluster")
    raw["network"]["public_origin"] = origin
    raw["pages"] = {"enabled": pages}
    try:
        artefacts = render(OspreyConfig.model_validate(raw), resolver=ref.resolver).artefacts
    except ValueError as refused:
        return refused
    return {n: t.encode("utf-8") if isinstance(t, str) else t for n, t in artefacts.items()}


def _what_the_render_gave(shape: str, files: dict[str, bytes]) -> tuple[str, str, str | None]:
    """The origin and the issuer the service was given, and what its real check says to the lot."""
    service = pages_service(shape, files)
    assert service is not None
    env = service["env"]
    [verdict] = _real_start_up_check([_resolved(shape, env)])
    return env["OSPREY_PAGES_PUBLIC_ORIGIN"], env["OSPREY_PAGES_OIDC_ISSUER"], verdict


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize(
    ("name", "origin", "outcome", "given", "refused"), ORIGIN_FORMS, ids=ORIGIN_IDS
)
def test_every_origin_form_is_given_to_the_service_as_it_accepts_it_or_refused_in_words(
    name: str, origin: str, outcome: str, given: str | None, refused: bool, brand: str
) -> None:
    """Each form is rendered with the page service on, and what comes out is held to the service's
    real check: either a value it starts with (the origin, and the issuer made from the same host and
    port), or the render's own refusal in words, never a value the service throws on. With the
    setting off the same form is the reference's business and is not refused by this slice."""
    on = _small_files(brand, origin, pages=True)
    off = _small_files(brand, origin, pages=False)
    if outcome == "elsewhere":
        assert isinstance(on, ValueError) and isinstance(off, ValueError), name
        assert not type(on).__name__.startswith("PageService"), on
        return
    assert not isinstance(off, ValueError), f"{name}: off must not be refused: {off}"
    if outcome == "refused":
        assert isinstance(on, ValueError), f"{name}: rendered a value the service refuses"
        assert type(on).__name__ == "PageServiceNeedsAnOrigin", on
        assert THE_ORIGIN_WORDS.match(str(on)), str(on)
        assert "pw" not in str(on), "a credential in the origin must not be printed"
        return
    assert not isinstance(on, ValueError), f"{name}: {on}"
    public, issuer, verdict = _what_the_render_gave("small", on)
    assert verdict is None, f"{name}: the service refuses what the render gave it: {verdict}"
    assert public == given
    identity = given.replace("https://", "https://id.", 1)  # type: ignore[union-attr]
    assert issuer == f"{identity}/realms/osprey"


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize(
    ("name", "origin", "outcome", "given", "refused"),
    REFUSED_FORMS,
    ids=[f[0] for f in REFUSED_FORMS],
)
def test_the_refusal_is_the_only_thing_between_a_form_and_a_service_that_cannot_start(
    name: str, origin: str, outcome: str, given: str | None, refused: bool, brand: str
) -> None:
    """A planted fault at the shape the renderer writes (rule 15): the render's refusal taken out,
    so the form reaches the service's environment as the renderer wrote it before round 9. Where
    the row says the service refuses it, the real check refuses that environment (and so the
    refusal is what keeps a service that cannot start from being rendered); where it does not, the
    refusal is the render being stricter than it need be, and the real check says so."""
    with _patched(
        "harness.pages_service", "refuse_an_origin_the_service_refuses", _no_refusal_at_all
    ):
        files = _small_files(brand, origin, pages=True)
    assert not isinstance(files, ValueError), f"{name}: another refusal stands in the way: {files}"
    _public, _issuer, verdict = _what_the_render_gave("small", files)
    assert (verdict is not None) is refused, f"{name}: {verdict}"


def _no_refusal_at_all(real: Callable[..., Any]) -> Callable[..., Any]:
    def planted(config: Any) -> None:
        return None

    return planted


@pytest.mark.parametrize(
    ("origin", "outcome"),
    [
        ("https://osprey.example.org", "rendered"),
        ("https://osprey.example.org:9443", "rendered"),
        ("https://osprey.example.org:443", "refused"),
        ("https://10.1.2.3", "refused"),
    ],
)
def test_the_cluster_shape_holds_the_same_origin_rule(origin: str, outcome: str) -> None:
    """The rule is in the one function both shapes call: a cluster, its chart's values."""
    on = _cluster_files(origin, pages=True)
    if outcome == "refused":
        assert isinstance(on, ValueError), "rendered a value the service refuses"
        assert type(on).__name__ in ("PageServiceNeedsAnOrigin", "PageServiceNeedsTrust"), on
        return
    assert not isinstance(on, ValueError), on
    public, _issuer, verdict = _what_the_render_gave("cluster", on)
    assert verdict is None, verdict
    assert public == origin


@pytest.mark.parametrize("brand", BRANDS)
def test_a_cluster_at_a_default_port_is_refused_in_words(brand: str) -> None:
    """Not the trust refusal's: a public name, so the origin rule is the one that answers."""
    on = _cluster_files("https://osprey.example.org:443", pages=True)
    assert isinstance(on, ValueError)
    assert type(on).__name__ == "PageServiceNeedsAnOrigin"
    assert "the port :443" in str(on)


# ---- 11a. every value the render passes, against every check config.ts makes -------------------

#: Each variable the render gives the service, and for each the check `config.ts` makes at start-up,
#: planted: (a value the check refuses, the words it says). `None` for a variable `config.ts` makes
#: no check on (the service's own default is used where it is not given, or it is not read there).
VALUES: dict[str, tuple[str, str] | None] = {
    "OSPREY_PAGES_TREE": None,
    "OSPREY_PAGES_PORT": ("70000", "OSPREY_PAGES_PORT must be at most 65535"),
    "OSPREY_PAGES_PUBLIC_ORIGIN": ("https://osprey.example.org:443", "must be the origin alone"),
    "OSPREY_PAGES_CONDUIT_URL": ("http://api:9001/v1", "with no path"),
    "OSPREY_PAGES_SESSION_SECRET": ("short", "at least 32 characters"),
    "OSPREY_PAGES_OIDC_ISSUER": (
        "http://id.osprey.example.org/realms/o",
        "must be an https address",
    ),
    "OSPREY_PAGES_CLIENT_ID": ("osprey pages", "must not hold a space"),
    "OSPREY_PAGES_CLIENT_SECRET": ("short", "at least 32 characters"),
    "VALKEY_HOST": None,
    "VALKEY_PORT": ("x", "VALKEY_PORT must be a whole number"),
    "VALKEY_TLS": None,
    "VALKEY_PASSWORD": None,
    # Node's own, read when the process starts, not by `config.ts`: the CA the organisation signs with.
    "NODE_EXTRA_CA_CERTS": None,
}


@pytest.mark.parametrize("brand", BRANDS)
@pytest.mark.parametrize("shape", ON_SHAPES)
def test_every_variable_the_render_passes_has_a_row(shape: str, brand: str) -> None:
    """A variable the render adds that `VALUES` does not list fails here: it is asked, with the
    value it would need, whether `config.ts` checks it, before it is let through."""
    service = pages_service(shape, _render(shape, brand, **_on(shape)))
    assert service is not None
    assert set(service["env"]) <= set(VALUES), sorted(set(service["env"]) - set(VALUES))


@pytest.mark.parametrize(("variable", "check"), [(k, v) for k, v in VALUES.items() if v])
def test_each_check_config_ts_makes_on_a_value_the_render_passes_is_real(
    variable: str, check: tuple[str, str]
) -> None:
    """The row is a fact about the real check, not a belief about it: the bad value is refused with
    those words, while the render's own value for that variable (`test_on_is_an_environment_*`) is
    not."""
    bad, words = check
    env = {**CLEAN_ENVIRONMENT, "OSPREY_PAGES_CONDUIT_URL": "http://api:9001", variable: bad}
    [verdict] = _real_start_up_check([env])
    assert verdict is not None and words in verdict, verdict


@pytest.mark.parametrize("shape", ON_SHAPES)
def test_every_secret_the_deployment_mints_is_one_the_real_check_accepts(shape: str) -> None:
    """The two minted values, as `apply` (Lite and Small) and the cluster's install make them: each
    long enough, and made to start the service with the rest of the render's own environment."""
    from harness import apply as the_apply

    if shape == "small":
        pairs = dict(
            line.split("=", 1) for line in the_apply.pages_secret_lines().strip().splitlines()
        )
    else:
        config, values = _chart("ospreyflow", **ON)
        pairs = {k: v for k, v in _install(config, values).items() if k in PAGES_SECRETS}
    assert set(pairs) == set(PAGES_SECRETS)
    env = {
        **CLEAN_ENVIRONMENT,
        "OSPREY_PAGES_CLIENT_SECRET": pairs["OSPREY_PAGES_CLIENT_SECRET"],
        "OSPREY_PAGES_SESSION_SECRET": pairs["OSPREY_PAGES_SESSION_SECRET"],
    }
    [verdict] = _real_start_up_check([env])
    assert verdict is None, verdict
