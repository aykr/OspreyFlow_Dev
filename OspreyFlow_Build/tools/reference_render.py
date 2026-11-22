"""The reference render of the deployment shapes (build id PL7, slice PL7a2a; ADR-152 Amendment 1,
decisions 1 and 2, and the owner's ruling of 21 November 2026: the page service in a deployment is a
setting, off by default, and no deployment changes until he turns it on).

This module renders each shape the way the product renders it today, with every input that is not
the configuration pinned, and stores the result byte for byte under
`tests/fixtures/reference_render/<shape>-<brand>/`, beside a `MANIFEST.json` (path, SHA-256, size).
`tests/harness/test_reference_render.py` renders again and compares. A change to a renderer, a
compose service, the front proxy's routes, a Helm value or a setting's default then shows as a
changed file, named, in a diff the owner can read.

It changes no renderer: it calls `harness.render.render` and, for the compose shapes, runs
`harness.apply.stage_deployment` itself (in a temporary folder, with the inputs below fixed), so the
files stored are the files `apply` writes: the compose file, the Caddyfile, `glass.json` (the file
the renderers write for the Glass: there is no `deployment.json`) and `deployment.env`, with the
env lines `stage_deployment` appends for the page service.

**What is pinned, and why.** A render reads things that are not the configuration; each is fixed
here, so the reference holds the same bytes on every machine and every day:

- the digest resolver (a hash of the reference, as `tools.cp_policy_check` does; the registry is
  never asked);
- `harness.render.git_sha` (the commit a build came from: it names the owned images' tags and is in
  `versions.lock`);
- `harness.release.checkout_version` (the version the deployment reports, `dev-<short commit>`);
- the design tokens (`read_tokens`, which the sign-in theme is written from, and which a cluster's
  values carry whole): the tokens' own changes are the design package's business, not a
  deployment's shape.

- the secrets `stage_deployment` mints (`secrets.token_urlsafe`) and the shell variables a render
  reads (`SHELL_INPUTS`, among them `OSPREY_IMAGE_REGISTRY`): the generator returns `PINNED_<n>` in
  turn, and the shell's values are removed for the run. So the stored `deployment.env` holds the
  minted entries as `PINNED_1` onwards (`OSPREY_OIDC_CLIENT_SECRET=PINNED_1` up to
  `MINIO_SECRET_KEY=PINNED_6` for local-lite): placeholders, never a real secret.

No clock is read into the output.

**Regenerate** (a deliberate change to the reference; the diff of `tests/fixtures/reference_render/`
is what the owner reads):

    cd OspreyFlow_Core && PYTHONPATH=../OspreyFlow_Build:packages \\
        uv run python -m tools.reference_render --write

`--check` prints what differs and exits 1; `--write` rewrites the folders (removing a file a shape
no longer writes) and gives the same bytes when run twice.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import itertools
import json
import os
import re
import sys
import tempfile
import unittest.mock as mock
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import yaml

BUILD = Path(__file__).resolve().parents[1]
CORE = BUILD.parent / "OspreyFlow_Core"
REFERENCE = BUILD / "tests" / "fixtures" / "reference_render"
MANIFEST = "MANIFEST.json"
#: The cloud-platform configurations `make cp-policy-check` and the render tests read.
CLOUD_PLATFORM_FIXTURES = BUILD / "tests" / "fixtures" / "cloud_platform"
#: The chart the three Helm shapes (`cluster`, `cloud-platform`, `cloud-platform-poc`) install, and
#: the folder of it stored beside their values: `chart/` in each of their reference folders.
CHART = CORE / "deploy" / "helm" / "ospreyflow"
CHART_PREFIX = "chart/"

#: The two brands the renderers read (`appearance.brand`). `ospreyflow` is the default.
BRANDS = ("ospreyflow", "govuk")

PINNED_SHA = "0123456789abcdef0123456789abcdef01234567"
PINNED_VERSION = "dev-0123456"
PINNED_TOKENS = ":root {\n  --reference-render-token: pinned;\n}\n"
#: What every secret `apply` mints is, in the stored `deployment.env`: `PINNED_` and the number of
#: the minting in that render (an ALL-CAPS word, which the stored-file scan reads as a reference
#: and not a value). Numbered, not one word: `harness.cloud_platform` mints twice and compares, to
#: tell a fixed first value from a fresh password, and one word would make every password fixed.
PINNED_SECRET_PREFIX = "PINNED_"
#: Read by the renderers from the process environment, and so removed for the length of a render:
#: `OSPREY_IMAGE_REGISTRY` names every image the deployment owns (`harness.render._owned`), and
#: `OSPREY_BUILT_FROM_SHA` is what `git_sha` falls back to outside a checkout.
SHELL_INPUTS = ("OSPREY_IMAGE_REGISTRY", "OSPREY_BUILT_FROM_SHA")

#: What the GOV.UK demo's own configuration sets, with synthetic words. The demo is a Lite
#: deployment (a named one, `govuk`, on this Mac at an `http://` address on a `.localhost` name), so
#: `local-lite-govuk` is the shape that stands for it.
GOVUK_APPEARANCE = {
    "brand": "govuk",
    "service_name": "Example Service",
    "organisation": "Example Organisation",
    "phase": "beta",
}

#: The shapes, in the order they are listed and stored. Each is the same configuration the existing
#: render tests use for that shape (`tests/harness/test_render.py`, `test_cluster_render.py`,
#: `test_cloud_platform_render.py`, whose fixtures `tools.cp_policy_check` reads).
SHAPES = ("local-lite", "small", "cluster", "cloud-platform", "cloud-platform-poc")


def _https(origin: str = "https://osprey.example.org") -> dict[str, Any]:
    return {"public_origin": origin}


def raw_config(shape: str) -> dict[str, Any]:
    """The configuration of one shape as plain data, before the brand is put in."""
    if shape == "local-lite":
        # The GOV.UK demo's own address form: plain HTTP on a `.localhost` name and a port.
        origin = "http://reference.ospreyflow.localhost:8081"
        return {"profile": "local-lite", "network": {"public_origin": origin}}
    if shape == "small":
        return {"profile": "small", "network": _https()}
    if shape == "cluster":
        return {
            "profile": "cluster",
            "components": {"analytics_engine": "clickhouse"},
            "network": _https(),
            "reporting": {"sync": True, "superset": True},
            "external": {
                "postgres": {"host": "db.example.internal"},
                "valkey": {"host": "cache.example.internal", "port": 6380, "tls": True},
                "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
                "search": {"url": "https://search-osprey.eu-west-2.es.amazonaws.com"},
            },
            "cluster": {"shared_storage_class": "efs-sc"},
        }
    name = {"cloud-platform": "development", "cloud-platform-poc": "poc"}[shape]
    return yaml.safe_load((CLOUD_PLATFORM_FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))


def config_for(shape: str, brand: str, **settings: Any) -> Any:
    """The `OspreyConfig` of `shape` under `brand`. `settings` are further top-level sections to
    set (a section a later slice adds, say); none is passed by the reference itself, which is the
    point of the "setting absent" case."""
    from schemas.deployment import OspreyConfig

    raw = raw_config(shape)
    if brand == "govuk":
        raw["appearance"] = dict(GOVUK_APPEARANCE)
    elif brand != "ospreyflow":
        raise ValueError(f"unknown brand {brand!r}: one of {BRANDS}")
    raw.update(settings)
    return OspreyConfig.model_validate(raw)


def resolver(reference: str) -> str:
    """A stand-in digest for each image reference: total, stable across runs and machines (not
    Python's `hash`, which differs run to run), and never a registry or a daemon."""
    return "sha256:" + hashlib.sha256(reference.encode()).hexdigest()


@contextlib.contextmanager
def pinned_inputs() -> Iterator[None]:
    """Fixes everything a render reads that is not the configuration (see the module's docstring):
    the commit, the version, the design tokens, the minted secrets, and the shell's variables that
    name images. Patches the functions where the renderers look them up, and the environment, for
    the length of the block; both are as they were after it, and nothing on disk changes."""
    mint = itertools.count(1)
    with (
        mock.patch("harness.render.git_sha", lambda *_a, **_k: PINNED_SHA),
        mock.patch("harness.release.checkout_version", lambda *_a, **_k: PINNED_VERSION),
        mock.patch("harness.cluster.read_tokens", lambda *_a, **_k: PINNED_TOKENS),
        mock.patch("harness.keycloak_theme.read_tokens", lambda *_a, **_k: PINNED_TOKENS),
        # `harness.realm.generate_client_secret` and `harness.reporting` both call this one. A
        # counter, started again for each render: the same sequence on every machine.
        mock.patch(
            "secrets.token_urlsafe", lambda *_a, **_k: f"{PINNED_SECRET_PREFIX}{next(mint)}"
        ),
        mock.patch.dict(os.environ),
    ):
        for name in SHELL_INPUTS:
            os.environ.pop(name, None)
        yield


def render_files(config: Any, *, render_fn: Callable[..., Any] | None = None) -> dict[str, bytes]:
    """Every file the shape writes, keyed by its path in the deployment's folder, as bytes (UTF-8,
    as `harness.render.write` writes them).

    For a compose shape that is what `harness.apply.stage_deployment` leaves in the staging folder,
    run for real with the render's own step (`render_deployment`) given `render_fn` (default
    `harness.render.render`) and the pinned resolver: the artefacts of the render, the realm
    import, the model gateway's routing table, the sign-in theme, and `deployment.env` with every
    line `apply` appends to it (the identity provider's addresses, the stores' hosts, the page
    service's two secrets, the reporting and gateway secrets), each minted value pinned to
    `PINNED_<n>`, numbered by the order the render mints them. `osprey.yaml` (the input, copied)
    and `.rendered` (the list of the files) are not rendered content and are not stored.

    For a Helm shape: `render`'s own artefacts, and the chart's files as they render with the page
    service off (`chart_files`), under `chart/`."""
    from harness.render import render

    from schemas.deployment import Profile

    with pinned_inputs():
        if config.profile in (Profile.LOCAL_LITE, Profile.SMALL):
            return staged_files(config, render_fn or render)
        result = (render_fn or render)(config, resolver=resolver)
        files = {name: text.encode("utf-8") for name, text in result.artefacts.items()}
        files.update(chart_files())
    return dict(sorted(files.items()))


#: What `stage_deployment` leaves that is not rendered content: the input, copied beside the
#: compose file, and the list of the files `harness.render.write` wrote.
_NOT_RENDERED = ("osprey.yaml", ".rendered")


def staged_files(config: Any, render_fn: Callable[..., Any]) -> dict[str, bytes]:
    """`stage_deployment` run into a temporary folder (inside `pinned_inputs`: the caller's block).
    Its render step is the one place the digest resolver is chosen (it asks the daemon and the
    registry, `allow_unpinned`), so that step alone is replaced, by the same render with this
    module's resolver; everything else in `stage_deployment` is the product's own code, and
    `environ` is passed empty, so no provider key, mail password or organisation secret of the
    shell can reach a file."""
    import harness.apply as apply_module

    def render_with_resolver(cfg: Any, out_dir: Path, *, images_from: Path | None) -> Any:
        result = render_fn(cfg, resolver=resolver)
        apply_module.write_artefacts(result, out_dir)
        return result

    with tempfile.TemporaryDirectory(prefix="reference-render-") as scratch:
        root = Path(scratch)
        config_path = root / "osprey.yaml"
        config_path.write_text(f"profile: {config.profile.value}\n", encoding="utf-8")
        stage = root / "deploy" / "generated" / "reference"
        with mock.patch.object(apply_module, "render_deployment", render_with_resolver):
            apply_module.stage_deployment(
                config,
                config_path,
                stage,
                realm="osprey",
                demo_analyst=False,
                images_from=None,
                previous_env="",
                environ={},
            )
        found = read_folder(stage)
    return dict(sorted((n, d) for n, d in found.items() if n not in _NOT_RENDERED))


#: The one guard form the view reads: these two lines, each exactly, each on a line of its own. The
#: setting is `pages.enabled`, the missing entry of the deployment schema (the owner's ruling of 21
#: November 2026, answer 6). Anything else that mentions it is refused, not read.
GUARD_LINE = "{{- if .Values.pages.enabled }}"
END_LINE = "{{- end }}"
_MENTIONS_SETTING = re.compile(r"pages\.enabled")
#: One line of a template that opens a block (`if`, `range`, `with`, `define`, `block`), one that
#: closes it, one that is an `else`; and an action anywhere in a line that does any of these, to
#: tell a line whose block count cannot be trusted (an action that is not the whole of its line).
_BLOCK_OPEN = re.compile(r"^\s*\{\{-?\s*(?:if|range|with|define|block)\b")
_BLOCK_END = re.compile(r"^\s*\{\{-?\s*end\s*-?\}\}\s*$")
_BLOCK_ELSE = re.compile(r"^\s*\{\{-?\s*else\b")
_BLOCK_ACTION = re.compile(r"\{\{-?\s*(?:if|range|with|define|block|end|else)\b")


class UnsupportedGuard(ValueError):
    """A template mentions `pages.enabled` in a form the view does not read. No view is built: the
    message names the file and the line, so the render fails (the invariant case, `--write`,
    `--check`) instead of storing a text whose off render may not be what it is taken for."""

    def __init__(self, path: str, line: int, why: str) -> None:
        super().__init__(f"{path}:{line}: {why}")


def _is(line: str, wanted: str) -> bool:
    return line.removesuffix("\n") == wanted


def _guarded_block_end(lines: list[str], start: int, path: str) -> int:
    """The index of the line that closes the guard opened at `start`. Raises `UnsupportedGuard`
    when the block is not closed by the exact end line, holds an `else` of the guard's own, holds
    another mention of the setting (a nested guard included), or holds an action that opens or
    closes a block that is not the whole of its line (the count cannot be told)."""
    depth = 1
    for index in range(start + 1, len(lines)):
        line = lines[index]
        number = index + 1
        if _MENTIONS_SETTING.search(line):
            raise UnsupportedGuard(path, number, "a second mention of pages.enabled inside a guard")
        if len(_BLOCK_ACTION.findall(line)) > 1:
            raise UnsupportedGuard(path, number, "more than one block action on a line")
        if _BLOCK_OPEN.match(line):
            depth += 1
        elif _BLOCK_END.match(line):
            depth -= 1
            if depth == 0:
                if not _is(line, END_LINE):
                    raise UnsupportedGuard(
                        path, number, f"the guard's end is not exactly the line {END_LINE!r}"
                    )
                return index
        elif _BLOCK_ELSE.match(line):
            if depth == 1:
                raise UnsupportedGuard(path, number, "an else in a guard")
        elif _BLOCK_ACTION.search(line):
            raise UnsupportedGuard(path, number, "a block action that is not the whole of its line")
    raise UnsupportedGuard(path, start + 1, "the guard is not closed")


def without_pages_guard(text: str, path: str = "template") -> str:
    """A template as it renders with `pages.enabled` off: every block opened by the line
    `{{- if .Values.pages.enabled }}` and closed by the line `{{- end }}`, each on a line of its
    own, removed. Not a Helm renderer: it reads that one form and fails closed on the rest.

    Any other line that mentions `pages.enabled` (a trailing `-}}`, no leading dash, an indent, an
    inline guard, a close that is `{{ end }}` or `{{- end -}}`, an `else`, a second guard inside the
    first, a block never closed, a setting read as a value, a comment) raises `UnsupportedGuard`
    naming `path` and the line. Helm's trim markers apply whether or not an `if` is taken, so those
    forms' off render is not the text without the block, and this does not model them: it refuses.
    The whitespace around the accepted form is not modelled either; write the guard after a line of
    content. `if .Values.pages` does not mention the setting and is left as text, so it shows as a
    change."""
    lines = text.splitlines(keepends=True)
    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if _is(line, GUARD_LINE):
            index = _guarded_block_end(lines, index, path) + 1
            continue
        if _MENTIONS_SETTING.search(line):
            raise UnsupportedGuard(
                path,
                index + 1,
                f"pages.enabled in a form the view does not read (only the line {GUARD_LINE!r}, "
                f"closed by the line {END_LINE!r}, each on a line of its own, is read)",
            )
        kept.append(line)
        index += 1
    return "".join(kept)


_PAGES_KEY = re.compile(r"^pages:[ \t]*(?:#.*)?$")
_ENABLED_OFF = re.compile(r"^([ \t]+)enabled:[ \t]*false[ \t]*(?:#.*)?$")


def _section_is_off(body: list[str]) -> bool:
    """Whether a section's own `enabled` key, at the section's first indentation level, is false.
    A key nested deeper (`ingress: enabled: false`) is a sub-toggle and says nothing of the
    section: a section that is on, with a sub-toggle off, is on."""
    own = next(
        (
            line[: len(line) - len(line.lstrip(" \t"))]
            for line in body
            if line.strip() and not line.lstrip().startswith("#")
        ),
        None,
    )
    if own is None:
        return False
    for line in body:
        found = _ENABLED_OFF.match(line.rstrip("\r\n"))
        if found and found.group(1) == own:
            return True
    return False


def without_pages_section_when_off(text: str) -> str:
    """The chart's default `values.yaml` as it reads with the page service off: a top-level
    `pages:` section whose own first-level `enabled` key is false (not a key nested in it), with
    the comment lines directly above it and one blank line above those, is not there. A `pages:`
    section that is on, or does not say, stays."""
    lines = text.splitlines(keepends=True)
    for start, line in enumerate(lines):
        if not _PAGES_KEY.match(line.rstrip("\r\n")):
            continue
        end = start + 1
        while end < len(lines) and (not lines[end].strip() or lines[end][0] in " \t"):
            end += 1
        # Blank lines at the end of the section belong to what follows it.
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        if not _section_is_off(lines[start + 1 : end]):
            return text
        first = start
        while first > 0 and lines[first - 1].lstrip().startswith("#"):
            first -= 1
        if first > 0 and not lines[first - 1].strip():
            first -= 1
        return "".join(lines[:first] + lines[end:])
    return text


def chart_off_view(path: str, data: bytes) -> bytes | None:
    """One chart file as it is with the page service off, or None where it is not a file at all
    (a template that renders nothing: Helm writes no manifest for it)."""
    text = data.decode("utf-8")
    if path.startswith("templates/"):
        text = without_pages_guard(text, f"{CHART_PREFIX}{path}")
        return text.encode("utf-8") if text.strip() else None
    if path == "values.yaml":
        return without_pages_section_when_off(text).encode("utf-8")
    return data


def chart_files() -> dict[str, bytes]:
    """The chart's files, as bytes, keyed `chart/<path in the chart>`, as the chart is with the page
    service off (`chart_off_view`). Not `helm template` output: that needs the `helm` binary, which
    a pure test does not assume (`make chart-check` and `make cp-policy-check` template the chart).
    They are the sources `helm template` renders from, so a template that changes (a workload, an
    Ingress path, a NetworkPolicy) changes the file stored here and the manifest's hash of it; a
    block under `pages.enabled` is not part of what is stored, so adding one is not a change while
    the setting is off. Read by a plain recursion over the one chart folder."""
    files = {}
    for path, data in read_folder(CHART).items():
        viewed = chart_off_view(path, data)
        if viewed is not None:
            files[f"{CHART_PREFIX}{path}"] = viewed
    return files


def render_shape(shape: str, brand: str, **settings: Any) -> dict[str, bytes]:
    """The shape under the brand, rendered with the settings as the reference sets them."""
    return render_files(config_for(shape, brand, **settings))


def folder_name(shape: str, brand: str) -> str:
    return f"{shape}-{brand}"


def all_folders() -> list[tuple[str, str]]:
    return [(shape, brand) for shape in SHAPES for brand in BRANDS]


# ---- the manifest ---------------------------------------------------------------------------


def manifest_of(files: dict[str, bytes]) -> dict[str, Any]:
    """`MANIFEST.json`'s content: path, SHA-256 and size of each file, sorted by path."""
    return {
        "files": [
            {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            for name, data in sorted(files.items())
        ]
    }


def manifest_bytes(files: dict[str, bytes]) -> bytes:
    return (json.dumps(manifest_of(files), indent=2, sort_keys=True) + "\n").encode("utf-8")


def first_difference(shape_folder: str, name: str, expected: bytes, actual: bytes) -> str:
    """A message naming the shape, the file and the first line that differs (1-based), with both
    sides' text, for a failing comparison."""
    old = expected.decode("utf-8", "replace").splitlines()
    new = actual.decode("utf-8", "replace").splitlines()
    for number, (a, b) in enumerate(zip(old, new, strict=False), start=1):
        if a != b:
            return (
                f"{shape_folder}/{name}: first differing line is {number}\n"
                f"  reference: {a!r}\n  rendered:  {b!r}"
            )
    if len(old) != len(new):
        number = min(len(old), len(new)) + 1
        longer = "rendered" if len(new) > len(old) else "reference"
        extra = (new if len(new) > len(old) else old)[number - 1]
        return (
            f"{shape_folder}/{name}: first differing line is {number} "
            f"(the {longer} text goes on: {extra!r})"
        )
    return (
        f"{shape_folder}/{name}: the text is the same line for line, but the bytes differ "
        "(line endings, a trailing newline or an encoding)"
    )


def read_folder(folder: Path) -> dict[str, bytes]:
    """The files of a stored reference folder, by path relative to it, `MANIFEST.json` apart. A
    plain recursion over one known folder, not a search of the tree."""
    found: dict[str, bytes] = {}

    def visit(directory: Path) -> None:
        for entry in sorted(directory.iterdir()):
            if entry.is_dir():
                visit(entry)
            elif entry.name != MANIFEST:
                found[entry.relative_to(folder).as_posix()] = entry.read_bytes()

    if folder.is_dir():
        visit(folder)
    return found


def stored_folders(reference: Path = REFERENCE) -> list[str]:
    return sorted(p.name for p in reference.iterdir() if p.is_dir()) if reference.is_dir() else []


def differences(
    shape: str, brand: str, rendered: dict[str, bytes], reference: Path = REFERENCE
) -> list[str]:
    """What differs between a render and the stored folder: a file added, a file dropped, a file
    changed (naming its first differing line), the manifest out of step with the files."""
    name = folder_name(shape, brand)
    stored = read_folder(reference / name)
    out = [
        f"{name}/{path}: rendered, and not in the reference"
        for path in rendered.keys() - stored.keys()
    ]
    out += [
        f"{name}/{path}: in the reference, and no longer rendered"
        for path in stored.keys() - rendered.keys()
    ]
    out += [
        first_difference(name, path, stored[path], rendered[path])
        for path in sorted(stored.keys() & rendered.keys())
        if stored[path] != rendered[path]
    ]
    manifest = reference / name / MANIFEST
    if not manifest.is_file():
        out.append(f"{name}/{MANIFEST}: missing")
    elif manifest.read_bytes() != manifest_bytes(stored):
        out.append(f"{name}/{MANIFEST}: does not describe the files stored beside it")
    return sorted(out)


def write_reference(reference: Path = REFERENCE) -> list[str]:
    """Rewrites every folder from a fresh render: files written byte for byte, the manifest beside
    them, a file a shape no longer writes removed, a folder no shape names removed. Returns the
    paths written. Running it twice leaves the same bytes."""
    written: list[str] = []
    wanted = {folder_name(shape, brand) for shape, brand in all_folders()}
    # Every shape is rendered before anything is touched: a render that raises (an
    # `UnsupportedGuard`) leaves the reference as it was.
    rendered = {(shape, brand): render_shape(shape, brand) for shape, brand in all_folders()}
    for stale in set(stored_folders(reference)) - wanted:
        _remove(reference / stale)
    for (shape, brand), files in rendered.items():
        folder = reference / folder_name(shape, brand)
        for path in set(read_folder(folder)) - files.keys():
            (folder / path).unlink()
        for path, data in files.items():
            target = folder / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(f"{folder.name}/{path}")
        (folder / MANIFEST).write_bytes(manifest_bytes(files))
        _prune_empty(folder)
    return written


def _remove(folder: Path) -> None:
    for entry in folder.iterdir():
        _remove(entry) if entry.is_dir() else entry.unlink()
    folder.rmdir()


def _prune_empty(folder: Path) -> None:
    for entry in sorted(folder.iterdir()):
        if entry.is_dir():
            _prune_empty(entry)
            if not any(entry.iterdir()):
                entry.rmdir()


# ---- what a stored file must not hold -------------------------------------------------------

#: A string shaped like a credential, in the shapes the renderers could emit one: a provider key, a
#: bearer token, a private key block, a cloud access key, and a secret-named setting given a literal
#: value (a reference to a variable by `${...}` or by its ALL-CAPS name, `''`, a Terraform
#: `random_password`, or this module's `PINNED_<n>` is the right shape; a name ending `_ID` is an
#: identifier, not a secret).
_SECRET_SHAPES = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(
        r"(?im)\b[A-Z_]*(?:PASSWORD|SECRET|TOKEN)[A-Z_]*(?<!_ID)\s*[:=]\s*['\"]?"
        r"(?![$'\"\s]|random_password|OSPREY_|http|true|false)"
        r"(?!(?-i:[A-Z][A-Z0-9_]*['\"]?[ \t]*$))"
        r"(?!(?-i:(?:sk-)?PINNED_\d+['\"]?[ \t]*$))"
        r"[A-Za-z0-9+/_=-]{8,}['\"]?[ \t]*$"
    ),
)
#: The one address-shaped string the product's own sign-in script carries as a placeholder.
_PLACEHOLDER_ADDRESSES = ("name@organisation.gov.uk",)
_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL_HOST = re.compile(r"\bhttps?://([A-Za-z0-9.-]+)")
#: A host written bare, as the renderers write the database, cache, search and object-store hosts
#: and an image registry: a dotted name whose last label is a top-level domain a real host could
#: end in (the file extensions that are also domains, `.sh`, `.py`, `.md` and `.zip`, are left out).
_BARE_HOST = re.compile(
    r"(?<![\w.-])((?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"
    r"(?:com|org|net|uk|io|gov|edu|int|eu|co|dev|app|cloud|info|biz|us|ie|de|fr|nl|ca|au|in|ai"
    r"|tech|online|site|xyz|local|internal|localhost))(?![\w-])(?!\.\w)",
    re.IGNORECASE,
)
#: A host in the place a setting names one, whatever its top-level domain: a key that says `host`,
#: `endpoint`, `registry`, `server`, `domain`, `origin`, `address` or `url`, given a dotted value.
_KEYED_HOST = re.compile(
    r"(?im)\b[\w.-]*(?:host|endpoint|registry|server|domain|origin|address|url)[\w-]*"
    r"\s*[:=]\s*['\"]?([A-Za-z][A-Za-z0-9+.-]*://)?([A-Za-z0-9][A-Za-z0-9.-]*)(?![A-Za-z0-9.(_-])"
)
#: The hosts a stored file may name: this reference's own synthetic ones (`example.org` and
#: `example.internal`, which are reserved or ours, and `.localhost`), and the public hosts of the
#: software and standards the renderers name (a registry, a cloud's API, a model provider). A host
#: is allowed when it is one of these or a subdomain of one: `evilghcr.io` is neither.
SYNTHETIC_HOST_SUFFIXES = ("example.org", "example.internal", "localhost")
PUBLIC_HOST_SUFFIXES = (
    "amazonaws.com", "ghcr.io", "quay.io", "docker.io", "gov.uk", "w3.org", "kubernetes.io",
    "k8s.io", "projectcalico.org", "login.microsoftonline.com", "api.anthropic.com",
    "api.openai.com", "googleapis.com", "github.com", "svc.cluster.local", "ospreyflow.io",
)  # fmt: skip
_SYNTHETIC_ACCOUNT = "123456789012"


def host_allowed(host: str) -> bool:
    """Whether a stored file may name `host`: a service on the internal network (no dot), the
    loopback address, a synthetic host or a public software or standards host, or a subdomain of
    one of those."""
    if "." not in host or host == "127.0.0.1":
        return True
    if re.fullmatch(r"[0-9.]+", host) or re.fullmatch(r"[\w-]+-\d+\.[\w-]+-headless", host):
        return True  # a version number; a pod's name under its StatefulSet's headless service
    return any(
        host == s or host.endswith("." + s) for s in SYNTHETIC_HOST_SUFFIXES + PUBLIC_HOST_SUFFIXES
    )


def stored_text_findings(files: dict[str, bytes]) -> list[str]:
    """What in `files` is a credential-shaped string, an address that is not the product's
    placeholder, a host that is neither synthetic nor a public software or standards host, or a
    cloud account other than the synthetic one. Empty when the reference is clean."""
    found: list[str] = []
    for path, data in sorted(files.items()):
        text = data.decode("utf-8")
        for shape in _SECRET_SHAPES:
            found += [
                f"{path}: credential-shaped {m.group(0)[:40]!r}" for m in shape.finditer(text)
            ]
        for m in _ADDRESS.finditer(text):
            if m.group(0) not in _PLACEHOLDER_ADDRESSES and not m.group(0).endswith("sha256"):
                found.append(f"{path}: address {m.group(0)!r}")
        hosts = [m.group(1) for m in _URL_HOST.finditer(text)]
        hosts += [m.group(1) for m in _BARE_HOST.finditer(text)]
        hosts += [m.group(2) for m in _KEYED_HOST.finditer(text) if "." in m.group(2)]
        for host in sorted({h.rstrip(".").lower() for h in hosts}):
            if not host_allowed(host):
                found.append(f"{path}: host {host!r}")
        for m in re.finditer(r"\b(\d{12})\.dkr\.ecr\.", text):
            if m.group(1) != _SYNTHETIC_ACCOUNT:
                found.append(f"{path}: cloud account {m.group(1)!r}")
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tools.reference_render", description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="rewrite the reference from a render")
    mode.add_argument("--check", action="store_true", help="list what differs; exit 1 if any")
    parser.add_argument(
        "--reference",
        type=Path,
        default=REFERENCE,
        help="the folder to write or compare (default: tests/fixtures/reference_render)",
    )
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except UnsupportedGuard as refused:
        print(f"reference_render: refused, {refused}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.write:
        written = write_reference(args.reference)
        print(f"reference_render: wrote {len(written)} files under {args.reference}")
        return 0
    found = [
        line
        for shape, brand in all_folders()
        for line in differences(shape, brand, render_shape(shape, brand), args.reference)
    ]
    for line in found:
        print(line)
    print(f"reference_render: {len(found)} difference(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
