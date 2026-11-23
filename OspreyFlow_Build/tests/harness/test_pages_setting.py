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
        }
    workloads = {w["name"]: w for w in _values(files).get("workloads", [])}
    found = workloads.get("pages")
    if found is None:
        return None
    return {
        "image": found["image"],
        "env": _named(found.get("env")),
        "env_file": bool(found.get("envFrom")),
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
@pytest.mark.parametrize("shape", COMPOSE)
def test_the_two_minted_secrets_are_the_same_off_and_on(shape: str, brand: str) -> None:
    """The conductor's reading of the amendment (the brief of PL7a2b): the two secrets `apply` has
    minted since PL9a stay as the reference pins them, off or on. `deployment.env` is the
    reference's, byte for byte, with the setting on: the setting adds no secret, and takes none
    away."""
    on = _render(shape, brand, **ON)
    stored = ref.read_folder(ref.REFERENCE / ref.folder_name(shape, brand))
    assert on["deployment.env"] == stored["deployment.env"]
    for name in ("OSPREY_PAGES_CLIENT_SECRET", "OSPREY_PAGES_SESSION_SECRET"):
        assert re.search(rf"(?m)^{name}=PINNED_\d+$", on["deployment.env"].decode("utf-8"))


# ---- 3. on adds the service, its route and its variables, and only that -------------------------


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_on_holds_the_service_the_route_and_the_variables(shape: str, brand: str) -> None:
    files = _render(shape, brand, **ON)
    assert on_findings(shape, brand, files) == []


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_on_reaches_the_service_by_its_own_variables_and_by_name(shape: str, brand: str) -> None:
    """The variables are the ones `apps/pages/server/config.ts` reads, with the secrets by
    reference to the env file's two names and no value (a compose file or a chart's values holds no
    secret), and the public origin as the deployment's own."""
    from harness.site import sites

    files = _render(shape, brand, **ON)
    service = pages_service(shape, files)
    assert service is not None
    env = service["env"]
    assert env["OSPREY_PAGES_TREE"] == TREE[brand]
    assert env["OSPREY_PAGES_PORT"] == PAGES_PORT
    assert env["OSPREY_PAGES_PUBLIC_ORIGIN"] == sites(ref.config_for(shape, brand)).glass
    assert env["OSPREY_PAGES_CONDUIT_URL"] == "http://api:8000"
    secret = env["OSPREY_PAGES_SESSION_SECRET"]
    assert "PINNED_" not in secret and "token" not in secret.lower()
    if shape in COMPOSE:
        assert secret.startswith("${OSPREY_PAGES_SESSION_SECRET:?"), secret
        if shape == "local-lite":
            # Plain HTTP: no issuer the service accepts, so none of the three sign-in variables
            # (`test_local_lite_on_plain_http_is_given_no_half_of_a_sign_in`).
            assert "OSPREY_PAGES_CLIENT_SECRET" not in env
        else:
            assert env["OSPREY_PAGES_CLIENT_SECRET"].startswith("${OSPREY_PAGES_CLIENT_SECRET:?")
            assert env["OSPREY_PAGES_OIDC_ISSUER"].endswith("/realms/osprey")
    else:
        assert secret == "secret:OSPREY_PAGES_SESSION_SECRET", secret


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_on_changes_only_the_files_that_name_the_service(shape: str, brand: str) -> None:
    """On adds what decision 7 describes and only that: the files that differ from the reference
    are the ones that carry a service, a route, or the lock of the images; nothing else moves."""
    on = _render(shape, brand, **ON)
    stored = ref.read_folder(ref.REFERENCE / ref.folder_name(shape, brand))
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


@pytest.mark.parametrize("shape", HELM)
def test_on_writes_the_chart_value_and_the_chart_carries_none_by_default(shape: str) -> None:
    """The chart's own defaults say nothing of the page service (a chart installed from them
    renders none, and the reference's view of them is what it was: a `pages:` section added to the
    defaults would be a second one beside the reference's own plant, `test_reference_render.py`'s
    `values off`), and the renderer's values hold `pages.enabled: true` with the setting on."""
    default = yaml.safe_load((ref.CHART / "values.yaml").read_text(encoding="utf-8"))
    assert "pages" not in default
    assert _values(_render(shape, "ospreyflow", **ON))["pages"] == {"enabled": True}
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


@pytest.mark.parametrize(("plant", "shape", "brand"), PLANT_CASES)
def test_the_same_thing_missing_while_on_is_red(plant: Plant, shape: str, brand: str) -> None:
    """On holds the service, the route, the variable and the chart value: with the one the plant
    names taken out, the on checks fail, naming it. Clean first (the on render holds all of it),
    red with the thing out, clean again after."""
    assert on_findings(shape, brand, _render(shape, brand, **ON)) == [], "not clean first"
    with plant.taken_out(shape):
        found = on_findings(shape, brand, _render(shape, brand, **ON))
    assert found, f"{plant.name} in {shape}-{brand}: taking it out was not seen"
    assert any(plant.missing in line for line in found), f"red for another reason: {found}"
    assert on_findings(shape, brand, _render(shape, brand, **ON)) == [], "not clean after"


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


@pytest.mark.parametrize("shape", SHAPES)
def test_the_complete_govuk_tree_with_the_setting_on_renders_without_the_workspace(
    shape: str, tmp_path: Path
) -> None:
    """I22: no workspace service and no route to one; every path goes to `pages`. And the workspace
    is there while the tree is partial (the default of the repository today), setting on."""
    partial = _render(shape, "govuk", **ON)
    assert has_a_workspace(shape, partial), "the workspace is gone while the tree is partial"
    assert "/" not in pages_paths(shape, partial)
    with a_complete_govuk_tree(tmp_path):
        files = _render(shape, "govuk", **ON)
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


def _page_service_refuses(shape: str, files: dict[str, bytes]) -> list[str]:
    """`apps/pages/server/config.ts`'s `loadConfig` refusals that a rendered environment can meet
    (`sessionSecret`, `publicOrigin`, `oidcSettings`, `conduitAddress`), each named as the service
    names it: a render that leaves any of them would be a service that throws at start-up, its
    health check never passing. Empty is an environment the service starts with."""
    from urllib.parse import urlsplit

    service = pages_service(shape, files)
    assert service is not None
    env = _resolved(shape, service["env"])
    refused: list[str] = []

    def address(name: str) -> Any:
        raw = env[name]
        url = urlsplit(raw)
        if url.scheme not in ("http", "https") or not url.hostname:
            refused.append(f"{name} must be an address such as https://host:port")
        elif url.username or url.password or url.query or url.fragment or "?" in raw or "#" in raw:
            refused.append(f"{name} must not carry a user name, password, query or fragment")
        return url

    if len(env.get("OSPREY_PAGES_SESSION_SECRET", "")) < 32:
        refused.append("OSPREY_PAGES_SESSION_SECRET must be at least 32 characters")
    given = [n for n in ("OSPREY_PAGES_OIDC_ISSUER", "OSPREY_PAGES_CLIENT_ID") if n in env]
    if "OSPREY_PAGES_CLIENT_SECRET" in env:
        given.append("OSPREY_PAGES_CLIENT_SECRET")
    if given:
        for name in ("OSPREY_PAGES_OIDC_ISSUER", "OSPREY_PAGES_CLIENT_SECRET"):
            if name not in env:
                refused.append(f"{name} is required: once any sign-in setting is set, all are")
        if "OSPREY_PAGES_OIDC_ISSUER" in env:
            issuer = address("OSPREY_PAGES_OIDC_ISSUER")
            host = issuer.hostname or ""
            loopback = (
                host == "localhost" or host == "::1" or re.fullmatch(r"127(\.\d{1,3}){3}", host)
            )
            if issuer.scheme != "https" and not (issuer.scheme == "http" and loopback):
                refused.append(
                    "OSPREY_PAGES_OIDC_ISSUER must be an https address "
                    "(http only for localhost or another loopback address)"
                )
    for name in ("OSPREY_PAGES_PUBLIC_ORIGIN", "OSPREY_PAGES_CONDUIT_URL"):
        if name in env:
            address(name)
    if "OSPREY_PAGES_PUBLIC_ORIGIN" in env:
        raw = env["OSPREY_PAGES_PUBLIC_ORIGIN"]
        url = urlsplit(raw)
        origin = f"{url.scheme}://{url.netloc}"
        if raw != origin:
            refused.append("OSPREY_PAGES_PUBLIC_ORIGIN must be the origin alone")
    elif given or "OSPREY_PAGES_CONDUIT_URL" in env:
        refused.append("OSPREY_PAGES_PUBLIC_ORIGIN is required")
    return refused


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_on_is_an_environment_the_page_service_starts_with(shape: str, brand: str) -> None:
    """The values, not only the names: with the setting on, what each shape renders for the service
    passes the refusals of its own `loadConfig` (an `http` issuer that is not loopback, an origin
    with a path, a short or missing secret). Local-lite on plain HTTP, the demo's own address form,
    is the shape this caught: its sign-in cannot be given the service, and the service is then
    started with none of the three sign-in variables (it answers 503 on sign-in, as it did before
    it was built) rather than with an issuer it refuses."""
    assert _page_service_refuses(shape, _render(shape, brand, **ON)) == []


def _an_http_issuer(real: Callable[..., Any]) -> Callable[..., Any]:
    """The renderer's old form, as it wrote it: the public identity name over whatever scheme the
    deployment's own origin has, wherever a sign-in is set up."""

    def planted(config: Any, *, with_sign_in: bool) -> dict[str, str]:
        from harness.realm import PAGES_CLIENT_ID, PAGES_CLIENT_SECRET_KEY
        from harness.site import REALM, sites

        environment: dict[str, str] = real(config, with_sign_in=with_sign_in)
        if with_sign_in:
            names = sites(config)
            environment["OSPREY_PAGES_OIDC_ISSUER"] = f"{names.identity}/realms/{REALM}"
            environment["OSPREY_PAGES_CLIENT_ID"] = PAGES_CLIENT_ID
            environment["OSPREY_PAGES_CLIENT_SECRET"] = "${%s:?set}" % PAGES_CLIENT_SECRET_KEY
        return environment

    return planted


@pytest.mark.parametrize("brand", BRANDS)
def test_the_start_up_check_is_red_for_an_http_issuer_that_is_not_loopback(brand: str) -> None:
    """The planted fault takes the shape the renderer wrote: `http://id.<host>/realms/osprey` in
    local-lite. The check is clean first, red with it (naming the issuer and the rule), clean again."""
    assert _page_service_refuses("local-lite", _render("local-lite", brand, **ON)) == []
    with _patched("harness.pages_service", "service_environment", _an_http_issuer):
        found = _page_service_refuses("local-lite", _render("local-lite", brand, **ON))
    assert any("OSPREY_PAGES_OIDC_ISSUER must be an https address" in line for line in found), found
    assert _page_service_refuses("local-lite", _render("local-lite", brand, **ON)) == []


@pytest.mark.parametrize("shape", ("small", "cluster"))
def test_an_https_deployment_is_given_its_sign_in(shape: str) -> None:
    """Where the issuer is an https address the service accepts, the three sign-in variables are
    written (compose only: the cluster's chart carries the realm's own, PL9b)."""
    env = (pages_service(shape, _render(shape, "govuk", **ON)) or {})["env"]
    if shape == "small":
        assert env["OSPREY_PAGES_OIDC_ISSUER"].startswith("https://")
        assert "OSPREY_PAGES_CLIENT_ID" in env and "OSPREY_PAGES_CLIENT_SECRET" in env


def test_local_lite_on_plain_http_is_given_no_half_of_a_sign_in() -> None:
    """All three sign-in variables or none (the service refuses a part): on plain HTTP, none."""
    env = (pages_service("local-lite", _render("local-lite", "govuk", **ON)) or {})["env"]
    assert not [
        name for name in env if name.startswith(("OSPREY_PAGES_OIDC", "OSPREY_PAGES_CLIENT"))
    ]


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


@pytest.mark.parametrize("shape", SHAPES)
def test_a_govuk_function_with_its_page_is_routed_to_pages_and_the_rest_stays(
    shape: str, tmp_path: Path
) -> None:
    """Partial tree with one route listed, setting on: that path goes to `pages` (the Caddyfile's
    matcher, or the Ingress's path) beside the service's own; the workspace is still there; and
    the same tree with the setting off is the reference."""
    with a_partial_govuk_tree(tmp_path, ["/studio/example"]):
        files = _render(shape, "govuk", **ON)
        routed = pages_paths(shape, files)
        assert routed >= {"/studio/example"} | OWN_PATHS, routed
        assert "/" not in routed and has_a_workspace(shape, files)
        assert on_findings(shape, "govuk", files) == []
        assert ref.differences(shape, "govuk", _render(shape, "govuk")) == []


@pytest.mark.parametrize("shape", SHAPES)
def test_with_no_function_page_yet_only_the_services_own_paths_go_to_pages(shape: str) -> None:
    """The tree as the repository has it today (no route list): `pages`' own paths and nothing else."""
    assert pages_paths(shape, _render(shape, "govuk", **ON)) == OWN_PATHS


@pytest.mark.parametrize("shape", SHAPES)
def test_the_default_brand_reads_no_govuk_route_list(shape: str, tmp_path: Path) -> None:
    """The route list is the GOV.UK tree's: the default theme's table is the Studio's and the
    service's own, whatever that list holds."""
    with a_partial_govuk_tree(tmp_path, ["/studio/example"]):
        routed = pages_paths(shape, _render(shape, "ospreyflow", **ON))
    assert routed == OWN_PATHS | STUDIO_PATHS


@pytest.mark.parametrize("shape", SHAPES)
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
            routed = pages_paths(shape, _render(shape, "govuk", **ON))
    assert "/studio/example" not in routed
