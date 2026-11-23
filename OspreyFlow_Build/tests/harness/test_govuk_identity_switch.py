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

import hashlib
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
    # Written as false, not left out: the sign-in script reads a settings object with no key as one from before the switch
    # existed (the identity as it was), so the harness says "off" in words every time (ADR-152 decision 14, I9).
    assert '"govukIdentity": false' in off[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]


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


def _drawn_by_the_generated_chrome_script(url: str, *, identity: bool) -> dict[str, bool]:
    """Runs the GOV.UK chrome script exactly as the harness writes it for the deployment (its settings line and the script's
    own text, from `render_login_theme`, not a copy) in jsdom at `url`, and reads back what it drew."""
    assert NODE, "node is needed to run the sign-in theme's script"
    theme = render_login_theme(
        TOKENS,
        appearance=AppearanceConfig(brand="govuk", govuk_identity=identity),
        glass_origin=GLASS,
    )
    harness = (
        f"const {{ JSDOM }} = require({json.dumps(str(CORE / 'node_modules' / 'jsdom'))});"
        "const dom = new JSDOM('<!doctype html><html><body><main></main></body></html>',"
        f" {{ url: {json.dumps(url)}, runScripts: 'outside-only' }});"
        "const d = dom.window.document;"
        "d.documentElement.setAttribute('data-brand', 'govuk');"
        f"dom.window.eval({json.dumps(theme[GOVUK_CHROME_SCRIPT])});"
        "console.log(JSON.stringify({"
        "logotype: !!d.querySelector('.govuk-header__logotype'),"
        "crown: !!d.querySelector('.govuk-header__logotype g'),"
        "footer_crown: !!d.querySelector('.govuk-footer__crown'),"
        "crown_copyright: /Crown copyright/.test(d.body.textContent)}));"
    )
    done = subprocess.run(  # noqa: S603
        [NODE, "-e", harness], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    return {k: bool(v) for k, v in json.loads(done.stdout).items()}


def test_the_generated_sign_in_script_draws_none_of_the_identity_with_the_switch_off_on_gov_uk() -> (
    None
):
    """The shape the script meets in a deployment: the settings the harness wrote, at a gov.uk address, switch off.
    Planted: the harness leaving the key out (so the script reads it as one from before the switch) turns this red."""
    assert _drawn_by_the_generated_chrome_script(
        "https://id.service.gov.uk/realms/osprey/", identity=False
    ) == {"logotype": False, "crown": False, "footer_crown": False, "crown_copyright": False}


def test_the_generated_sign_in_script_draws_the_crown_with_the_switch_on_on_gov_uk() -> None:
    assert _drawn_by_the_generated_chrome_script(
        "https://id.service.gov.uk/realms/osprey/", identity=True
    ) == {"logotype": True, "crown": True, "footer_crown": True, "crown_copyright": True}


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


# ----- the image is per deployment as the switch is: round 4's finding. Every deployment built from source tagged its
# workspace image `osprey/workspace:local`, so a switch-on build and a default build shared one tag, and whichever was
# built last was what a start that does not rebuild ran: the default deployment served the face's files, or the GOV.UK
# one fell back to arial in silence.


def _workspace_image(appearance: dict[str, object], **components: object) -> str:
    config = OspreyConfig.model_validate(
        {"components": {"source_path": ".", **components}, "appearance": appearance}
    )
    images = service_images(config, build_context="../../..")
    return str(compose_services(config, images)["workspace"]["image"])


def test_a_default_deployment_and_one_with_the_identity_on_never_share_a_workspace_image_tag() -> (
    None
):
    default = _workspace_image({"brand": "govuk"})
    switched_on = _workspace_image({"brand": "govuk", "govuk_identity": True})
    assert (
        default == "osprey/workspace:local"
    )  # what it was: a default deployment renders byte for byte as before
    assert switched_on != default
    # Every other deployment on the machine that is not GOV.UK with the switch on keeps the default's tag, wherever the
    # switch is written (under the other brand it means nothing: ADR-152 decision 14).
    assert _workspace_image({"brand": "ospreyflow", "govuk_identity": True}) == default
    assert _workspace_image({}) == default


def test_the_other_images_of_a_deployment_with_the_identity_on_keep_their_tags() -> None:
    def tags(appearance: dict[str, object]) -> dict[str, str]:
        config = OspreyConfig.model_validate(
            {"components": {"source_path": "."}, "appearance": appearance}
        )
        images = service_images(config, build_context="../../..")
        return {k: str(v["image"]) for k, v in compose_services(config, images).items()}

    on, off = tags({"brand": "govuk", "govuk_identity": True}), tags({"brand": "govuk"})
    assert {k for k in on if on[k] != off[k]} == {"workspace"}


def test_a_cloud_platform_pushes_the_workspace_with_the_identity_on_under_its_own_tag() -> None:
    """The images a cloud platform's registry holds are named by commit alone: two deployments sharing a registry would
    share `workspace:<commit>` too."""

    def target(**appearance: object) -> str:
        return next(
            str(i["target"])
            for i in _images_plan(**appearance)
            if "/workspace:" in str(i["target"])
        )

    assert target(brand="govuk", govuk_identity=True) != target(brand="govuk")
    assert target(brand="ospreyflow", govuk_identity=True) == target(brand="govuk")


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
    compose = (
        tmp_path / "generated" / "local-lite" / "compose.yaml"
    )  # the default profile's folder, by name
    return code, (yaml.safe_load(compose.read_text("utf-8")) if compose.is_file() else {})


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


CLOUD_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "cloud_platform"


def _resolver(ref: str) -> str:
    """A stand-in digest for each reference, so the render needs no registry (as the cloud platform's own tests give)."""
    return "sha256:" + hashlib.sha256(ref.encode()).hexdigest()


def _images_plan(**appearance: object) -> list[dict[str, object]]:
    """A cloud platform's image plan (`images.yaml`, which `ospreyflow images push` follows), from its own fixture."""

    from harness.render import render

    raw = yaml.safe_load((CLOUD_FIXTURES / "development.yaml").read_text(encoding="utf-8"))
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
    (core / "packages" / "design").mkdir(parents=True)
    for name in (
        "fonts.json",
        "panelType.css",
        "primitives.css",
        "scale.css",
        "tokens.css",
    ):  # the folder, by name
        shutil.copy(CORE / "packages" / "design" / name, core / "packages" / "design" / name)
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


def _stylesheet(out: Path) -> str:
    """The Default tree's built stylesheet, named by the build's own manifest."""
    return (out / json.loads((out / "manifest.json").read_text("utf-8"))["pages.css"]).read_text(
        "utf-8"
    )


def test_the_pages_build_drops_the_govuk_brand_and_the_plant_that_stops_it_is_red(
    tmp_path: Path,
) -> None:
    """The real script, run in the scratch folder, writes a stylesheet with no GDS Transport and no GOV.UK brand rule (green
    first, so the red below is the plant's). With `withoutGovukBrand` made to keep every rule, the build is refused in words
    by its own second check (a stylesheet that names the face is never written as the Default tree's)."""
    real = PAGES_SCRIPT.read_text("utf-8")
    ok, out = _pages_build(tmp_path / "real", real)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    css = _stylesheet(out)
    assert (
        "GDS Transport" not in css
        and 'data-brand="govuk"' not in css
        and "data-govuk-typeface" not in css
    )

    keeps = _plant(real, "return dropGovuk(blankComments(css));", "return css;")
    bad, _ = _pages_build(tmp_path / "keeps", keeps)
    assert bad.returncode != 0, "a build that keeps the GOV.UK brand's rules was accepted"
    assert "GDS Transport" in bad.stderr and "carries" in bad.stderr, bad.stdout + bad.stderr


def test_the_plant_that_stops_the_drop_and_the_check_ships_the_face_in_the_stylesheet(
    tmp_path: Path,
) -> None:
    """The second line of defence lost too (the shape a regression takes when both are edited together): the stylesheet is
    written with the typeface rule in it. That is what `test_default_tree_carries_no_govuk_assets.py`'s scan of the built
    tree reads, so the proof does not rest on the build's check alone (that file plants the same text into its copy)."""
    real = PAGES_SCRIPT.read_text("utf-8")
    both = _plant(real, "return dropGovuk(blankComments(css));", "return css;")
    both = _plant(both, "const found = GOVUK_IDENTITY.exec(text);", "const found = null;")
    done, out = _pages_build(tmp_path / "both", both)
    assert done.returncode == 0, done.stdout + done.stderr
    css = _stylesheet(out)
    assert "GDS Transport" in css and "data-govuk-typeface" in css
    # The scan's own pattern for the face (as `TEXT_SHAPES` there writes it) finds it in this very file.
    assert re.search(r"GDS[ -]?Transport", css, re.I)


def test_the_switch_is_a_field_the_schema_describes() -> None:
    field = AppearanceConfig.model_fields["govuk_identity"]
    assert field.default is False
    assert field.description and field.description.startswith("Default: false.")


# ----- round 8: a missing key means off (the owner's ruling of 23 November 2026), so the renderer must never leave it out

_SETTINGS_PREFIX = "window.OSPREY_GOVUK = "


def _key_written(files: dict[str, str]) -> object:
    """The `govukIdentity` the sign-in script will read, or a marker string when its settings line does not hold the key."""
    first = files[GOVUK_CHROME_SCRIPT].split("\n", 1)[0]
    assert first.startswith(_SETTINGS_PREFIX)
    return json.loads(first.removeprefix(_SETTINGS_PREFIX).rstrip(";")).get("govukIdentity", "<missing>")


_APPEARANCES = [
    {},
    {"govuk_identity": True},
    {"govuk_identity": False},
    {"govuk_identity": True, "phase": "none"},
    {"organisation": "A department", "service_name": "Service", "banner_text": "Words."},
    {"govuk_identity": True, "organisation": "A department", "banner_text": "Words."},
]


@pytest.mark.parametrize("raw", _APPEARANCES, ids=[json.dumps(a) for a in _APPEARANCES])
def test_no_render_path_leaves_the_switch_out_of_the_sign_in_settings(
    raw: dict[str, object], tmp_path: Path
) -> None:
    """The shape the callers pass (`login_theme_options` of a loaded file: apply, refresh and the cluster render all use it),
    through the renderer and through the writer. The key is a real `true` or `false` every time under the GOV.UK brand."""
    from harness.keycloak_theme import login_theme_options, write_login_theme

    config = OspreyConfig.model_validate(
        {"components": {"source_path": "."}, "appearance": {"brand": "govuk", **raw}}
    )
    options = login_theme_options(config)
    expected = bool(raw.get("govuk_identity", False))
    assert _key_written(render_login_theme(TOKENS, **options)) is expected
    write_login_theme(tmp_path, tokens_css=TOKENS, **options)
    on_disk = (tmp_path / "keycloak-theme" / "osprey" / GOVUK_CHROME_SCRIPT).read_text(encoding="utf-8")
    assert _key_written({GOVUK_CHROME_SCRIPT: on_disk}) is expected


def test_the_check_that_the_key_is_written_is_red_for_a_settings_line_without_it() -> None:
    """Rule 15, at the shape the renderer emits: its own first line with the key taken out."""
    files = render_login_theme(
        TOKENS, appearance=AppearanceConfig(brand="govuk", govuk_identity=False), glass_origin=GLASS
    )
    line, _, rest = files[GOVUK_CHROME_SCRIPT].partition("\n")
    settings = json.loads(line.removeprefix(_SETTINGS_PREFIX).rstrip(";"))
    del settings["govukIdentity"]
    stripped = {GOVUK_CHROME_SCRIPT: f"{_SETTINGS_PREFIX}{json.dumps(settings)};\n{rest}"}
    assert _key_written(stripped) == "<missing>"
    assert _key_written(files) is False


def test_the_generated_sign_in_script_draws_none_of_the_identity_with_no_key_on_gov_uk() -> None:
    """The shape a deployment made before this version holds: the settings line without the key, at a gov.uk address.
    Fail closed: no logotype, no crown, no Crown copyright."""
    assert NODE, "node is needed to run the sign-in theme's script"
    files = render_login_theme(
        TOKENS, appearance=AppearanceConfig(brand="govuk", govuk_identity=True), glass_origin=GLASS
    )
    line, _, rest = files[GOVUK_CHROME_SCRIPT].partition("\n")
    settings = json.loads(line.removeprefix(_SETTINGS_PREFIX).rstrip(";"))
    del settings["govukIdentity"]
    old = f"{_SETTINGS_PREFIX}{json.dumps(settings)};\n{rest}"
    harness = (
        f"const {{ JSDOM }} = require({json.dumps(str(CORE / 'node_modules' / 'jsdom'))});"
        "const dom = new JSDOM('<!doctype html><html><body><main></main></body></html>',"
        " { url: 'https://id.service.gov.uk/realms/osprey/', runScripts: 'outside-only' });"
        "const d = dom.window.document;"
        "d.documentElement.setAttribute('data-brand', 'govuk');"
        f"dom.window.eval({json.dumps(old)});"
        "console.log(JSON.stringify({logotype: !!d.querySelector('.govuk-header__logotype'),"
        "crown: !!d.querySelector('circle[cx=\"20\"][cy=\"17.6\"]'),"
        "footer_crown: !!d.querySelector('.govuk-footer__crown'),"
        "crown_copyright: /Crown copyright/.test(d.body.textContent)}));"
    )
    done = subprocess.run(  # noqa: S603
        [NODE, "-e", harness], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "logotype": False,
        "crown": False,
        "footer_crown": False,
        "crown_copyright": False,
    }
