"""A reference render of the deployment shapes: "a deployment is unchanged while the page service is
off" as a test (build id PL7, slice PL7a2a; ADR-152 Amendment 1, decisions 1 and 2; the owner's
ruling of 21 November 2026: the page service in a deployment is a setting, off by default, turned on
per deployment by the owner; no deployment changes until then; the GOV.UK demo is not touched).

**What this pins.** Each shape is rendered the way the product renders it today and compared, byte
for byte, with the copy stored under `tests/fixtures/reference_render/<shape>-<brand>/` and the
`MANIFEST.json` beside it (path, SHA-256, size). The shapes: `local-lite`, `small` (compose, with
the Caddyfile, `deployment.env`, `glass.json`, the realm import, the gateway's routing table and the
sign-in theme), `cluster` (the chart's `values.yaml` and `versions.lock`), `cloud-platform` and
`cloud-platform-poc` (its values, the image plan, the Ingress inside the values, the namespace's
Terraform and, for the poc, its install and decommission guides). Each under both brands the
renderers read, `appearance.brand` `ospreyflow` (the default) and `govuk`.

**The GOV.UK demo's shape.** The demo is the owner's named Lite deployment `govuk` on his Mac
(plain HTTP on a `.localhost` name and a port, the GOV.UK brand), so `local-lite-govuk` stands for
it; `small-govuk` is pinned beside it because a deployment on a server of one's own is the same code
with HTTPS. Nothing here reads, starts or changes that deployment: it is a render in memory from
synthetic settings.

**The chart is pinned by its sources, as they render with the page service off.** `helm template`
output is not stored: it needs the `helm` binary, which a pure test does not assume (`make
chart-check` and `make cp-policy-check` template the chart). So each Helm shape (`cluster`,
`cloud-platform`, `cloud-platform-poc`) stores, beside its values, the chart's own files under
`chart/` (`Chart.yaml`, the chart's default `values.yaml`, `.helmignore` and every template), byte
for byte and in the manifest with their SHA-256: what `helm template` renders from, so a template
that changes (a workload, an Ingress path, a NetworkPolicy) is a changed file, named. **Stored as
the chart is with `pages.enabled` off** (`tools.reference_render.chart_off_view`, which reads one
guard and is not a Helm renderer): a block of a template opened by `{{- if .Values.pages.enabled }}`
on a line of its own and closed by `{{- end }}` on one of its own, with no `else`, is not in the
stored file; a template that is nothing but such a block is not a file; a top-level `pages:` section
of the chart's default `values.yaml` that says `enabled: false` is not there. So the chart PL7a2b
changes to add the page service, behind that guard, is the reference unchanged; the same block
unguarded, guarded by anything else (`if .Values.pages` is true of a mapping that says `enabled:
false`), under an `else`, or switched on by default, is red (each case is below). That is the
guard's name from the owner's ruling of 21 November 2026 (answer 6: `pages.enabled`); if PL7a2b
names it otherwise, the guard it uses is a deliberate change to `chart_off_view`, in a diff he
reads. **What this cannot see** without `helm`: a template that renders a page service while off
by a guard it does not read (a `lookup`, an `include` of a helper), or a workload the renderer
writes into the values (that one is in the stored values, and is red).

**The compose shapes' `deployment.env` is the one `apply` writes.** The shapes `local-lite` and
`small` are rendered through `harness.apply.stage_deployment`, run into a temporary folder with its
render step given this module's resolver, so the file holds every line `apply` appends to the
rendered one: the identity provider's addresses, the stores' hosts and the page service's two
secrets (`OSPREY_PAGES_CLIENT_SECRET`, `OSPREY_PAGES_SESSION_SECRET`), each minted value
`PINNED_<n>` (numbered by the order the render mints them; not one word, because
`harness.cloud_platform` mints twice and compares to tell a fixed value from a fresh one). An
enable flag added beside them, or the two secrets made conditional, is a changed
`deployment.env`. `osprey.yaml` (the input, copied) and `.rendered` (the list of what was written)
are not rendered content and are not stored. There is no `deployment.json` among the files: the
renderers write `glass.json` (ADR-114 Amendment 4), which is stored; `/deployment.json` is what
the Glass is served from it.

**No network, no docker, no real secret, no clock; nothing from the shell.** The renders take their
digests from a hash of the image reference (`tools.reference_render.resolver`: the registry is never
asked) and have the commit, the version, the design tokens, the minted secrets and the shell's
`OSPREY_IMAGE_REGISTRY` and `OSPREY_BUILT_FROM_SHA` pinned (`pinned_inputs`: they are read from the
checkout or the shell, and would otherwise move with every commit or every terminal). A render reads
no clock; `apply` is given an empty environment, so no provider key or mail password of the shell
reaches a file. The last cases below scan every stored file for a credential-shaped string, an
address, a real host and a cloud account other than the synthetic one, and are shown red on each.

**The page-service setting.** Today there is none: `OspreyConfig` has no `pages` section, and no
renderer reads one. The case `test_the_render_with_no_page_service_setting_equals_the_reference`
renders with no `pages` setting passed and requires the reference. PL7a2b adds the setting, off by
default; that case then holds it to "off, or not set, renders what it rendered", and stays green or
the slice is wrong. It checks `model_fields_set`, so it still means "not set" once the field exists.

**Planted faults, at the shape the renderer really emits (rule 15).** Each is a patched function
called in place of the real one (the real renderer files are never edited): a `pages:` service in
the compose services; a `handle /studio` block in the Caddyfile; a changed Helm value (on both Helm
shapes); a file dropped from a shape (on a compose shape and on the Terraform one); one byte changed
in a stored fixture (a copy of it); and, in a temporary copy of the chart
(`tools.reference_render.CHART`
pointed at it), a `pages` workload added to `templates/workloads.yaml`, a `/studio` path added to
the Ingress in `templates/ingress.yaml`, and a template file dropped. Each is shown clean first (so
the red is the plant's), red with
a message naming the shape, the file and the first differing line, and clean again after.

**Regenerate the reference** (a deliberate change; the diff of `tests/fixtures/reference_render/`
is what the owner reads):

    cd OspreyFlow_Core && PYTHONPATH=../OspreyFlow_Build:packages \\
        uv run python -m tools.reference_render --write

(`--check` lists what differs and exits 1.) Writing twice yields the same bytes
(`test_writing_the_reference_twice_gives_the_same_bytes`).

**What this test reads.** The folder `OspreyFlow_Build/tests/fixtures/reference_render/` (each
shape's folder, by a recursion over those folders only), the cloud-platform fixtures
`OspreyFlow_Build/tests/fixtures/cloud_platform/{development,poc}.yaml` (and the platform settings
they name, through the renderer), the chart `OspreyFlow_Core/deploy/helm/ospreyflow/` (one
recursion over that folder, its files only, for the Helm shapes), the design tokens
`OspreyFlow_Core/packages/design/tokens.css` (read once, to plant a change to them in a temporary
copy, and to show no fixture holds them), and, by importing the renderers,
`OspreyFlow_Core/harness/` and `OspreyFlow_Core/packages/schemas/`. It writes only to temporary
folders (the staging folder `stage_deployment` fills, and the copies of the chart and of the
reference a plant edits). It walks no other folder.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from tools import reference_render as ref

REFERENCE = ref.REFERENCE
SHAPE_BRANDS = ref.all_folders()
IDS = [ref.folder_name(shape, brand) for shape, brand in SHAPE_BRANDS]
#: The compose shapes (a compose file and a Caddyfile).
COMPOSE = ("local-lite", "small")
#: The shapes installed from the chart, and the chart files that matter most to "unchanged when
#: off".
HELM = ("cluster", "cloud-platform", "cloud-platform-poc")
CHART_PINS = {
    "chart/Chart.yaml",
    "chart/values.yaml",
    "chart/templates/workloads.yaml",
    "chart/templates/ingress.yaml",
    "chart/templates/networkpolicies.yaml",
    "chart/templates/services.yaml",
}


@pytest.fixture(scope="module")
def rendered() -> dict[tuple[str, str], dict[str, bytes]]:
    """Every shape under every brand, rendered once with no page-service setting."""
    return {(shape, brand): ref.render_shape(shape, brand) for shape, brand in SHAPE_BRANDS}


# ---- the reference holds, byte for byte -------------------------------------------------------


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_each_shape_renders_exactly_the_reference_file_by_file(
    shape: str, brand: str, rendered: dict[tuple[str, str], dict[str, bytes]]
) -> None:
    """Exact bytes, file by file. A failure names the shape, the file and the first differing line
    (and a file added, dropped or whose manifest entry is stale)."""
    found = ref.differences(shape, brand, rendered[(shape, brand)])
    assert not found, "the render is not the reference:\n" + "\n".join(found)


def test_every_shape_and_brand_has_a_stored_folder_and_nothing_else_is_stored() -> None:
    """No shape without a reference, and no folder of a shape that is no longer pinned (a stale
    folder would be read as a pin that is not kept)."""
    assert ref.stored_folders() == sorted(IDS)
    # The shapes the brief names, each under both brands, the GOV.UK demo's among them.
    assert set(ref.SHAPES) >= {"local-lite", "small", "cluster", "cloud-platform"}
    assert {"local-lite-govuk", "small-govuk"} <= set(IDS)


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_the_set_of_files_each_shape_writes_is_the_set_in_the_manifest(
    shape: str, brand: str, rendered: dict[tuple[str, str], dict[str, bytes]]
) -> None:
    """No file added and none dropped, and the manifest is true of the files beside it: the paths
    the manifest lists are the paths the shape renders and the paths stored, and each entry's
    SHA-256 and size are those of the stored bytes (so a changed byte shows as a changed hash)."""
    chart_now = ref.chart_files()
    folder = REFERENCE / ref.folder_name(shape, brand)
    listed = json.loads((folder / ref.MANIFEST).read_text(encoding="utf-8"))["files"]
    paths = [entry["path"] for entry in listed]
    assert paths == sorted(paths), "the manifest is not sorted by path"
    assert len(paths) == len(set(paths))
    now = rendered[(shape, brand)]
    stored = ref.read_folder(folder)
    assert set(paths) == set(now), (
        f"{folder.name}: the shape writes {sorted(set(now) - set(paths))} that the manifest "
        f"does not list, and the manifest lists {sorted(set(paths) - set(now))} that it no "
        "longer writes"
    )
    assert set(paths) == set(stored), f"{folder.name}: the files stored are not the manifest's"
    for entry in listed:
        data = stored[entry["path"]]
        assert entry["sha256"] == hashlib.sha256(data).hexdigest(), (
            f"{folder.name}/{entry['path']}: the manifest's hash is not the stored file's"
        )
        assert entry["size"] == len(data)
    # Not a stub: every shape writes its named artefacts.
    expected = {
        "local-lite": {"compose.yaml", "Caddyfile", "deployment.env", "glass.json", "realm.json"},
        "small": {"compose.yaml", "Caddyfile", "deployment.env", "glass.json", "realm.json"},
        "cluster": {"values.yaml", "versions.lock"} | CHART_PINS,
        "cloud-platform": {"values.yaml", "versions.lock", "images.yaml", "terraform/rds.tf"}
        | CHART_PINS,
        "cloud-platform-poc": {"values.yaml", "images.yaml", "terraform/rds.tf", "INSTALL.md"}
        | CHART_PINS,
    }[shape]
    assert expected <= set(paths), f"{folder.name} lacks {sorted(expected - set(paths))}"
    # The chart is pinned for the Helm shapes and only for them, every file of it.
    pinned = {path for path in paths if path.startswith(ref.CHART_PREFIX)}
    assert pinned == (set(chart_now) if shape in HELM else set()), f"{folder.name}: chart pins"
    assert len(chart_now) >= 12, "the chart has its templates and its files"


# ---- the invariant PL7a2b has to keep ---------------------------------------------------------


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
def test_the_render_with_no_page_service_setting_equals_the_reference(
    shape: str, brand: str
) -> None:
    """The invariant itself: with the page-service setting absent, a deployment renders what it
    rendered before the setting existed. Today there is no such setting; this renders without
    passing any `pages` setting, as a deployment that never heard of it. PL7a2b adds the setting,
    off by default, and keeps this case green."""
    config = ref.config_for(shape, brand)
    assert "pages" not in config.model_fields_set, "this case renders with no pages setting"
    assert "pages" not in ref.raw_config(shape)
    found = ref.differences(shape, brand, ref.render_files(config))
    assert not found, "a deployment with no page-service setting changed:\n" + "\n".join(found)


# ---- planted faults, each clean, then red for its own reason, then clean --------------------


def _plant_red_then_green(
    shape: str,
    brand: str,
    plant: Callable[[], Any],
    *,
    names: str,
    first_line_has: str | None = None,
    render_fn: Callable[..., Any] | None = None,
) -> str:
    """Clean first; then the render with the plant applied must differ from the reference in the
    file `names`, with `first_line_has` in the message when it is given; then clean again with the
    plant gone. Returns the red message."""
    assert ref.differences(shape, brand, ref.render_shape(shape, brand)) == [], "not clean first"
    with plant():
        planted = ref.render_files(ref.config_for(shape, brand), render_fn=render_fn)
        found = ref.differences(shape, brand, planted)
    message = "\n".join(found)
    assert found, f"{shape}-{brand}: the planted fault was not seen"
    assert ref.folder_name(shape, brand) in message, message
    assert names in message, f"the red message does not name {names}:\n{message}"
    if first_line_has is not None:
        assert first_line_has in message, f"red for another reason:\n{message}"
    assert ref.differences(shape, brand, ref.render_shape(shape, brand)) == [], "not clean after"
    return message


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", COMPOSE)
def test_a_new_service_block_in_the_compose_output_is_red(shape: str, brand: str) -> None:
    """(a) A `pages:` service added to the compose services, where `compose_services` returns them
    (the shape `_render_compose` dumps): the compose file differs, at the new block."""
    import harness.render as render_module

    real = render_module.compose_services

    def with_pages(config: Any, images: Any) -> dict[str, Any]:
        services = real(config, images)
        services["pages"] = {
            "image": "ghcr.io/ospreyflow/pages:pinned",
            "restart": "unless-stopped",
            "networks": ["osprey"],
            "environment": {"PORT": "3000"},
        }
        return services

    message = _plant_red_then_green(
        shape,
        brand,
        lambda: mock.patch.object(render_module, "compose_services", with_pages),
        names="compose.yaml",
        first_line_has="pages",
    )
    assert "first differing line" in message


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", COMPOSE)
def test_a_new_handle_block_in_the_caddyfile_is_red(shape: str, brand: str) -> None:
    """(b) A `handle /studio` block in the front proxy's site block for the workspace, as Caddy
    would be told to route a path to a new service: written into `render_caddyfile`'s own output,
    in the place it writes the workspace's `reverse_proxy`."""
    import harness.render as render_module

    real = render_module.render_caddyfile

    def with_studio(config: Any, **kwargs: Any) -> str:
        text = real(config, **kwargs)
        upstream = "\treverse_proxy workspace:8080\n"
        assert upstream in text, "the real Caddyfile has no workspace route to plant beside"
        return text.replace(
            upstream,
            "\thandle /studio* {\n\t\treverse_proxy pages:3000\n\t}\n"
            "\thandle {\n\t\treverse_proxy workspace:8080\n\t}\n",
            1,
        )

    _plant_red_then_green(
        shape,
        brand,
        lambda: mock.patch.object(render_module, "render_caddyfile", with_studio),
        names="Caddyfile",
        first_line_has="handle /studio",
    )


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize(
    ("shape", "module", "function"),
    [
        ("cluster", "harness.cluster", "render_cluster"),
        ("cloud-platform", "harness.cloud_platform", "render_cloud_platform"),
    ],
)
def test_a_changed_helm_value_is_red(shape: str, module: str, function: str, brand: str) -> None:
    """(c) One value in the chart's `values.yaml` changed (the first `replicas:` line, one more),
    written into the renderer's own text, not a re-dump of it: only that line differs."""
    target = importlib.import_module(module)
    real = getattr(target, function)

    def with_one_more_replica(*args: Any, **kwargs: Any) -> dict[str, str]:
        artefacts = dict(real(*args, **kwargs))
        lines = artefacts["values.yaml"].splitlines(keepends=True)
        index = next(i for i, line in enumerate(lines) if line.startswith("  replicas: "))
        lines[index] = f"  replicas: {int(lines[index].split(':')[1]) + 1}\n"
        artefacts["values.yaml"] = "".join(lines)
        return artefacts

    message = _plant_red_then_green(
        shape,
        brand,
        lambda: mock.patch.object(target, function, with_one_more_replica),
        names="values.yaml",
        first_line_has="replicas",
    )
    assert message.count("first differing line") == 1, "only the one value changed"


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize(
    ("shape", "dropped"),
    [("local-lite", "Caddyfile"), ("small", "glass.json"), ("cloud-platform", "terraform/rds.tf")],
)
def test_a_file_dropped_from_a_shape_is_red(shape: str, dropped: str, brand: str) -> None:
    """(d) A file the shape writes today, no longer rendered: named, as no longer rendered, and the
    manifest's set is the one that disagrees."""
    from harness.render import render

    def without(config: Any, **kwargs: Any) -> Any:
        result = render(config, **kwargs)
        artefacts = {k: v for k, v in result.artefacts.items() if k != dropped}
        assert artefacts != result.artefacts, f"{dropped} is not a file of {shape}"
        return type(result)(profile=result.profile, artefacts=artefacts)

    _plant_red_then_green(
        shape,
        brand,
        contextlib.nullcontext,
        names=f"{dropped}: in the reference, and no longer rendered",
        render_fn=without,
    )


def _chart_copy(tmp_path: Path) -> Path:
    """A temporary copy of the real chart, which `ref.CHART` is pointed at; the real chart is never
    edited."""
    copy = tmp_path / "chart"
    shutil.copytree(ref.CHART, copy)
    return copy


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", HELM)
@pytest.mark.parametrize(
    ("template", "plant", "line"),
    [
        (
            "workloads.yaml",
            # A document in the shape the template writes its workloads: a Deployment of the pages
            # service, unguarded by any value.
            "---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: pages\nspec:\n"
            "  replicas: 1\n",
            "the rendered text goes on",  # the file is longer: the reference ends where it did
        ),
        (
            "ingress.yaml",
            # A path in the Ingress's own `paths` loop, before it closes: `/studio` to `pages`.
            "          - path: /studio\n            pathType: Prefix\n            backend:\n"
            "              service:\n                name: pages\n",
            "path: /studio",
        ),
    ],
    ids=["a pages workload", "a studio ingress path"],
)
def test_a_changed_helm_template_is_red(
    shape: str, brand: str, template: str, plant: str, line: str, tmp_path: Path
) -> None:
    """(f) The chart's own templates are pinned: a workload or an Ingress path added to a template,
    in the shape the template writes, is a changed file under `chart/templates/` for every Helm
    shape, naming the file and the first differing line, with the real chart untouched."""
    copy = _chart_copy(tmp_path)
    target = copy / "templates" / template
    text = target.read_text(encoding="utf-8")
    if template == "ingress.yaml":
        anchor = "          {{- end }}\n    {{- end }}\n"
        assert anchor in text, "the Ingress template has no paths loop to plant in"
        text = text.replace(anchor, plant + anchor, 1)
    else:
        text += plant
    target.write_text(text, encoding="utf-8")
    assert ref.differences(shape, brand, ref.render_shape(shape, brand)) == [], "not clean first"
    with mock.patch.object(ref, "CHART", copy):
        found = ref.differences(shape, brand, ref.render_shape(shape, brand))
    message = "\n".join(found)
    name = ref.folder_name(shape, brand)
    assert f"{name}/chart/templates/{template}: first differing line is" in message, message
    assert line in message, f"red for another reason:\n{message}"
    assert len(found) == 1, message  # only that file; the values and the manifest are as before
    assert ref.differences(shape, brand, ref.render_shape(shape, brand)) == [], "not clean after"


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", HELM)
def test_a_chart_file_dropped_or_added_is_red(shape: str, brand: str, tmp_path: Path) -> None:
    """(f) A template dropped from the chart, and one added, are each named as no longer rendered or
    as rendered and not in the reference."""
    name = ref.folder_name(shape, brand)
    copy = _chart_copy(tmp_path)
    (copy / "templates" / "networkpolicies.yaml").unlink()
    with mock.patch.object(ref, "CHART", copy):
        dropped = ref.differences(shape, brand, ref.render_shape(shape, brand))
    assert (
        f"{name}/chart/templates/networkpolicies.yaml: in the reference, and no longer rendered"
        in (dropped)
    ), dropped
    copy = _chart_copy(tmp_path / "again")
    (copy / "templates" / "pages.yaml").write_text("kind: Deployment\n", encoding="utf-8")
    with mock.patch.object(ref, "CHART", copy):
        added = ref.differences(shape, brand, ref.render_shape(shape, brand))
    assert f"{name}/chart/templates/pages.yaml: rendered, and not in the reference" in added, added


@pytest.mark.parametrize("shape", COMPOSE)
def test_a_compose_shape_is_not_pinned_to_the_chart(shape: str, tmp_path: Path) -> None:
    """A change to the chart is not a change to a compose deployment: the compose shapes render the
    reference with the chart changed."""
    copy = _chart_copy(tmp_path)
    (copy / "templates" / "workloads.yaml").write_text("changed\n", encoding="utf-8")
    with mock.patch.object(ref, "CHART", copy):
        assert ref.differences(shape, "govuk", ref.render_shape(shape, "govuk")) == []


@pytest.mark.parametrize("brand", ref.BRANDS)
def test_one_changed_byte_in_a_fixture_is_red(brand: str, tmp_path: Path) -> None:
    """(e) One byte of a stored file changed (in a copy of the folder, never the real one): the
    render no longer equals it, naming the file and the line, and the manifest no longer describes
    the files beside it, so the changed byte is a changed hash."""
    name = ref.folder_name("small", brand)
    copy = tmp_path / "reference"
    shutil.copytree(REFERENCE, copy)
    assert ref.differences("small", brand, ref.render_shape("small", brand), copy) == []

    target = copy / name / "compose.yaml"
    before = target.read_bytes()
    data = bytearray(before)
    position = data.index(b"restart: ") + len(b"restart: ")
    data[position] = ord("X")  # one byte
    target.write_bytes(bytes(data))
    assert len(target.read_bytes()) == len(before)

    found = "\n".join(ref.differences("small", brand, ref.render_shape("small", brand), copy))
    assert f"{name}/compose.yaml: first differing line is" in found, found
    assert f"{name}/{ref.MANIFEST}: does not describe the files stored beside it" in found, found
    listed = json.loads((copy / name / ref.MANIFEST).read_text(encoding="utf-8"))["files"]
    entry = next(e for e in listed if e["path"] == "compose.yaml")
    assert entry["sha256"] != hashlib.sha256(target.read_bytes()).hexdigest()


def test_a_change_that_only_removes_the_last_newline_is_red(tmp_path: Path) -> None:
    """Exact bytes, not the text a person reads: a file whose lines are the same but whose last
    newline is gone is not the reference."""
    copy = tmp_path / "reference"
    shutil.copytree(REFERENCE, copy)
    target = copy / "local-lite-ospreyflow" / "Caddyfile"
    original = target.read_bytes()
    assert original.endswith(b"\n")
    target.write_bytes(original[:-1])
    rendered_now = ref.render_shape("local-lite", "ospreyflow")
    found = "\n".join(ref.differences("local-lite", "ospreyflow", rendered_now, copy))
    assert "local-lite-ospreyflow/Caddyfile:" in found, found


# ---- every input that is not configuration is pinned -----------------------------------------

#: Read by the renderers from the process environment (`harness.render._owned` names every owned
#: image from the first; `git_sha` falls back to the second): the shell a test or `--write` runs in
#: must not reach the stored bytes.
SHELL_INPUTS = ("OSPREY_IMAGE_REGISTRY", "OSPREY_BUILT_FROM_SHA")


def test_the_real_renderer_does_read_the_image_registry_from_the_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not vacuous: with the commit fixed and nothing else touched, the same configuration renders
    different compose bytes under a different `OSPREY_IMAGE_REGISTRY`. So the pin below is doing
    something, and a render that is not pinned would carry the shell into the reference."""
    from harness.render import render

    config = ref.config_for("small", "ospreyflow")

    def compose() -> str:
        with mock.patch("harness.render.git_sha", lambda *_a, **_k: ref.PINNED_SHA):
            return render(config, resolver=ref.resolver).artefacts["compose.yaml"]

    monkeypatch.delenv("OSPREY_IMAGE_REGISTRY", raising=False)
    without = compose()
    monkeypatch.setenv("OSPREY_IMAGE_REGISTRY", "registry.other.example/elsewhere")
    assert compose() != without


@pytest.mark.parametrize(("shape", "brand"), SHAPE_BRANDS, ids=IDS)
@pytest.mark.parametrize("variable", SHELL_INPUTS)
def test_a_variable_in_the_shell_moves_no_fixture(
    variable: str, shape: str, brand: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every shape renders the reference with the variable set to something else, and the variable
    is as it was after the render (the pin is for the length of the render)."""
    monkeypatch.setenv(variable, "registry.other.example/elsewhere")
    found = ref.differences(shape, brand, ref.render_shape(shape, brand))
    assert not found, f"{variable} in the shell moved the reference:\n" + "\n".join(found)
    assert os.environ[variable] == "registry.other.example/elsewhere"


@contextlib.contextmanager
def _pins_with(extra: Callable[[], Any]) -> Any:
    """The real pins, then `extra` on top of them (a plant that undoes one): `ref.pinned_inputs`
    replaced for the length of the block."""
    real = ref.pinned_inputs

    @contextlib.contextmanager
    def undone() -> Any:
        with real(), extra():
            yield

    with mock.patch.object(ref, "pinned_inputs", undone):
        yield


@pytest.mark.parametrize(
    ("shape", "brand"), [("small", "ospreyflow"), ("cluster", "govuk"), ("cloud-platform", "govuk")]
)
def test_the_registry_pin_is_what_keeps_the_shell_out(shape: str, brand: str) -> None:
    """Shown red (rule 15): the same render with the variable put back after the pin is not the
    reference, naming the image line; and clean again with the pin as it is."""
    assert ref.differences(shape, brand, ref.render_shape(shape, brand)) == []
    with _pins_with(lambda: mock.patch.dict(os.environ, {"OSPREY_IMAGE_REGISTRY": "r.example/x"})):
        found = ref.differences(shape, brand, ref.render_shape(shape, brand))
    message = "\n".join(found)
    assert "/x" in message, message  # the registry as each shape writes it
    assert ref.differences(shape, brand, ref.render_shape(shape, brand)) == []


@pytest.mark.parametrize("shape", COMPOSE)
def test_the_secret_pin_is_what_keeps_a_minted_value_out(shape: str) -> None:
    """Shown red (rule 15): with the generator put back after the pin, `deployment.env` is not the
    reference, naming a secret's line (the case above is the same without the plant)."""
    import secrets

    with _pins_with(lambda: mock.patch.object(secrets, "token_urlsafe", lambda *_a: "x" * 43)):
        found = ref.differences(shape, "govuk", ref.render_shape(shape, "govuk"))
    message = "\n".join(found)
    assert f"{shape}-govuk/deployment.env: first differing line" in message, message
    assert "_SECRET=" in message or "_PASSWORD=" in message, message


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", COMPOSE)
def test_a_minted_secret_is_pinned(shape: str, brand: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """`apply` mints each secret with `secrets.token_urlsafe` (the realm's and the reporting
    module's call it too); a generator that returns something new each time moves no fixture."""
    import secrets

    counter = iter(range(1_000_000))
    monkeypatch.setattr(secrets, "token_urlsafe", lambda *_a, **_k: f"fresh-{next(counter)}")
    found = ref.differences(shape, brand, ref.render_shape(shape, brand))
    assert not found, "\n".join(found)


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", COMPOSE)
def test_the_stored_deployment_env_is_the_one_apply_writes(shape: str, brand: str) -> None:
    """The compose shapes' `deployment.env` is what `harness.apply.stage_deployment` leaves in the
    folder, not only what the render writes: the lines `apply` adds are pinned, among them the page
    service's two secrets (which every deployment holds today), with a synthetic value."""
    from harness.apply import PAGES_CLIENT_SECRET_KEY, PAGES_SESSION_SECRET_KEY

    env = ref.read_folder(REFERENCE / ref.folder_name(shape, brand))["deployment.env"].decode()
    for name in (PAGES_CLIENT_SECRET_KEY, PAGES_SESSION_SECRET_KEY, "OSPREY_OIDC_CLIENT_SECRET"):
        assert re.search(rf"(?m)^{name}=PINNED_\d+$", env), (
            f"{shape}-{brand} deployment.env: {name}"
        )
    for line in (
        "OIDC_JWKS_URL=http://keycloak:8080/realms/osprey/protocol/openid-connect/certs\n",
        "ARCADEDB_HOST=arcadedb\n",
        "VALKEY_HOST=valkey\n",
    ):
        assert line in env, f"{shape}-{brand} deployment.env lacks {line!r}"
    # Two names for one password hold one value, as `apply` writes them.
    shared = re.search(r"(?m)^OSPREY_ARCADEDB_PASSWORD=(PINNED_\d+)$", env)
    assert shared is not None and env.count(shared[1] + "\n") == 2


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", COMPOSE)
@pytest.mark.parametrize(
    ("replacement", "line_has"),
    [
        # A page-service secret made conditional (gone while the service is off).
        (lambda real: "", "OSPREY_PAGES_CLIENT_SECRET"),
        # A new line, as an enable flag would be, beside the secrets.
        (lambda real: real() + "PAGES_ENABLED=false\n", "PAGES_ENABLED"),
    ],
    ids=["the page secrets made conditional", "an enable flag added"],
)
def test_a_changed_page_service_line_in_the_deployment_env_is_red(
    shape: str, brand: str, replacement: Callable[[Any], str], line_has: str
) -> None:
    """The lines `apply` appends to `deployment.env` are pinned: a change to the page service's own,
    made in the function that writes them, is a changed `deployment.env`, naming the line."""
    import harness.apply as apply_module

    real = apply_module.pages_secret_lines
    message = _plant_red_then_green(
        shape,
        brand,
        lambda: mock.patch.object(apply_module, "pages_secret_lines", lambda: replacement(real)),
        names="deployment.env",
        first_line_has=line_has,
    )
    assert message.count("first differing line") == 1, message


# ---- "unchanged when off" in the chart: a block guarded by `pages.enabled` is not rendered ----

GUARD = "{{- if .Values.pages.enabled }}\n"
#: The guard with no dash before `if`, and an end that trims what follows it (`-}}`).
DASHLESS_GUARD = "{{ if .Values.pages.enabled }}\n"
END_TRIMMED = "{{- end -}}\n"
A_PAGES_WORKLOAD = (
    "---\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: pages\nspec:\n  replicas: 1\n"
)


def _differences_with_chart(shape: str, brand: str, chart: Path) -> list[str]:
    with mock.patch.object(ref, "CHART", chart):
        return ref.differences(shape, brand, ref.render_shape(shape, brand))


def _insert_before(text: str, line_start: str, block: str) -> str:
    """`block` put in front of the first line of `text` that starts with `line_start`."""
    at = text.index(line_start)
    return text[:at] + block + text[at:]


def _edit(chart: Path, relative: str, edit: Callable[[str], str]) -> None:
    target = chart / relative
    target.write_text(edit(target.read_text(encoding="utf-8")), encoding="utf-8")


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", HELM)
@pytest.mark.parametrize(
    "guarded_edit",
    [
        # A workload appended to the template, wrapped in the guard.
        lambda c: (
            "templates/workloads.yaml",
            lambda t: t + GUARD + A_PAGES_WORKLOAD + "{{- end }}\n",
        ),
        # The same with a branch of its own inside the guard.
        lambda c: (
            "templates/workloads.yaml",
            lambda t: (
                t + GUARD + A_PAGES_WORKLOAD + "{{- if .Values.global }}\n  x: 1\n{{- end }}\n"
                "{{- end }}\n"
            ),
        ),
        # A path in the Ingress's own loop, guarded.
        lambda c: (
            "templates/ingress.yaml",
            lambda t: t.replace(
                "          {{- end }}\n    {{- end }}\n",
                GUARD + "          - path: /studio\n            pathType: Prefix\n"
                "{{- end }}\n          {{- end }}\n    {{- end }}\n",
                1,
            ),
        ),
        # The chart's default values gain a page-service section, off.
        lambda c: ("values.yaml", lambda t: t + "\npages:\n  enabled: false\n"),
    ],
    ids=["a guarded workload", "a guarded workload with a branch", "a guarded path", "values off"],
)
def test_a_pages_block_guarded_by_the_setting_is_not_a_change_while_it_is_off(
    shape: str,
    brand: str,
    guarded_edit: Callable[[Path], tuple[str, Callable[[str], str]]],
    tmp_path: Path,
) -> None:
    """The chart as it renders with `pages.enabled` off: a template block under
    `{{- if .Values.pages.enabled }}` ... `{{- end }}` is not in what is stored or compared, so the
    chart PL7a2b changes (a pages workload, a pages Ingress path, a default `pages: enabled:
    false`) is the reference unchanged, and the render-with-setting-absent case stays green. The
    unguarded version of each is red (`test_a_changed_helm_template_is_red`)."""
    copy = _chart_copy(tmp_path)
    relative, edit = guarded_edit(copy)
    _edit(copy, relative, edit)
    assert (copy / relative).read_text(encoding="utf-8") != (CHART_REAL / relative).read_text(
        encoding="utf-8"
    ), "the plant changed nothing"
    assert _differences_with_chart(shape, brand, copy) == []


CHART_REAL = ref.CHART


@pytest.mark.parametrize("shape", HELM)
def test_a_whole_template_file_under_the_guard_is_not_a_file_while_it_is_off(
    shape: str, tmp_path: Path
) -> None:
    """Helm writes nothing for a manifest that renders empty: a new `templates/pages.yaml` that is
    one guarded block is no new file in the reference. Unguarded it is red (the added-file case)."""
    copy = _chart_copy(tmp_path)
    (copy / "templates" / "pages.yaml").write_text(
        GUARD + A_PAGES_WORKLOAD + "{{- end }}\n", encoding="utf-8"
    )
    assert _differences_with_chart(shape, "govuk", copy) == []


@pytest.mark.parametrize("brand", ref.BRANDS)
@pytest.mark.parametrize("shape", HELM)
@pytest.mark.parametrize(
    ("relative", "edit", "line_has"),
    [
        # A guard on the section, not its `enabled`: a mapping is true whether or not it is off, so
        # this block renders while the setting is off.
        (
            "templates/workloads.yaml",
            lambda t: t + "{{- if .Values.pages }}\n" + A_PAGES_WORKLOAD + "{{- end }}\n",
            "{{- if .Values.pages }}",
        ),
        # The guard, then the body after the end: the workload is outside it.
        (
            "templates/workloads.yaml",
            lambda t: t + GUARD + "{{- end }}\n" + A_PAGES_WORKLOAD,
            "the rendered text goes on",
        ),
        # Guard and end on one line: not a block this reads, so it stays in view.
        (
            "templates/workloads.yaml",
            lambda t: t + "{{- if .Values.pages.enabled }}x{{- end }}\n",
            "pages.enabled",
        ),
        # An `else`: what is in it renders while the setting is off, so the block is not removed.
        (
            "templates/workloads.yaml",
            lambda t: t + GUARD + A_PAGES_WORKLOAD + "{{- else }}\n  y: 2\n{{- end }}\n",
            "{{- if .Values.pages.enabled }}",
        ),
        # A guard that is never closed: nothing is removed.
        (
            "templates/workloads.yaml",
            lambda t: t + GUARD + A_PAGES_WORKLOAD,
            "{{- if .Values.pages",
        ),
        # A guard closed by `{{- end -}}`: the trim after the action joins the line after the block
        # to the line before the guard, so the render changes while the setting is off. The block
        # is inserted before an existing line, so the view without it would equal the reference.
        (
            "templates/workloads.yaml",
            lambda t: _insert_before(
                t, "  maxUnavailable:", GUARD + A_PAGES_WORKLOAD + END_TRIMMED
            ),
            "{{- if .Values.pages.enabled }}",
        ),
        # A guard with no dash before `if`: off, the guard's own indentation and its line break are
        # left in the render, an extra line.
        (
            "templates/workloads.yaml",
            lambda t: _insert_before(
                t, "  maxUnavailable:", DASHLESS_GUARD + A_PAGES_WORKLOAD + "{{- end }}\n"
            ),
            "{{ if .Values.pages.enabled }}",
        ),
        # Switched on in the chart's own defaults: a page service rendered by default.
        ("values.yaml", lambda t: t + "pages:\n  enabled: true\n", "'pages:'"),
        # On, with a sub-toggle that is off (the shape PL7a2b is likely to write): the section's
        # own `enabled` is true, so it is not off, whatever a key nested in it says. This reaches
        # the filter's own branch; the bare case above passes through its fallthrough.
        (
            "values.yaml",
            lambda t: t + "pages:\n  enabled: true\n  ingress:\n    enabled: false\n",
            "'pages:'",
        ),
        # The same, with the sub-toggle written first and the section's own key after it.
        (
            "values.yaml",
            lambda t: t + "pages:\n  ingress:\n    enabled: false\n  enabled: true\n",
            "'pages:'",
        ),
    ],
    ids=[
        "a section guard",
        "the body after the end",
        "one line",
        "an else",
        "never closed",
        "a guard closed by a trimming end",
        "a guard with no dash",
        "on by default",
        "on by default with a sub-toggle off",
        "on by default, sub-toggle first",
    ],
)
def test_a_pages_change_that_renders_while_off_is_red(
    shape: str,
    brand: str,
    relative: str,
    edit: Callable[[str], str],
    line_has: str,
    tmp_path: Path,
) -> None:
    """The other side: what the guard does not cover is red, so the green above is the guard's."""
    copy = _chart_copy(tmp_path)
    _edit(copy, relative, edit)
    found = _differences_with_chart(shape, brand, copy)
    message = "\n".join(found)
    assert f"{ref.folder_name(shape, brand)}/chart/{relative}: first differing line" in message, (
        message
    )
    assert line_has in message, f"red for another reason:\n{message}"


@pytest.mark.parametrize(
    "section",
    [
        "pages:\n  enabled: false\n",
        "pages:\n  enabled: false\n  ingress:\n    enabled: true\n",
        "pages:\n  ingress:\n    enabled: true\n  enabled: false  # off\n",
    ],
    ids=["off", "off with a sub-toggle on", "off, sub-toggle first"],
)
def test_a_pages_section_that_is_off_in_its_own_key_is_not_in_the_view(section: str) -> None:
    """The other side of the nested-key plants: a section whose own `enabled` is false is off
    whatever its sub-keys say, and is not in the chart as it renders off."""
    assert ref.without_pages_section_when_off("a: 1\n\n" + section + "b: 2\n") == "a: 1\nb: 2\n"


# ---- the regenerate command --------------------------------------------------------------------


def _tree(root: Path) -> dict[str, bytes]:
    return {
        f"{folder.name}/{path}": data
        for folder in sorted(p for p in root.iterdir() if p.is_dir())
        for path, data in {
            **ref.read_folder(folder),
            ref.MANIFEST: (folder / ref.MANIFEST).read_bytes(),
        }.items()
    }


def test_writing_the_reference_twice_gives_the_same_bytes(tmp_path: Path) -> None:
    """The regenerate command is deterministic (twice, the same bytes, the same set of files), and
    what it writes is what is committed: a deliberate change is then the only diff."""
    first, second = tmp_path / "first", tmp_path / "second"
    ref.write_reference(first)
    ref.write_reference(second)
    ref.write_reference(second)  # over its own output: the same again, nothing stale left
    assert _tree(first) == _tree(second)
    assert _tree(first) == _tree(REFERENCE), "the committed reference is not what --write writes"


def test_writing_the_reference_removes_a_file_a_shape_no_longer_writes(tmp_path: Path) -> None:
    root = tmp_path / "reference"
    ref.write_reference(root)
    stale = root / "local-lite-govuk" / "old" / "gone.txt"
    stale.parent.mkdir(parents=True)
    stale.write_text("x")
    (root / "retired-shape-govuk").mkdir()
    (root / "retired-shape-govuk" / "f").write_text("x")
    ref.write_reference(root)
    assert not stale.exists() and not stale.parent.exists()
    assert not (root / "retired-shape-govuk").exists()
    assert _tree(root) == _tree(REFERENCE)


def test_the_check_command_reports_clean(capsys: pytest.CaptureFixture[str]) -> None:
    assert ref.main(["--check"]) == 0
    assert "0 difference(s)" in capsys.readouterr().out


def test_the_check_command_names_a_difference_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--check` on a reference that differs lists the file and the first differing line, and
    returns 1 (the clean run above is the same command on the real reference, so the red is the
    copy's)."""
    copy = tmp_path / "reference"
    shutil.copytree(REFERENCE, copy)
    assert ref.main(["--check", "--reference", str(copy)]) == 0
    capsys.readouterr()
    target = copy / "local-lite-govuk" / "Caddyfile"
    target.write_bytes(target.read_bytes() + b"handle /studio {\n}\n")
    assert ref.main(["--check", "--reference", str(copy)]) == 1
    out = capsys.readouterr().out
    assert "local-lite-govuk/Caddyfile" in out, out
    assert "first differing line" in out, out
    assert "reference_render: 0 difference(s)" not in out, out


# ---- the design tokens are pinned, in every shape ---------------------------------------------


def _with_real_tokens_changed(root: Path) -> Any:
    """The real token source changed on disk: the function both renderers call, read from a copy
    of the tokens file with one more line (its default `repo_root` pointed at the copy)."""
    from harness import keycloak_theme

    source = keycloak_theme.REPO_ROOT / keycloak_theme.TOKENS_RELATIVE_PATH
    target = root / keycloak_theme.TOKENS_RELATIVE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8") + "\n:root { --n0: #123456; }\n")
    return mock.patch.object(keycloak_theme.read_tokens, "__defaults__", (root,))


def test_a_change_to_the_design_tokens_moves_no_fixture(tmp_path: Path) -> None:
    """The tokens are the design package's business, not a deployment's shape: with the real
    tokens changed, every shape (the compose shapes' sign-in theme and the cluster shapes' values)
    still renders the reference. Shown red first: with the pinning removed, the same change moves a
    compose shape and a cluster shape."""
    from harness import keycloak_theme

    original = keycloak_theme.read_tokens
    with _with_real_tokens_changed(tmp_path):
        assert "#123456" in original()
        for shape, brand in SHAPE_BRANDS:
            found = ref.differences(shape, brand, ref.render_shape(shape, brand))
            assert not found, "a token change moved the reference:\n" + "\n".join(found)
        # The plant: no pinning, so the changed tokens reach the render.
        with mock.patch.object(ref, "pinned_inputs", contextlib.nullcontext):
            for shape, brand in (("small", "govuk"), ("cluster", "govuk")):
                red = ref.differences(shape, brand, ref.render_shape(shape, brand))
                assert red, f"{shape}-{brand} did not move with the tokens unpinned"
    # And clean again once the real source is back.
    assert not ref.differences("small", "govuk", ref.render_shape("small", "govuk"))


def test_no_stored_file_holds_the_real_tokens() -> None:
    """The pinned marker is what every stored copy of the tokens carries, not the design package's
    own file (the head of the real file is in none of them)."""
    from harness import keycloak_theme

    real_head = keycloak_theme.read_tokens().splitlines()[0]
    assert real_head and real_head != ref.PINNED_TOKENS.splitlines()[0]
    holders = [
        f"{folder}/{path}"
        for folder in ref.stored_folders()
        for path, data in ref.read_folder(REFERENCE / folder).items()
        if real_head.encode() in data
    ]
    assert not holders, f"stored files hold the real tokens: {holders}"


# ---- the fixtures hold nothing they must not --------------------------------------------------


def test_the_stored_files_carry_no_secret_address_or_real_host() -> None:
    """The renders use synthetic settings: no credential-shaped string, no address but the
    product's own placeholder, no URL host that is not synthetic (`example.org`, `.localhost`,
    `.internal`), a service on the internal network or a public software or standards host, and no
    cloud account but the synthetic one."""
    assert ref.stored_folders(), "nothing is stored, so there is nothing to scan"
    found = [
        f"{folder}/{finding}"
        for folder in ref.stored_folders()
        for finding in ref.stored_text_findings(ref.read_folder(REFERENCE / folder))
    ]
    assert not found, "\n".join(found)


#: Each is put together here, in pieces, so that no whole credential-shaped string sits in this
#: file; what is planted is the shape a render would emit it in.
_PLANTS = [
    ("OSPREY_ARCADEDB_PASSWORD=" + "hunter2" * 2 + "\n", "credential-shaped"),
    ("      OPENAI_API_KEY: " + "sk" + "-" + "a1b2c3d4" * 3 + "\n", "credential-shaped"),
    ('Authorization: "' + "Bear" + "er " + "x1y2z3w4" * 3 + '"\n', "credential-shaped"),
    ("-----BEGIN " + "RSA PRIVATE" + " KEY-----\n", "credential-shaped"),
    ("      LITELLM_MASTER_KEY: " + "AK" + "IA" + "Q" * 16 + "\n", "credential-shaped"),
    ("OSPREY_LITELLM_MASTER_SECRET=" + "sk" + "-" + "a1b2c3d4" * 3 + "\n", "credential-shaped"),
    ("OSPREY_PAGES_CLIENT_SECRET=" + "abcdef0123456789" + "\n", "credential-shaped"),
    ("contact: someone" + "@" + "real-organisation.co.uk\n", "address"),
    ("origin: https://portal.not-an-example.co.uk\n", "host"),
    ("image: 210987654321.dkr.ecr.eu-west-2.amazonaws.com/api:1\n", "cloud account"),
]


#: A host written bare, as the renderers write one (so the scan is shown red on the form the
#: renderers use, not only on `https://`): the real cluster values' own lines with the synthetic
#: host swapped for a real-shaped one. Each is named in the stored `cluster-ospreyflow/values.yaml`.
_BARE_HOSTS = [
    ("VALKEY_HOST: cache.example.internal", "VALKEY_HOST: cache.acme-corp.co.uk"),
    ("psql -h db.example.internal ", "psql -h db.acme-corp.com "),
    ("host: db.example.internal", "host: db.acme-corp.zone"),
    ("endpoint: s3.eu-west-2.amazonaws.com", "endpoint: s3.storage.acme-corp.example"),
    ("image: ghcr.io/ospreyflow/api:", "image: registry.acme-corp.co.uk/ospreyflow/api:"),
    ("image: ghcr.io/ospreyflow/api:", "image: evilghcr.io/ospreyflow/api:"),
]


@pytest.mark.parametrize(("real", "planted"), _BARE_HOSTS)
def test_the_scan_is_red_on_a_host_written_without_a_scheme(real: str, planted: str) -> None:
    """The renderers write database, cache, search and object-store hosts and image registries bare.
    The text below is the stored cluster values with one of those swapped for a real-shaped host
    (each `real` is in the stored file, which is clean without the swap)."""
    values = ref.read_folder(REFERENCE / "cluster-ospreyflow")
    assert ref.stored_text_findings(values) == []
    text = values["values.yaml"].decode("utf-8")
    assert real in text, f"{real!r} is not a line the renderer writes"
    swapped = text.replace(real, planted)
    found = ref.stored_text_findings({**values, "values.yaml": swapped.encode("utf-8")})
    assert found, f"{planted!r} was not seen"
    assert all("host" in line for line in found), found


def test_the_scan_leaves_the_pinned_values_and_identifiers_alone() -> None:
    """Its own green for the `deployment.env` lines: a pinned value (the secrets `apply` mints are
    `PINNED_<n>` here) and an identifier whose name has `TOKEN` in it are not findings."""
    ok = (
        "OSPREY_OIDC_CLIENT_SECRET=PINNED_3\nOSPREY_LITELLM_MASTER_SECRET=sk-PINNED_12\n"
        "OIDC_TOKEN_EXCHANGE_CLIENT_ID=osprey-conduit\n"
    )
    assert ref.stored_text_findings({"deployment.env": ok.encode()}) == []


def test_the_scan_leaves_the_hosts_the_renderers_write_alone() -> None:
    """Its own green: the synthetic and public hosts, a service name, a pod's name under its
    headless service and a version are not findings (so the red above is the plant's)."""
    ok = (
        "VALKEY_HOST: cache.example.internal\nimage: ghcr.io/ospreyflow/api:1\n"
        "endpoint: s3.eu-west-2.amazonaws.com\nhost: arcadedb-0.arcadedb-headless\n"
        "version: 25.8.33.6\nhost: reference.ospreyflow.localhost\nimport java.io.File;\n"
    )
    assert ref.stored_text_findings({"values.yaml": ok.encode()}) == []


@pytest.mark.parametrize(("planted", "expect"), _PLANTS)
def test_the_scan_of_the_stored_files_is_red_on_each_thing_it_names(
    planted: str, expect: str
) -> None:
    """The scan's own red-then-green (rule 15): each plant is appended to a real stored file, which
    is clean without it, and is named by the finding it should be."""
    real = ref.read_folder(REFERENCE / "small-ospreyflow")
    assert ref.stored_text_findings(real) == []
    planted_files = {**real, "compose.yaml": real["compose.yaml"] + planted.encode("utf-8")}
    found = ref.stored_text_findings(planted_files)
    assert any(expect in line for line in found), found
    # A plant may be two things at once (an address's own domain is a host); nothing else is named.
    assert all(expect in line or "host" in line for line in found), found


# ---- the guard's block count when an action is not on a line of its own (rule 15) ----


#: A guarded block inside an outer `range`, with `inside` where a template might put an action that
#: opens or closes a block somewhere other than the whole of its line. `real: {{ . }}` and the
#: range's own end render while the setting is off, so the view must keep them.
def _ranged_guard(inside: str) -> str:
    return (
        "{{- range .Values.list }}\n"
        "{{- if .Values.pages.enabled }}\n"
        f"{inside}"
        "kind: Deployment\n"
        "{{- end }}\n"
        "real: {{ . }}\n"
        "{{- end }}\n"
    )


def test_the_guard_scan_removes_only_the_block_when_every_action_is_on_its_own_line() -> None:
    """The control for the plants below: the same template with the inner `if` written on lines
    of its own is read right (the guard's block out, the range and `real:` kept), so the plants'
    red is the inline form's."""
    template = _ranged_guard("{{- if .Values.global }}\nx: 1\n{{- end }}\n")
    # The inner block's own end sits inside the guard: the guard closes at the second end.
    assert ref.without_pages_guard(template) == (
        "{{- range .Values.list }}\nreal: {{ . }}\n{{- end }}\n"
    )


@pytest.mark.parametrize(
    "inside",
    [
        # An `if` opened and closed on one line: the open counts, the close is not on a line alone.
        "{{- if .Values.global }}x: 1{{- end }}\n",
        # A close after other text on its line, under an open of its own.
        "{{- if .Values.global }}\n  x: 1 {{- end }}\n",
        # A close after text with no open of its own: the count would be one short.
        "  x: 1 {{- end }}\n",
        # An open after text.
        "  x: 1 {{- if .Values.global }}\n{{- end }}\n",
        # Two actions on one line: an end, then an open.
        "{{- if .Values.global }}\n{{- end }}{{- if .Values.other }}\n{{- end }}\n",
        # An `else` after text, at the guard's own level: what it holds renders while off.
        "  x: 1 {{- else }}\n",
    ],
    ids=[
        "inline if and end",
        "a close after text under an open",
        "a close after text",
        "an open after text",
        "an end and an open on one line",
        "an else after text",
    ],
)
def test_a_guard_whose_block_count_cannot_be_told_is_left_in_the_view(inside: str) -> None:
    """`without_pages_guard` removes a guarded block only when it can count its end. An action that
    opens or closes a block anywhere but as the whole of a line makes the count unreliable, so the
    guard and everything the scan would have passed stay in the view (a shown change), and never a
    line that renders while the setting is off is taken out: that line would then be stored by
    `--write` as if it were not there, and a change to it would show nothing."""
    template = _ranged_guard(inside)
    assert ref.without_pages_guard(template) == template
    assert "real: {{ . }}" in ref.without_pages_guard(template)


# ---- a guard's own trim markers: Go's lexer applies them whether or not the if is taken ----


def test_a_guard_removed_from_the_view_is_one_whose_off_render_is_the_view() -> None:
    """The control for the plants below: a dashed guard closed by a plain end, after a line of
    content with nothing trailing on it, renders (off) as the template with the block's lines taken
    out. Inside the block, an end with a trailing trim marker is skipped text and changes nothing:
    only the guard's own two actions count."""
    template = "a: 1\n" + GUARD + "{{- if .Values.global }}\nx: 1\n{{- end -}}\n{{- end }}\nb: 2\n"
    assert ref.without_pages_guard(template) == "a: 1\nb: 2\n"


@pytest.mark.parametrize(
    "template",
    [
        # The guard's own end trims what follows it: off, `b: 2` loses its line break and joins
        # `a: 1` (the render is `a: 1b: 2`).
        "a: 1\n" + GUARD + "x: 1\n{{- end -}}\n  b: 2\n",
        # The same where the end is the last thing in the template: nothing follows, but the shape
        # is the same, and is not read.
        "a: 1\n" + GUARD + "x: 1\n{{- end -}}\n",
        # No dash before `if`: off, the guard's indentation and the line break after the end stay,
        # one extra line in the render (inside a block scalar, content).
        "a: 1\n" + DASHLESS_GUARD + "x: 1\n{{- end }}\nb: 2\n",
        # Blank lines before a dashed guard: its left trim takes them, so off the render has none.
        "a: 1\n\n" + GUARD + "x: 1\n{{- end }}\nb: 2\n",
        # Spaces at the end of the line before a dashed guard: the left trim takes them too.
        "a: 1  \n" + GUARD + "x: 1\n{{- end }}\nb: 2\n",
        # A guard first in the template with content after the block: off, the render starts with
        # the line break that follows the end.
        GUARD + "x: 1\n{{- end }}\nb: 2\n",
    ],
    ids=[
        "an end that trims what follows",
        "a trimming end last",
        "a guard with no dash",
        "a blank line before the guard",
        "spaces before the guard",
        "a guard first, with content after",
    ],
)
def test_a_guard_whose_off_render_is_not_the_template_without_the_block_is_left_in_the_view(
    template: str,
) -> None:
    """`without_pages_guard` removes a block only where Go's lexer would leave the rest of the
    template as the view has it. A trim marker on the guard's left, on the end's right, or none
    where there should be one, changes the whitespace around the block whether or not the `if` is
    taken; the view then keeps the guard and the block, and the change shows (rule 15: each plant
    is the template the scan would read, not a bare string that fails another way)."""
    assert ref.without_pages_guard(template) == template


def test_a_guard_that_is_the_whole_template_is_not_a_file() -> None:
    """The one place a guard may come first: nothing follows the block, so the off render is a
    line break, which Helm does not write as a manifest."""
    assert (
        ref.chart_off_view("templates/pages.yaml", (GUARD + "x: 1\n{{- end }}\n").encode()) is None
    )
