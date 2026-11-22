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

**What is not stored, and why.** `helm template` output: it needs the `helm` binary, which a pure
test does not assume (`make chart-check` and `make cp-policy-check` template the chart). The values
that the chart reads are stored; the chart's own templates are not rendered here. `osprey.yaml`
(the input) and `.rendered` (the list of what was written) are not rendered content. There is no
`deployment.json` among the files: the renderers write `glass.json` (ADR-114 Amendment 4), which is
stored; `/deployment.json` is what the Glass is served from it.

**No network, no docker, no real secret, no clock.** The renders take their digests from a hash of
the image reference (`tools.reference_render.resolver`: the registry is never asked) and have the
commit, the version and the design tokens pinned (`pinned_inputs`: they are read from the checkout,
and would otherwise move with every commit). A render reads no clock and mints no secret (`apply`
mints them after it), so the stored `deployment.env` names variables and holds no value; the last
case below scans every stored file for a credential-shaped string, an address, a real host and a
cloud account other than the synthetic one, and is shown red on each.

**The page-service setting.** Today there is none: `OspreyConfig` has no `pages` section, and no
renderer reads one. The case `test_the_render_with_no_page_service_setting_equals_the_reference`
renders with no `pages` setting passed and requires the reference. PL7a2b adds the setting, off by
default; that case then holds it to "off, or not set, renders what it rendered", and stays green or
the slice is wrong. It checks `model_fields_set`, so it still means "not set" once the field exists.

**Planted faults, at the shape the renderer really emits (rule 15).** Each is a patched function
called in place of the real one (the real renderer files are never edited): a `pages:` service in
the compose services; a `handle /studio` block in the Caddyfile; a changed Helm value (on both Helm
shapes); a file dropped from a shape (on a compose shape and on the Terraform one); one byte changed
in a stored fixture (a copy of it). Each is shown clean first (so the red is the plant's), red with
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
they name, through the renderer), and, by importing the renderers, `OspreyFlow_Core/harness/` and
`OspreyFlow_Core/packages/schemas/`. It walks no other folder.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
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
        "cluster": {"values.yaml", "versions.lock"},
        "cloud-platform": {"values.yaml", "versions.lock", "images.yaml", "terraform/rds.tf"},
        "cloud-platform-poc": {"values.yaml", "images.yaml", "terraform/rds.tf", "INSTALL.md"},
    }[shape]
    assert expected <= set(paths), f"{folder.name} lacks {sorted(expected - set(paths))}"


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


def test_the_check_command_reports_clean_and_names_a_difference(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert ref.main(["--check"]) == 0
    assert "0 difference(s)" in capsys.readouterr().out


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
    ("contact: someone" + "@" + "real-organisation.co.uk\n", "address"),
    ("origin: https://portal.not-an-example.co.uk\n", "host"),
    ("image: 210987654321.dkr.ecr.eu-west-2.amazonaws.com/api:1\n", "cloud account"),
]


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
    assert found and all(expect in line for line in found), found
