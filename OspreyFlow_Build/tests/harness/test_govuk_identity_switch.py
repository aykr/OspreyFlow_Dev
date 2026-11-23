"""Slice PL7c, item 1: the GOV.UK identity switch, `appearance.govuk_identity` (ADR-152 decision 14, invariant I9).

Off by default; a real `true` or `false` and nothing else; left out of every rendered file while it is off (a deployment
that does not use it renders byte for byte what it did); and, on, told to the Glass (`/deployment.json`), to the sign-in
page's theme (its stylesheet's marker and its script's settings) and to the workspace's build (the compose `build.args`,
which `test_default_build_holds_no_gds_transport.py` reads). The switch is the only thing that turns the GOV.UK identity
on: under `brand: govuk` alone, nothing is told.

Rule 15: each refusal is planted in the shape the code receives it: a YAML file's own scalars (`yaml.safe_load` of the
text a person writes: `yes`, `on`, a quoted `"true"`, a number), not a hand-written stand-in.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from harness.keycloak_theme import (
    GOVUK_CHROME_SCRIPT,
    THEME_SCRIPT,
    read_theme_script,
    render_login_theme,
)
from harness.render import compose_services, service_images
from harness.site import render_glass_settings
from pydantic import ValidationError
from tools.layout import CORE

from schemas.deployment import AppearanceConfig, OspreyConfig

TOKENS = (CORE / "packages" / "design" / "tokens.css").read_text(encoding="utf-8")
GLASS = "http://glass.example.test:8081"


def _told(raw: dict[str, object]) -> dict[str, object]:
    config = OspreyConfig.model_validate({"components": {"source_path": "."}, "appearance": raw})
    return dict(json.loads(render_glass_settings(config))["appearance"])


def test_govuk_identity_is_off_by_default() -> None:
    assert AppearanceConfig().govuk_identity is False
    assert OspreyConfig().appearance.govuk_identity is False
    assert (
        OspreyConfig.model_validate({"appearance": {"brand": "govuk"}}).appearance.govuk_identity
        is False
    )


def test_off_the_glass_is_told_nothing_new() -> None:
    told = _told({"brand": "govuk", "phase": "beta"})
    assert "govuk_identity" not in told
    assert told == {"brand": "govuk", "service_name": None, "organisation": None, "phase": "beta"}
    # Written as false, it is the same as not written at all.
    assert _told({"brand": "govuk", "phase": "beta", "govuk_identity": False}) == told


def test_on_the_glass_is_told_it() -> None:
    assert _told({"brand": "govuk", "govuk_identity": True})["govuk_identity"] is True


@pytest.mark.parametrize(
    "written", ["yes", "on", "'true'", '"yes"', "1", "0", "null", "[true]", "maybe"]
)
def test_only_a_real_true_or_false_is_accepted(written: str) -> None:
    # What a person types after `govuk_identity:`, read as the loader reads a file. An unquoted `yes` or `on` is a real
    # boolean in YAML 1.1 (`safe_load` turns it into True before the schema sees it), so it is accepted as what it is;
    # every other spelling reaches the schema as a string, a number or a null and is refused in words.
    value = yaml.safe_load(f"govuk_identity: {written}")["govuk_identity"]
    if isinstance(value, bool):
        assert AppearanceConfig(govuk_identity=value).govuk_identity is value
        return
    with pytest.raises(ValidationError, match="appearance.govuk_identity must be true or false"):
        AppearanceConfig(govuk_identity=value)


def test_the_switch_means_nothing_under_the_ospreyflow_brand_in_the_sign_in_theme() -> None:
    on = AppearanceConfig(brand="ospreyflow", govuk_identity=True)
    assert render_login_theme(TOKENS, appearance=on, glass_origin=GLASS) == render_login_theme(
        TOKENS
    )


def test_under_govuk_the_sign_in_theme_is_what_it_was_while_the_switch_is_off() -> None:
    off = render_login_theme(
        TOKENS, appearance=AppearanceConfig(brand="govuk", phase="beta"), glass_origin=GLASS
    )
    assert "data-govuk-identity" not in off[THEME_SCRIPT]
    # The settings the harness writes are the script's first line; the script's own text names the key.
    assert "govukIdentity" not in off[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]


def test_under_govuk_the_sign_in_theme_is_told_the_switch_when_it_is_on() -> None:
    on = AppearanceConfig(brand="govuk", phase="beta", govuk_identity=True)
    theme = render_login_theme(TOKENS, appearance=on, glass_origin=GLASS)
    assert (
        'document.documentElement.setAttribute("data-govuk-identity", "on");' in theme[THEME_SCRIPT]
    )
    # The page is marked with the brand first, then the switch, before the theme script's own lines.
    assert theme[THEME_SCRIPT].index('"data-brand"') < theme[THEME_SCRIPT].index(
        '"data-govuk-identity"'
    )
    assert '"govukIdentity": true' in theme[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]


def test_the_typeface_is_in_one_rule_that_needs_the_switch_and_the_address() -> None:
    """tokens.css, which the sign-in theme's stylesheet carries whole: GDS Transport named only where
    `data-govuk-typeface="on"` is, which is set only with the switch on AND on a gov.uk address (GDS Transport's licence:
    ADR-152 Amendment 2 item 3, `fonts.json` `only_when` and `only_on`). The marker's own behaviour is proved below for the
    sign-in theme's script and in `brand.test.tsx` for the Glass."""
    code = re.sub(r"/\*.*?\*/", "", TOKENS, flags=re.S)
    rules = [m.group(1).strip() for m in re.finditer(r"([^{}]+)\{[^}]*GDS Transport[^}]*\}", code)]
    assert rules == ['[data-brand="govuk"][data-govuk-typeface="on"]']


NODE = shutil.which("node")


def _marks_set_by_the_theme_script(hostname: str, *, identity: bool = True) -> dict[str, str]:
    """Runs the sign-in theme's own GOV.UK prefix (the lines the harness writes before the theme script's) in node with a
    page at `hostname`, and returns the attributes it put on <html>. The prefix is the generated text, not a copy of it."""
    assert NODE, "node is needed to run the sign-in theme's script"
    theme = render_login_theme(
        TOKENS,
        appearance=AppearanceConfig(brand="govuk", govuk_identity=identity),
        glass_origin=GLASS,
    )
    prefix = theme[THEME_SCRIPT].split(read_theme_script(), 1)[0]
    assert prefix.startswith('document.documentElement.setAttribute("data-brand", "govuk");')
    harness = (
        "const set = {};"
        f"globalThis.window = {{ location: {{ hostname: {json.dumps(hostname)} }} }};"
        "globalThis.document = { documentElement: { setAttribute: (k, v) => { set[k] = v; } } };"
        f"{prefix}\nconsole.log(JSON.stringify(set));"
    )
    done = subprocess.run(  # noqa: S603
        [NODE, "-e", harness], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    return dict(json.loads(done.stdout))


@pytest.mark.parametrize("host", ["service.gov.uk", "gov.uk", "Service.GOV.UK", "service.gov.uk."])
def test_the_sign_in_theme_draws_the_typeface_on_a_gov_uk_address_with_the_switch_on(
    host: str,
) -> None:
    assert _marks_set_by_the_theme_script(host) == {
        "data-brand": "govuk",
        "data-govuk-identity": "on",
        "data-govuk-typeface": "on",
    }


@pytest.mark.parametrize(
    "host", ["id.other.example.test", "localhost", "notgov.uk", "service.gov.uk.example.test", ""]
)
def test_the_sign_in_theme_draws_no_typeface_off_gov_uk_with_the_switch_on(host: str) -> None:
    """The case the I9 row names and the first round missed: the switch on at an address that is not gov.uk."""
    assert _marks_set_by_the_theme_script(host) == {
        "data-brand": "govuk",
        "data-govuk-identity": "on",
    }


def test_the_sign_in_theme_with_the_switch_off_sets_no_identity_mark_on_gov_uk() -> None:
    assert _marks_set_by_the_theme_script("service.gov.uk", identity=False) == {
        "data-brand": "govuk"
    }


# ----------------------------------------------- the build: the stylesheet's own stacks follow the address too

SYNC = CORE / "apps" / "workspace" / "scripts" / "sync_govuk_assets.mjs"
PACKAGE_CSS = CORE / "node_modules" / "govuk-frontend" / "dist" / "govuk" / "govuk-frontend.min.css"


def _node_json(script: str) -> dict[str, object]:
    assert NODE
    done = subprocess.run(  # noqa: S603
        [NODE, "--input-type=module", "-e", script],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return dict(json.loads(done.stdout))


def _gated_stylesheet() -> dict[str, object]:
    return _node_json(
        f"import {{ gateTypefaceOnTheAddress }} from {json.dumps(SYNC.as_uri())};"
        "import { readFileSync } from 'node:fs';"
        f"const r = gateTypefaceOnTheAddress(readFileSync({json.dumps(str(PACKAGE_CSS))}, 'utf8'));"
        "console.log(JSON.stringify({ stacks: r.stacks, css: r.css }));"
    )


def test_a_build_with_the_switch_on_names_the_typeface_at_the_head_of_no_stack() -> None:
    """GOV.UK Frontend's own components write `font-family:GDS Transport,arial,sans-serif`; left as it is, the switch on at
    any address would draw the face in them. Each stack must instead ask for `--govuk-typeface`, which only the
    gov.uk-address marker defines."""
    raw = PACKAGE_CSS.read_text("utf-8")
    assert len(re.findall(r"font-family:GDS Transport,", raw)) > 10, (
        "the package's stacks moved: update the build step"
    )
    done = _gated_stylesheet()
    css = str(done["css"])
    assert done["stacks"] == len(re.findall(r"font-family:GDS Transport,", raw))
    assert "font-family:GDS Transport," not in css
    assert "font-family:var(--govuk-typeface,)arial,sans-serif" in css
    # The face is still declared (the rules are what the marker's variable names), and nothing defines the variable here.
    assert "@font-face" in css and "--govuk-typeface:" not in css


def _sync_in_scratch(scratch: Path, script: str) -> subprocess.CompletedProcess[str]:
    """The sync step, as text given, run with the switch on in a scratch copy of the workspace folder (as
    `test_default_build_holds_no_gds_transport.py` runs it), with `node_modules` linked so the package resolves."""
    assert NODE
    app = scratch / "apps" / "workspace"
    (app / "scripts").mkdir(parents=True)
    (app / "scripts" / SYNC.name).write_text(script, "utf-8")
    (scratch / "node_modules").symlink_to(CORE / "node_modules")
    env = {**os.environ, "OSPREY_GOVUK_IDENTITY": "1"}
    return subprocess.run(  # noqa: S603
        [NODE, str(Path("scripts") / SYNC.name)],
        cwd=app,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_the_build_step_is_red_when_a_stack_is_left_naming_the_face(tmp_path: Path) -> None:
    """Rule 15: the real script, with the gating made to leave every stack as the package wrote it (the way a build would
    ship if the gating were lost), run with the switch on: it must refuse, not write a stylesheet that draws GDS Transport
    at every address. The same script, as it is, is shown to run green first, so the red is the plant's."""
    real = SYNC.read_text("utf-8")
    ok = _sync_in_scratch(tmp_path / "real", real)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    written = (
        tmp_path
        / "real"
        / "apps"
        / "workspace"
        / "public"
        / "assets"
        / "govuk"
        / "govuk-frontend.css"
    ).read_text("utf-8")
    assert "font-family:GDS Transport," not in written and "var(--govuk-typeface,)" in written
    planted, n = re.subn(
        r"export function gateTypefaceOnTheAddress\(css\) \{.*?\n\}\n",
        "export function gateTypefaceOnTheAddress(css) { return { css, stacks: 1 }; }\n",
        real,
        flags=re.S,
    )
    assert n == 1, (
        "the script has no `gateTypefaceOnTheAddress` function the plant can replace: update this test"
    )
    bad = _sync_in_scratch(tmp_path / "planted", planted)
    assert bad.returncode != 0 and "did not rewrite cleanly" in bad.stderr, bad.stdout + bad.stderr


# --------------------------------------------------------------- the renderer and the schema: what the switch reaches


def _workspace_build(appearance: dict[str, object], **components: object) -> dict[str, object]:
    config = OspreyConfig.model_validate(
        {"components": {"source_path": ".", **components}, "appearance": appearance}
    )
    return dict(
        compose_services(config, service_images(config, build_context="../../.."))["workspace"][
            "build"
        ]
    )


def test_the_switch_means_nothing_under_the_ospreyflow_brand_in_the_build() -> None:
    """ADR-152 decision 14: it means nothing under `ospreyflow`, so the image a deployment of that brand builds holds no
    GDS Transport either, whatever the switch says."""
    assert "args" not in _workspace_build({"brand": "ospreyflow", "govuk_identity": True})
    assert _workspace_build({"brand": "ospreyflow", "govuk_identity": True}) == _workspace_build(
        {"brand": "ospreyflow"}
    )
    assert _workspace_build({"brand": "govuk", "govuk_identity": True})["args"] == {
        "OSPREY_GOVUK_IDENTITY": "1"
    }


# ----- the switch on, by every route that decides whether the workspace is built: the file is read first, the build
# is settled after it, so the refusal cannot be the schema's (a finding of round 3: it refused `--build` from a checkout).

GOVUK_ON = "appearance:\n  brand: govuk\n  govuk_identity: true\n"


def _apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *flags: str, osprey_yaml: str = GOVUK_ON
) -> tuple[int, dict[str, object]]:
    """The real `harness.apply.main` over a written `osprey.yaml` (no `components.source_path`, as the CLI's own config is),
    with the preflight, the compose commands and the steps that need a running deployment stood in for, so nothing
    reaches Docker. Returns the exit code and the compose file it wrote (empty when it wrote none)."""
    from types import SimpleNamespace

    from harness import apply
    from harness.preflight.result import passed

    monkeypatch.setattr(apply, "_run", lambda *_a, **_k: "")
    monkeypatch.setattr(apply, "answer_localhost_with_loopback", lambda: None)
    monkeypatch.setattr(apply, "ALL_CHECKS", [SimpleNamespace(check=lambda _c: passed("ports"))])
    monkeypatch.setattr(apply, "uploads_ready", lambda _f: "ready")
    monkeypatch.setattr(apply, "stores_moved", lambda _f, _h: SimpleNamespace(services=[]))
    monkeypatch.setattr(apply, "wait_for_health", lambda _f, **_k: {"api": "healthy"})
    monkeypatch.setattr(apply, "move_model_keys_into_gateway", lambda _f: "none")
    monkeypatch.setattr(apply, "_wait_for_models", lambda _f, _c: "none")
    monkeypatch.setattr(apply, "grant_service_account_roles", lambda **_k: None)
    config = tmp_path / "osprey.yaml"
    config.write_text(osprey_yaml, encoding="utf-8")
    assert "source_path" not in osprey_yaml
    code = apply.main(
        [
            "--config",
            str(config),
            "--out-root",
            str(tmp_path / "generated"),
            "--skip-verify",
            *flags,
        ]
    )
    composes = list((tmp_path / "generated").glob("*/compose.yaml"))
    return code, (yaml.safe_load(composes[0].read_text("utf-8")) if composes else {})


def test_the_identity_on_builds_with_the_argument_when_apply_builds_from_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`start --build` runs `harness.apply --build` over a config with no `source_path`: the validator that refused this at
    load (before the flag was applied) made the switch unusable on the CLI's own build route."""
    code, compose = _apply(tmp_path, monkeypatch, "--build")
    assert code == 0
    assert compose["services"]["workspace"]["build"]["args"] == {"OSPREY_GOVUK_IDENTITY": "1"}


def test_the_identity_off_builds_with_no_argument_when_apply_builds_from_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, compose = _apply(
        tmp_path, monkeypatch, "--build", osprey_yaml="appearance:\n  brand: govuk\n"
    )
    assert code == 0
    assert "args" not in compose["services"]["workspace"]["build"]


def test_the_identity_on_with_the_releases_images_is_refused_in_words_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The release's images are default builds: with no build there is nowhere to pass the switch, so apply says so, at
    the render, and writes nothing, and does not leave the type to fall back to arial in silence."""
    code, compose = _apply(tmp_path, monkeypatch, "--no-build")
    said = capsys.readouterr()
    assert code != 0 and compose == {}
    assert "appearance.govuk_identity is on" in said.out + said.err
    assert "pulls the workspace image" in said.out + said.err


def test_the_file_with_the_identity_on_and_no_source_path_still_loads() -> None:
    """The schema reads the file as written; whether the image is built is settled later (`--build`, the CLI's install, a
    cloud platform's own build), so it cannot refuse here."""
    config = OspreyConfig.model_validate({"appearance": {"brand": "govuk", "govuk_identity": True}})
    assert config.appearance.govuk_identity is True


def test_a_render_that_pulls_the_workspace_refuses_the_identity_in_words() -> None:
    from harness.render import GovukIdentityNeedsABuild, render

    pulled = OspreyConfig.model_validate({"appearance": {"brand": "govuk", "govuk_identity": True}})
    with pytest.raises(GovukIdentityNeedsABuild, match="pulls the workspace image"):
        render(pulled, allow_unpinned=True)
    # Off, or under the other brand (where it means nothing), a pulled render is as it was.
    render(OspreyConfig.model_validate({"appearance": {"brand": "govuk"}}), allow_unpinned=True)
    render(
        OspreyConfig.model_validate(
            {"appearance": {"brand": "ospreyflow", "govuk_identity": True}}
        ),
        allow_unpinned=True,
    )


def test_a_cluster_that_pulls_the_releases_images_refuses_the_identity() -> None:
    """Enterprise pulls the release's images by digest: nothing to pass the switch to."""
    from harness.render import GovukIdentityNeedsABuild, render

    from tests.harness.test_cluster_render import AWS, _resolver, cluster_config

    config = cluster_config(AWS, appearance={"brand": "govuk", "govuk_identity": True})
    with pytest.raises(GovukIdentityNeedsABuild, match="pulls the workspace image"):
        render(config, resolver=_resolver)
    # The same cluster with the switch off renders, so the refusal is the switch's.
    render(cluster_config(AWS, appearance={"brand": "govuk"}), resolver=_resolver)


def _images_plan(**appearance: object) -> list[dict[str, object]]:
    """A cloud platform's image plan (`images.yaml`, which `ospreyflow images push` follows), from its own fixture."""
    from tools.cp_policy_check import FIXTURES, _resolver

    from harness.render import render

    raw = yaml.safe_load((FIXTURES / "development.yaml").read_text(encoding="utf-8"))
    raw["appearance"] = {**raw.get("appearance", {}), **appearance}
    config = OspreyConfig.model_validate(raw)
    plan = yaml.safe_load(render(config, resolver=_resolver).artefacts["images.yaml"])
    return list(plan["images"])


def test_a_cloud_platform_builds_the_workspace_with_the_argument_when_the_identity_is_on() -> None:
    """A cloud platform builds ours itself (`images push`, from the profile's build arguments) and refuses
    `components.source_path`, so the argument has to come with the plan, not from the compose file's `build`."""
    workspace = next(
        i
        for i in _images_plan(brand="govuk", govuk_identity=True)
        if "/workspace:" in str(i["target"])
    )
    assert workspace["build_args"] == {"OSPREY_GOVUK_IDENTITY": "1"}
    # Only the workspace's: no other image of ours is told.
    others = [
        i
        for i in _images_plan(brand="govuk", govuk_identity=True)
        if "/workspace:" not in str(i["target"])
    ]
    assert all("OSPREY_GOVUK_IDENTITY" not in dict(i.get("build_args", {})) for i in others)


@pytest.mark.parametrize(
    "appearance", [{"brand": "govuk"}, {"brand": "ospreyflow", "govuk_identity": True}, {}]
)
def test_a_cloud_platform_builds_the_default_workspace_when_the_identity_is_off(
    appearance: dict[str, object],
) -> None:
    workspace = next(i for i in _images_plan(**appearance) if "/workspace:" in str(i["target"]))
    assert "OSPREY_GOVUK_IDENTITY" not in dict(workspace.get("build_args", {}))


# ----- the pages' Default tree: the build step that keeps the GOV.UK brand out of its stylesheet, planted (rule 15). A finding
# of round 3: the scan file plants only into copies of the built output, so nothing showed it red if the build step itself
# stopped dropping `[data-brand="govuk"]` (whose block now holds the rule that names GDS Transport).

PAGES_SCRIPT = CORE / "apps" / "pages" / "scripts" / "assets.mjs"


def _pages_build(scratch: Path, script: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    """The pages asset build, as text given, run in a scratch folder shaped like `OspreyFlow_Core`: the design package copied
    (the build keeps the GOV.UK brand out of the files that live under it, by path, so they are real files here), the
    installed packages linked, and no client module (the stylesheet is what is in question)."""
    assert NODE
    core = scratch / "core"
    (core / "apps" / "pages" / "scripts").mkdir(parents=True)
    (core / "apps" / "pages" / "scripts" / PAGES_SCRIPT.name).write_text(script, "utf-8")
    shutil.copytree(CORE / "packages" / "design", core / "packages" / "design")
    (core / "node_modules").symlink_to(CORE / "node_modules")
    (core / "apps" / "pages" / "node_modules").symlink_to(CORE / "apps" / "pages" / "node_modules")
    (scratch / "no-modules").mkdir()
    out = scratch / "assets"
    done = subprocess.run(  # noqa: S603
        [
            NODE,
            str(core / "apps" / "pages" / "scripts" / PAGES_SCRIPT.name),
            "--out",
            str(out),
            "--modules",
            str(scratch / "no-modules"),
        ],
        cwd=core,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    return done, out


def _plant(script: str, old: str, new: str) -> str:
    assert script.count(old) == 1, (
        f"the build script no longer holds {old!r} exactly once: update this test with the script"
    )
    return script.replace(old, new)


def test_the_pages_build_drops_the_govuk_brand_and_the_plant_that_stops_it_is_red(
    tmp_path: Path,
) -> None:
    """The real script, run in the scratch folder, writes a stylesheet with no GDS Transport and no GOV.UK brand rule (green
    first, so the red below is the plant's). With `withoutGovukBrand` made to keep every rule, the build is refused in words
    by its own second check (a stylesheet that names the face is never written as the Default tree's)."""
    from tests.glass_trees.test_default_tree_carries_no_govuk_assets import (
        real_face_hashes,
        tree_problems,
    )

    faces = real_face_hashes()
    real = PAGES_SCRIPT.read_text("utf-8")
    ok, out = _pages_build(tmp_path / "real", real)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert tree_problems(out, faces) == []
    css = next(p for p in out.iterdir() if p.suffix == ".css").read_text("utf-8")
    assert 'data-brand="govuk"' not in css and "data-govuk-typeface" not in css

    keeps = _plant(real, "return dropGovuk(blankComments(css));", "return css;")
    bad, _ = _pages_build(tmp_path / "keeps", keeps)
    assert bad.returncode != 0, "a build that keeps the GOV.UK brand's rules was accepted"
    assert "GDS Transport" in bad.stderr and "carries" in bad.stderr, bad.stdout + bad.stderr


def test_the_plant_that_stops_the_drop_and_the_check_ships_the_face_and_the_scan_names_it(
    tmp_path: Path,
) -> None:
    """The second line of defence lost too (the shape a regression takes when both are edited together): the stylesheet is
    written with the typeface rule in it, and the Default tree's own scan (`tests/glass_trees/
    test_default_tree_carries_no_govuk_assets.py`) names it, so the proof does not rest on the build's check alone."""
    from tests.glass_trees.test_default_tree_carries_no_govuk_assets import (
        real_face_hashes,
        tree_problems,
    )

    real = PAGES_SCRIPT.read_text("utf-8")
    both = _plant(real, "return dropGovuk(blankComments(css));", "return css;")
    both = _plant(both, "const found = GOVUK_IDENTITY.exec(text);", "const found = null;")
    done, out = _pages_build(tmp_path / "both", both)
    assert done.returncode == 0, done.stdout + done.stderr
    problems = tree_problems(out, real_face_hashes())
    assert any("names GDS Transport" in p for p in problems), problems


def test_the_switch_is_a_field_the_schema_describes() -> None:
    field = AppearanceConfig.model_fields["govuk_identity"]
    assert field.default is False
    assert field.description and field.description.startswith("Default: false.")
