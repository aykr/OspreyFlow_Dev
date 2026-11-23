"""Refresh adds a plain `deployment.env` line the render writes and a deployment lacks (build id
PL14, slice PL14a; the owner's request and three answers of 23 November 2026, D216; v0.6.2 only).

**The fault.** `scripts/refresh.py` (`ospreyflow start --build`) never rewrote `deployment.env`
beyond the model lines and three more, but its last step rebuilds the search index. A
deployment whose `deployment.env` lacked a plain line the checkout's render writes kept lacking
it: a test user's, made before 13 November, had no `OPENSEARCH_HOST`, so the client fell back
to `localhost:9200`.

**The three answers, and the test of each.**

1. *The boundary.* Refresh takes plain lines only from what `harness.render._render_env` emits and
   never decides by a key's name that one is plain. **The boundary test fails closed**: red if a key
   `_render_env` emits matches the secret name test (`_SECRET_KEY`, `harness/apply.py`) or is not on
   the reviewed list (`tests/fixtures/refresh_plain_lines_reviewed.txt`, which only a human who has
   judged the key plain may add to). A new render line therefore forces a human decision.
   `test_the_render_emits_nothing_secret_or_unreviewed` and the three plants beside it.
2. *The lines `apply` appends* (the identity provider's addresses, the stores' hosts and ports) are
   not touched: `test_what_apply_appended_and_the_operator_added_stays`.
3. *Add, never change.* A missing render line is added, as the render writes it, in the render's
   order; a line that is there keeps its value, and refresh names the key (never the value) and says
   to run `ospreyflow apply`. A secret is never written, changed or removed, and a line the render
   does not emit stays. `OSPREY_RELEASE_VERSION` is a deployment's own release and is never named.

**How the "as v0.6.1 renders it" file is made.** No v0.5.1 file is stored (the owner ruled none).
Each case takes this checkout's own render of a configuration (`render(config).artefacts`), adds
what `harness.apply` adds (plain lines, held secrets, a line an operator added), and removes one
chosen line of the render: the file a render without that line would have left. No release's own
render is claimed.

**What the cases catch (rule 12).**
- a missing line never added, or added elsewhere or differently from the render —
  `test_a_line_the_render_writes_comes_back_exactly_as_the_render_writes_it` (every key of the
  default render) and `test_a_line_the_render_writes_only_under_a_setting_is_added_only_where_
  osprey_yaml_renders_it`;
- an operator's edit overwritten, or the value said aloud, or the release version named —
  `test_a_line_the_operator_edited_keeps_its_edit_and_its_key_is_named`,
  `test_the_release_version_is_never_named_as_differing`;
- a secret changed, written, or named —
  `test_a_secret_line_is_never_changed_or_written_whatever_the_render_says`;
- the render's boundary silently widened — the boundary tests and their plants (rule 15: each is
  patched into `_render_env`'s output, never into the render, and each is shown red);
- a file half written by a run that dies — `test_a_refresh_that_refuses_changes_nothing`;
- the failure of the search rebuild sending the operator to the wrong command —
  `test_the_rebuild_with_no_opensearch_address_says_to_run_apply`.

**Folders this file walks.** None. It reads one file by name,
`tests/fixtures/refresh_plain_lines_reviewed.txt`, and the source text of five render functions
(`inspect.getsource`); its other files are its own temporary folders. It imports nothing from
another test file, so the scan map needs no row for it.
"""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import yaml
from harness import laurium, reporting
from harness import render as render_module
from harness.apply import _SECRET_KEY
from harness.keycloak_theme import write_login_theme
from harness.render import render, render_litellm_config
from scripts import refresh
from tools import reference_render as ref

from schemas.deployment import OspreyConfig, generated_folder

REVIEWED_FILE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "refresh_plain_lines_reviewed.txt"
)
TOKENS = ":root { --brass: #c08a34; }\n"

#: Plain lines `harness.apply` appends to the render's file (out of scope: refresh never touches
#: them).
APPENDED = (
    "OIDC_JWKS_URL=http://keycloak:8080/realms/osprey/protocol/openid-connect/certs\n"
    "OIDC_TOKEN_EXCHANGE_URL=http://keycloak:8080/realms/osprey/protocol/openid-connect/token\n"
    "ARCADEDB_HOST=arcadedb\n"
    "VALKEY_HOST=valkey\n"
    "POSTGRES_HOST=postgres\n"
    "POSTGRES_PORT=5432\n"
)
#: Secrets `apply` mints, as an applied deployment holds them.
HELD_SECRETS = (
    "OSPREY_POSTGRES_PASSWORD=held-pg-secret-77\n"
    "OSPREY_LITELLM_MASTER_SECRET=held-master-secret-77\n"
    "MINIO_SECRET_KEY=held-store-secret-77\n"
)
OPERATOR_LINE = "MY_OWN_SETTING=operator-added-77\n"


class Recorder:
    """The compose commands a refresh would run, recorded; one is refused when `fail_on` is in it.
    Nothing reaches Docker. (Kept here, not imported from `tests/test_refresh.py`, which walks its
    own temporary folder: importing it would make this file one the scan map must list.)"""

    def __init__(self, fail_on: str | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv: Sequence[str]) -> None:
        self.calls.append(list(argv))
        if self.fail_on and self.fail_on in argv:
            raise refresh.RefreshFailed(" ".join(argv))


class Registrar:
    def __call__(self, argv: list[str]) -> int:
        return 0


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A product folder with one rendered deployment that holds a held secret, a current theme and
    an empty compose file."""
    out = tmp_path / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    (out / "deployment.env").write_text("OSPREY_POSTGRES_PASSWORD=pg-secret-77\n", encoding="utf-8")
    (out / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    tokens = tmp_path / "packages" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(TOKENS, encoding="utf-8")
    write_login_theme(out, tokens_css=TOKENS)
    return tmp_path


def _keys(env_text: str) -> list[str]:
    """The keys of the `KEY=value` lines of an env file's text, in order (no comments or blanks)."""
    found = []
    for line in env_text.splitlines():
        key, sep, _ = line.partition("=")
        if sep and not line.startswith("#") and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            found.append(key)
    return found


def _line(text: str, key: str) -> str:
    """The one line of `text` that sets `key`, with its newline."""
    (found,) = [line for line in text.splitlines(keepends=True) if line.startswith(f"{key}=")]
    return found


def _without(text: str, key: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if not line.startswith(f"{key}=")
    )


@pytest.fixture(autouse=True)
def _pinned(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The commit, the version and the shell's image names fixed, as the reference render does."""
    monkeypatch.delenv(refresh.DEPLOYMENT_DIR_VARIABLE, raising=False)
    with ref.pinned_inputs():
        yield


def _default_keys() -> list[str]:
    with ref.pinned_inputs():
        return _keys(render_module._render_env(OspreyConfig()))


DEFAULT_KEYS = _default_keys()


@dataclass
class Made:
    repo: Path
    out: Path
    full: str  # the file as a render of this checkout, plus what apply adds, would leave it
    before: str  # `full` with the chosen lines removed or edited: what the deployment holds
    config: OspreyConfig

    @property
    def env(self) -> Path:
        return self.out / "deployment.env"

    def after(self) -> str:
        return self.env.read_text(encoding="utf-8")


def _make(
    tmp_path: Path,
    *,
    settings: dict[str, Any] | None = None,
    yaml_settings: dict[str, Any] | None = None,
    drop: tuple[str, ...] = (),
    edit: dict[str, str] | None = None,
    own: str = "",
    with_osprey_yaml: bool = True,
) -> Made:
    """A rendered deployment under `tmp_path` whose `deployment.env` is this checkout's render of
    `settings`, with what `apply` adds, minus the lines in `drop`, with `edit`'s values put in
    (`own`: a line the file holds as well). Its `osprey.yaml` is `yaml_settings`' (the same by
    default): a deployment whose settings moved after its render."""
    config = OspreyConfig.model_validate(settings or {})
    artefacts = render(config, allow_unpinned=True).artefacts
    out = tmp_path / "deploy" / "generated" / generated_folder(config)
    out.mkdir(parents=True)
    compose = artefacts["compose.yaml"]
    # Every secret the compose file requires, held as an applied deployment holds them (the render
    # alone writes none): refresh refuses a compose file Compose could not interpolate.
    rendered = artefacts["deployment.env"]
    named = set(_keys(rendered + APPENDED + HELD_SECRETS + OPERATOR_LINE))
    required = sorted(set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?", compose)) - named)
    held = "".join(f"{n}=held-{n.lower()}\n" for n in required)
    full = rendered + APPENDED + HELD_SECRETS + held + OPERATOR_LINE
    before = full
    for key in drop:
        before = _without(before, key)
    for key, value in (edit or {}).items():
        before = before.replace(_line(before, key), f"{key}={value}\n")
    before += own
    (out / "compose.yaml").write_text(compose, encoding="utf-8")
    (out / "deployment.env").write_text(before, encoding="utf-8")
    (out / "deployment.env").chmod(0o600)
    (out / "litellm.yaml").write_text(render_litellm_config(config), encoding="utf-8")
    (out / "Caddyfile").write_text(artefacts["Caddyfile"], encoding="utf-8")
    if with_osprey_yaml:
        wanted = OspreyConfig.model_validate(yaml_settings) if yaml_settings is not None else config
        (out / "osprey.yaml").write_text(
            yaml.safe_dump(wanted.model_dump(mode="json"), sort_keys=False), encoding="utf-8"
        )
    tokens = tmp_path / "packages" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(TOKENS, encoding="utf-8")
    write_login_theme(out, tokens_css=TOKENS)
    return Made(tmp_path, out, full, before, config)


def _planted(line: str, after: str | None = None) -> Any:
    """`_render_env` with one more line in its output, after the line that starts `after` (the end
    if none): the shape the render writes, patched in place, never edited."""
    real = render_module._render_env

    def with_the_line(config: OspreyConfig) -> str:
        text = real(config)
        if after is None:
            return text + line + "\n"
        return "".join(
            chunk + (line + "\n" if chunk.startswith(after) else "")
            for chunk in text.splitlines(keepends=True)
        )

    return mock.patch.object(render_module, "_render_env", with_the_line)


# ---- the lines come back -------------------------------------------------------------------------


@pytest.mark.parametrize("key", DEFAULT_KEYS)
def test_a_line_the_render_writes_comes_back_exactly_as_the_render_writes_it(
    tmp_path: Path, key: str
) -> None:
    """Each line of the default render removed in turn (`OPENSEARCH_HOST` among them): refresh puts
    it back as the render writes it, and every other line is as it was, byte for byte."""
    made = _make(tmp_path, drop=(key,))
    assert key not in _keys(made.before)
    refresh.files_up_to_date(made.repo)
    after = made.after()
    wanted = _line(made.full, key)
    assert after.splitlines(keepends=True).count(wanted) == 1, (
        f"{key} not put back as the render writes it"
    )
    # Every other line, in order and byte for byte.
    assert _without(after, key) == _without(made.full, key)
    assert after == made.full  # in the render's own place, comments and all


def test_a_deployment_that_lacks_nothing_is_not_rewritten(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = _make(tmp_path)
    before = made.env.read_bytes()
    refresh.files_up_to_date(made.repo)
    assert made.env.read_bytes() == before
    assert "ospreyflow apply" not in capsys.readouterr().out


def test_several_missing_lines_come_back_in_the_renders_order(tmp_path: Path) -> None:
    drop = (
        "OPENSEARCH_HOST",
        "OPENSEARCH_PORT",
        "OSPREY_SEARCH_INDEX_ALIAS",
        "OSPREY_HIGHEST_MARKING",
    )
    made = _make(tmp_path, drop=drop)
    refresh.files_up_to_date(made.repo)
    assert made.after() == made.full


_CLICKHOUSE = {"components": {"analytics_engine": "clickhouse"}}
_NO_OPENSEARCH = {"components": {"search": "postgres-fulltext"}}


@pytest.mark.parametrize(
    ("settings", "yaml_settings", "key", "comes_back"),
    [
        # The render writes it for this osprey.yaml: it comes back.
        (_CLICKHOUSE, None, "CLICKHOUSE_HOST", True),
        (_CLICKHOUSE, None, "CLICKHOUSE_HTTP_PORT", True),
        (_CLICKHOUSE, None, "CLICKHOUSE_USER", True),
        (None, None, "OPENSEARCH_HOST", True),
        (None, None, "OPENSEARCH_PORT", True),
        (None, None, "OSPREY_SEARCH_INDEX_ALIAS", True),
        # The file was rendered under a setting its osprey.yaml no longer has: not added.
        (_CLICKHOUSE, {}, "CLICKHOUSE_HOST", False),
        (_CLICKHOUSE, {}, "CLICKHOUSE_USER", False),
        (None, _NO_OPENSEARCH, "OPENSEARCH_HOST", False),
        (None, _NO_OPENSEARCH, "OSPREY_SEARCH_INDEX_ALIAS", False),
    ],
)
def test_a_line_the_render_writes_only_under_a_setting_is_added_only_where_osprey_yaml_renders_it(
    tmp_path: Path,
    settings: dict[str, Any] | None,
    yaml_settings: dict[str, Any] | None,
    key: str,
    comes_back: bool,
) -> None:
    made = _make(tmp_path, settings=settings, yaml_settings=yaml_settings, drop=(key,))
    refresh.files_up_to_date(made.repo)
    assert (key in _keys(made.after())) is comes_back
    if comes_back:
        assert made.after() == made.full
    else:
        assert made.after() == made.before  # nothing else moved either


def test_a_deployment_with_no_osprey_yaml_beside_it_is_left_alone(tmp_path: Path) -> None:
    made = _make(tmp_path, drop=("OPENSEARCH_HOST",), with_osprey_yaml=False)
    refresh.files_up_to_date(made.repo)
    assert "OPENSEARCH_HOST" not in _keys(made.after())


# ---- a line that is there is never changed -------------------------------------------------------


def test_a_line_the_operator_edited_keeps_its_edit_and_its_key_is_named(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edited = {
        "OSPREY_HOTLIST_AUDIENCE": "edited-by-the-operator-77",
        "CORS_ALLOWED_ORIGINS": "http://mine-77",
    }
    made = _make(tmp_path, drop=("OPENSEARCH_HOST",), edit=edited)
    refresh.files_up_to_date(made.repo)
    after = made.after()
    for key, value in edited.items():
        assert f"{key}={value}\n" in after, f"{key} was changed"
    assert "OPENSEARCH_HOST=opensearch\n" in after  # the missing one is still added
    said = capsys.readouterr().out
    assert "OSPREY_HOTLIST_AUDIENCE" in said and "CORS_ALLOWED_ORIGINS" in said
    assert "ospreyflow apply" in said
    for value in edited.values():
        assert value not in said, "a value was said aloud"
    assert "opensearch" not in said.lower().replace("ospreyflow", ""), (
        "a line only added is not 'differing'"
    )
    # Only what differs is named.
    assert "OSPREY_PROFILE" not in said and "OSPREY_GRAPH_STORE" not in said
    # Nothing else moved.
    for key in _keys(made.full):
        if key not in edited and key != "OPENSEARCH_HOST":
            assert _line(after, key) == _line(made.full, key)


def test_the_files_only_run_update_reads_still_ends_in_its_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`update` reads the last line of this run's output as JSON, stdout then stderr: the words come
    before it, on stdout, and nothing is written to stderr after."""
    made = _make(tmp_path, edit={"OSPREY_HOTLIST_AUDIENCE": "edited-by-the-operator-77"})
    assert refresh.main(["--files-only"], repo_root=made.repo) == 0
    seen = capsys.readouterr()
    assert seen.err == ""
    lines = seen.out.strip().splitlines()
    assert set(json.loads(lines[-1])) == {"proxy_changed", "theme_changed", "routing_changed"}
    assert any("OSPREY_HOTLIST_AUDIENCE" in line for line in lines[:-1])


def test_the_release_version_is_never_named_as_differing(tmp_path: Path) -> None:
    """A deployment's release is the one it was rendered with (`harness.fresh_only`; `apply` keeps
    it). The helper that names the differing keys is asked directly: the other steps of a refresh
    move this one line, so a whole run could not show the exclusion at work."""
    made = _make(tmp_path)
    text = made.before.replace(
        _line(made.before, "OSPREY_RELEASE_VERSION"), "OSPREY_RELEASE_VERSION=v0.0.1-mine\n"
    )
    made.env.write_text(text, encoding="utf-8")
    assert refresh._plain_lines_differing(made.out) == []
    # ...and the helper does name a key that differs, so an empty answer above is not a helper that
    # names nothing.
    made.env.write_text(
        text.replace("OSPREY_GRAPH_STORE=arcadedb", "OSPREY_GRAPH_STORE=mine"), encoding="utf-8"
    )
    assert refresh._plain_lines_differing(made.out) == ["OSPREY_GRAPH_STORE"]


def test_what_apply_appended_and_the_operator_added_stays(tmp_path: Path) -> None:
    """Answer 2: the lines `apply` appends are not touched (the remaining gap, named in the report);
    a line the render does not emit is never removed or changed."""
    made = _make(tmp_path, drop=("OPENSEARCH_HOST", "OSPREY_HIGHEST_MARKING"))
    refresh.files_up_to_date(made.repo)
    after = made.after()
    for line in (APPENDED + OPERATOR_LINE).splitlines(keepends=True):
        assert after.splitlines(keepends=True).count(line) == 1, line
    # A missing line `apply` appends is not added either: the render does not emit it.
    gone = _make(tmp_path / "again", drop=("VALKEY_HOST", "OIDC_JWKS_URL"))
    refresh.files_up_to_date(gone.repo)
    assert gone.after() == gone.before


SECRET_SHAPED = (
    "OSPREY_PLANTED_PASSWORD",
    "OSPREY_PLANTED_SECRET",
    "PLANTED_ACCESS_KEY",
    "OSPREY_MODEL_KEY_PLANTED",
    "OSPREY_CONNECTION_SECRET_PLANTED",
    "OSPREY_CONNECTOR_EGRESS",
)


@pytest.mark.parametrize("key", SECRET_SHAPED)
def test_a_secret_line_is_never_changed_or_written_whatever_the_render_says(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    """A render line named like a secret is planted (patched into `_render_env`'s output). A
    deployment that holds the line keeps its value and the key is not named; one that lacks it is
    not given it. Both at the shape the render would emit: `KEY=value`."""
    assert _SECRET_KEY.search(key), "the plant is not shaped like a secret name any more"
    holds = _make(tmp_path / "holds", own=f"{key}=held-by-the-deployment-77\n")
    lacks = _make(tmp_path / "lacks")
    with _planted(f"{key}=from-the-render-77", after="OSPREY_SEARCH_BACKEND="):
        refresh.files_up_to_date(holds.repo)
        refresh.files_up_to_date(lacks.repo)
    assert holds.after() == holds.before  # the held value, and nothing else moved
    assert lacks.after() == lacks.before
    said = capsys.readouterr().out
    assert (
        key not in said
        and "from-the-render-77" not in said
        and "held-by-the-deployment-77" not in said
    )


def test_a_secret_line_the_render_does_not_emit_is_never_changed(tmp_path: Path) -> None:
    made = _make(tmp_path, drop=("OPENSEARCH_HOST",))
    refresh.files_up_to_date(made.repo)
    for line in HELD_SECRETS.splitlines(keepends=True):
        assert line in made.after().splitlines(keepends=True)


def test_a_new_plain_render_line_is_added_after_the_line_it_follows_in_the_render(
    tmp_path: Path,
) -> None:
    """The owner's red-first plant: one new plain line in the render, absent from a deployment. On
    main refresh does not add it; after this slice it does, where the render puts it."""
    made = _make(tmp_path)
    assert "OSPREY_PLANTED_THING" not in made.before
    with _planted("OSPREY_PLANTED_THING=x", after="OSPREY_SEARCH_BACKEND="):
        refresh.files_up_to_date(made.repo)
    after = made.after().splitlines(keepends=True)
    at = after.index("OSPREY_PLANTED_THING=x\n")
    assert after[at - 1].startswith("OSPREY_SEARCH_BACKEND=")
    # Nothing else moved.
    assert _without(made.after(), "OSPREY_PLANTED_THING") == made.before


def test_a_new_plain_render_line_at_the_end_of_the_render_is_added_after_the_line_before_it(
    tmp_path: Path,
) -> None:
    """The line before it in the render is in the deployment: the first branch of `_put_line`.
    (The branches that hold nothing before it are the two tests below.)"""
    made = _make(tmp_path)
    with _planted("OSPREY_PLANTED_THING=x"):  # at the end of the render
        refresh.files_up_to_date(made.repo)
    assert "OSPREY_PLANTED_THING=x\n" in made.after().splitlines(keepends=True)
    assert _without(made.after(), "OSPREY_PLANTED_THING") == made.before


@pytest.mark.parametrize(
    "ends_in_newline", [True, False], ids=["newline-ended", "no-final-newline"]
)
def test_a_line_added_to_a_deployment_that_holds_no_render_line_goes_at_the_end_and_joins_nothing(
    tmp_path: Path, ends_in_newline: bool
) -> None:
    """The last branch of `_put_line`: no line the render has, before or after, is in the file, so
    the line goes at the end. Where the file ends without a newline (an operator's last line), the
    guard ends that line first: without it the added line would be joined onto it, which changes
    the operator's value (answer 3). Every render key is dropped, so the first line added has
    nothing to follow, and the plant adds one more line that the deployment lacks as well."""
    made = _make(tmp_path, drop=tuple(DEFAULT_KEYS))
    assert not set(DEFAULT_KEYS) & set(_keys(made.before)), "a render line is still in the file"
    held = made.before if ends_in_newline else made.before.removesuffix("\n")
    assert held.rstrip("\n").endswith(OPERATOR_LINE.rstrip("\n"))
    made.env.write_text(held, encoding="utf-8")
    with _planted("OSPREY_PLANTED_THING=x"):
        refresh.files_up_to_date(made.repo)
    after = made.after()
    # Every line the file held is still there, whole and in order, ahead of what was added.
    assert after.startswith(held if ends_in_newline else held + "\n"), (
        "a held line was joined onto, or moved"
    )
    lines = after.splitlines(keepends=True)
    for line in OPERATOR_LINE.splitlines(keepends=True):
        assert lines.count(line) == 1, f"the operator's line was changed: {line!r}"
    for line in (APPENDED + HELD_SECRETS).splitlines(keepends=True):
        assert lines.count(line) == 1, line
    # ...and what was missing is there, as the render writes it, once each.
    for key in [*DEFAULT_KEYS, "OSPREY_PLANTED_THING"]:
        assert sum(1 for line in lines if line.startswith(f"{key}=")) == 1, key
    assert "OSPREY_PLANTED_THING=x\n" in lines


def test_a_line_added_before_the_nearest_line_the_render_has_after_it_when_none_before_is_held(
    tmp_path: Path,
) -> None:
    """The middle branch: nothing before it in the render is in the file, a line after it is. A line
    planted at the head of the render, ahead of `OSPREY_PROFILE`, goes before the nearest held one
    and not at the end of the file."""
    made = _make(tmp_path)
    real = render_module._render_env

    def planted_first(config: OspreyConfig) -> str:
        return "OSPREY_PLANTED_THING=x\n" + real(config)

    with mock.patch.object(render_module, "_render_env", planted_first):
        refresh.files_up_to_date(made.repo)
    lines = made.after().splitlines(keepends=True)
    at = lines.index("OSPREY_PLANTED_THING=x\n")
    assert lines[at + 1].startswith(f"{DEFAULT_KEYS[0]}="), (
        "not before the nearest held line after it"
    )
    assert _without(made.after(), "OSPREY_PLANTED_THING") == made.before


# ---- the staged way ------------------------------------------------------------------------------


def test_a_refresh_that_refuses_changes_nothing(tmp_path: Path) -> None:
    """A secret the compose file requires is missing: refresh refuses, and the line it would have
    added is not in the file (the files pass runs on a copy; nothing moves until it is whole)."""
    made = _make(tmp_path, drop=("OPENSEARCH_HOST", "OSPREY_POSTGRES_PASSWORD"))
    before = made.env.read_bytes()
    with pytest.raises(refresh.RefreshFailed):
        refresh.files_up_to_date(made.repo)
    assert made.env.read_bytes() == before


def test_the_file_is_written_600_and_a_second_run_changes_nothing(tmp_path: Path) -> None:
    made = _make(tmp_path, drop=("OPENSEARCH_HOST",))
    made.env.chmod(0o644)
    refresh.files_up_to_date(made.repo)
    assert made.env.stat().st_mode & 0o777 == 0o600
    first = made.env.read_bytes()
    refresh.files_up_to_date(made.repo)
    assert made.env.read_bytes() == first


# ---- the rebuild's failure message ---------------------------------------------------------------

_OPENSEARCH_COMPOSE = (
    "services:\n  api:\n    image: osprey/api\n"
    "  opensearch:\n    image: opensearchproject/opensearch:2.19.1\n"
)


def _rebuild_fails(repo: Path, env: str) -> str:  # noqa: F811
    out = repo / "deploy" / "generated" / "local-lite"
    (out / "compose.yaml").write_text(_OPENSEARCH_COMPOSE, encoding="utf-8")
    (out / "deployment.env").write_text(env, encoding="utf-8")
    with pytest.raises(refresh.RefreshFailed) as failed:
        refresh.refresh(
            repo, run=Recorder(fail_on="scripts.rebuild_search_index"), register=Registrar()
        )
    return str(failed.value)


@pytest.mark.parametrize(
    "env",
    [
        "OSPREY_POSTGRES_PASSWORD=x\n",
        "OSPREY_POSTGRES_PASSWORD=x\nOPENSEARCH_HOST=\n",
        # As Compose reads the file, these set nothing (the lane review's findings on search_rebuild).
        "OSPREY_POSTGRES_PASSWORD=x\nOPENSEARCH_HOST= # note\n",
        'OSPREY_POSTGRES_PASSWORD=x\nexport OPENSEARCH_HOST=""\n',
        "OSPREY_POSTGRES_PASSWORD=x\n# OPENSEARCH_HOST=opensearch\n",
    ],
)
def test_the_rebuild_with_no_opensearch_address_says_to_run_apply(repo: Path, env: str) -> None:  # noqa: F811
    said = _rebuild_fails(repo, env)
    assert "ospreyflow apply" in said, said
    assert "start --build" not in said, said
    assert "OPENSEARCH_URL" in said and "OPENSEARCH_HOST" in said, (
        "names the setting that is missing"
    )
    assert "search index" in said and "exact identifiers" in said


@pytest.mark.parametrize(
    "env",
    [
        "OSPREY_POSTGRES_PASSWORD=x\nOPENSEARCH_HOST=opensearch\n",
        "OSPREY_POSTGRES_PASSWORD=x\nOPENSEARCH_URL=https://search.example.org\n",
        # As Compose reads the file, these set an address.
        "OSPREY_POSTGRES_PASSWORD=x\nexport OPENSEARCH_HOST=opensearch\n",
        "OSPREY_POSTGRES_PASSWORD=x\n  OPENSEARCH_HOST=opensearch\n",
        'OSPREY_POSTGRES_PASSWORD=x\nOPENSEARCH_URL="https://search.example.org" # mine\n',
    ],
)
def test_a_rebuild_that_fails_for_another_reason_keeps_its_message(repo: Path, env: str) -> None:  # noqa: F811
    said = _rebuild_fails(repo, env)
    assert "ospreyflow start --build" in said, said
    assert "ospreyflow apply" not in said, said
    assert "exact identifiers" in said


# ---- the file as Compose reads it ----------------------------------------------------------------
# Refresh decides what a deployment.env holds as Compose does (`harness.preflight.ports.
# read_env_file`): an `export ` prefix and leading space are dropped, a quoted value is taken whole,
# an unquoted value's ` #` comment is left off. A line Compose reads as setting a key is a line
# that is there; the render's line is not added beside it, and its value is never replaced.

_FORMS = {
    "export": "export {key}={value}\n",
    "export-spaced": "export   {key}={value}\n",
    "indented": "  {key}={value}\n",
    "tabbed": "\t{key}={value}\n",
}


def _in_form(text: str, key: str, form: str, value: str | None = None) -> str:
    """`text` with the line that sets `key` written in `form`, keeping the render's value unless
    `value` is given."""
    was = _line(text, key)
    wanted = _FORMS[form].format(key=key, value=value if value is not None else _value(was))
    return text.replace(was, wanted)


def _value(line: str) -> str:
    return line.partition("=")[2].rstrip("\n")


_THE_RENDERS = [key for key in DEFAULT_KEYS if key not in refresh._MODEL_LINES]


@pytest.mark.parametrize("form", _FORMS)
def test_a_line_compose_reads_as_set_is_not_added_again_nor_changed_and_is_named_if_it_differs(
    tmp_path: Path, form: str, capsys: pytest.CaptureFixture[str]
) -> None:
    made = _make(tmp_path)
    key = "OSPREY_HIGHEST_MARKING"
    held = _in_form(made.full, key, form, "OFFICIAL-edited-77")
    made.env.write_text(held, encoding="utf-8")
    refresh.files_up_to_date(made.repo)
    assert made.after() == held, "the operator's line was added beside, moved or changed"
    said = capsys.readouterr().out
    assert key in said and "ospreyflow apply" in said
    assert "OFFICIAL-edited-77" not in said, "a value was said aloud"


@pytest.mark.parametrize("key", _THE_RENDERS)
def test_an_export_line_with_the_renders_value_is_left_alone_and_not_named(
    tmp_path: Path, key: str, capsys: pytest.CaptureFixture[str]
) -> None:
    made = _make(tmp_path)
    held = _in_form(made.full, key, "export")
    made.env.write_text(held, encoding="utf-8")
    refresh.files_up_to_date(made.repo)
    assert made.after() == held
    assert key not in capsys.readouterr().out


def test_a_file_written_wholly_with_export_is_not_added_to_nor_changed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = _make(tmp_path)
    held = "".join(
        f"export {line}"
        if (key := refresh._the_key(line)) is not None and key not in refresh._MODEL_LINES
        else line
        for line in made.full.splitlines(keepends=True)
    )
    made.env.write_text(held, encoding="utf-8")
    refresh.files_up_to_date(made.repo)
    assert made.after() == held
    assert "refresh: these settings" not in capsys.readouterr().out


def test_a_value_compose_reads_the_same_is_not_named_as_differing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = _make(tmp_path)
    key = "OSPREY_HIGHEST_MARKING"
    was = _line(made.full, key)
    quoted = f'{key}="{_value(was)}" # a note of mine\n'
    held = made.full.replace(was, quoted)
    made.env.write_text(held, encoding="utf-8")
    refresh.files_up_to_date(made.repo)
    assert made.after() == held
    assert key not in capsys.readouterr().out


def test_the_last_line_compose_reads_for_a_key_decides_whether_it_differs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    made = _make(tmp_path)
    key = "OSPREY_HIGHEST_MARKING"
    held = made.full + f"export {key}=OFFICIAL-later-77\n"
    made.env.write_text(held, encoding="utf-8")
    refresh.files_up_to_date(made.repo)
    assert made.after() == held
    said = capsys.readouterr().out
    assert key in said and "OFFICIAL-later-77" not in said



# ---- the boundary, fail closed -------------------------------------------------------------------


def _reviewed() -> frozenset[str]:
    return frozenset(
        line.strip()
        for line in REVIEWED_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _shape_configs(tmp_path: Path) -> list[tuple[str, OspreyConfig]]:
    """Every shape and every setting that adds or removes a line of the render's env file."""
    org = {
        "governance": {
            "organisation_sign_in": "acme",
            "organisation_provider": {
                "label": "Acme",
                "issuer": "https://id.example.org",
                "client_id": "c",
            },
        }
    }
    scheme = tmp_path / "scheme.yaml"
    scheme.write_text(
        yaml.safe_dump(
            {
                "scheme": "force-4x3",
                "source": ["A", "B"],
                "intelligence": ["1", "2"],
                "handling": ["P", "C"],
            }
        ),
        encoding="utf-8",
    )
    by_setting: dict[str, tuple[str, dict[str, Any]]] = {
        "clickhouse": ("local-lite", {"components": {"analytics_engine": "clickhouse"}}),
        "no opensearch": ("local-lite", {"components": {"search": "postgres-fulltext"}}),
        "sized to the server": ("small", {"resources": {"memory_gib": 32}}),
        "mail": (
            "local-lite",
            {"mail": {"host": "mail.example.org", "from_address": "a@example.org"}},
        ),
        "organisation sign-in": ("small", org),
        "connectors": (
            "local-lite",
            {"connectors": {"private_hosts": ["10.0.0.0/8"], "secrets": ["DB"]}},
        ),
        "hosted fallback": (
            "local-lite",
            {"models": {"local_only": False, "hosted_fallback": "x"}},
        ),
        "an engine": (
            "local-lite",
            {
                "models": {
                    "local_only": False,
                    "providers": [{"name": "openai", "roles": {"extraction": "gpt-4o"}}],
                }
            },
        ),
        "report sync": ("local-lite", {"reporting": {"sync": True}}),
        "superset": ("local-lite", {"reporting": {"superset": True}}),
        "a graph port": ("local-lite", {"deployment": {"graph_port": 2490}}),
        "a grading file": ("local-lite", {"grading": {"scheme": str(scheme)}}),
        "laurium": ("cloud-platform-poc", {"models": {"extraction_engine": "laurium"}}),
    }
    configs = [
        (f"{shape} {brand}", ref.config_for(shape, brand)) for shape, brand in ref.all_folders()
    ]
    for name, (shape, settings) in by_setting.items():
        configs.append((name, ref.config_for(shape, "ospreyflow", **settings)))
    for _, config in configs:
        config.grading.read_file(tmp_path)
    return configs


def boundary_violations(
    configs: list[tuple[str, OspreyConfig]], reviewed: frozenset[str]
) -> list[str]:
    """Each key `_render_env` emits (through the module, so a plant in it is seen) that the secret
    name test matches or the reviewed list lacks."""
    found = []
    for name, config in configs:
        for key in _keys(render_module._render_env(config)):
            if _SECRET_KEY.search(key):
                found.append(f"{name}: {key} matches the secret name test")
            if key not in reviewed:
                found.append(f"{name}: {key} is not on the reviewed list")
    return found


#: The functions whose source is the render's env lines: a line in a branch no shape above reaches
#: is still a literal `"KEY="` here.
def _env_sources() -> dict[str, str]:
    return {
        fn.__qualname__: inspect.getsource(fn)
        for fn in (
            render_module._render_env,
            render_module._grading_env,
            render_module.model_engines_env,
            reporting.reporting_env,
            laurium.laurium_env,
        )
    }


def source_violations(sources: dict[str, str], reviewed: frozenset[str]) -> list[str]:
    found = []
    for name, text in sources.items():
        for key in sorted(set(re.findall(r"""["']([A-Z][A-Z0-9_]*)=""", text))):
            if _SECRET_KEY.search(key):
                found.append(f"{name}: {key} matches the secret name test")
            if key not in reviewed:
                found.append(f"{name}: {key} is not on the reviewed list")
    return found


def test_the_render_emits_nothing_secret_or_unreviewed(tmp_path: Path) -> None:
    configs = _shape_configs(tmp_path)
    assert len(configs) >= 20
    assert boundary_violations(configs, _reviewed()) == []


def test_every_env_line_the_render_source_names_is_reviewed(tmp_path: Path) -> None:
    sources = _env_sources()
    assert len(sources) == 5 and all("=" in text for text in sources.values())
    assert source_violations(sources, _reviewed()) == []


def test_the_reviewed_list_is_one_key_per_line_and_names_no_secret() -> None:
    keys = [
        line.strip()
        for line in REVIEWED_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert keys and len(keys) == len(set(keys))
    assert all(re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in keys)
    assert [key for key in keys if _SECRET_KEY.search(key)] == []
    header = REVIEWED_FILE.read_text(encoding="utf-8").splitlines()[:12]
    assert any("a human" in line.lower() for line in header), "the header says who may add to it"


def test_a_new_plain_render_line_not_on_the_list_is_red(tmp_path: Path) -> None:
    configs = _shape_configs(tmp_path)
    assert boundary_violations(configs, _reviewed()) == []  # green first
    with _planted("OSPREY_PLANTED_THING=x"):
        found = boundary_violations(configs, _reviewed())
    assert found and all(
        "OSPREY_PLANTED_THING is not on the reviewed list" in line for line in found
    ), found
    assert not any("secret name test" in line for line in found)


def test_a_new_render_line_named_like_a_password_is_red_even_if_someone_reviewed_it(
    tmp_path: Path,
) -> None:
    configs = _shape_configs(tmp_path)
    with _planted("OSPREY_PLANTED_PASSWORD=x"):
        found = boundary_violations(configs, _reviewed())
        assert any("OSPREY_PLANTED_PASSWORD is not on the reviewed list" in line for line in found)
        assert any("OSPREY_PLANTED_PASSWORD matches the secret name test" in line for line in found)
        # Added to the list by mistake, it is still red: the name test is the second lock.
        found = boundary_violations(configs, _reviewed() | {"OSPREY_PLANTED_PASSWORD"})
    assert found and all("matches the secret name test" in line for line in found), found


def test_a_new_render_line_named_like_a_token_is_caught_by_the_list_alone(tmp_path: Path) -> None:
    """`_SECRET_KEY` does not match `..._TOKEN`: the reviewed list is what catches it, which is why
    the list exists."""
    assert _SECRET_KEY.search("OSPREY_PLANTED_TOKEN") is None
    configs = _shape_configs(tmp_path)
    with _planted("OSPREY_PLANTED_TOKEN=x"):
        found = boundary_violations(configs, _reviewed())
    assert found and all(
        "OSPREY_PLANTED_TOKEN is not on the reviewed list" in line for line in found
    ), found


def test_a_line_added_in_a_branch_no_shape_reaches_is_red_in_the_source_scan() -> None:
    """The shape of a new conditional line in the render: `lines.append("KEY=...")` in a function
    the shapes above may not reach."""
    sources = _env_sources()
    assert source_violations(sources, _reviewed()) == []  # green first
    planted = dict(sources)
    planted["_render_env"] += '\n    lines.append("OSPREY_PLANTED_BRANCH=1")\n'
    assert source_violations(planted, _reviewed()) == [
        "_render_env: OSPREY_PLANTED_BRANCH is not on the reviewed list"
    ]
    planted["_render_env"] = (
        sources["_render_env"] + '\n    lines.append(f"OSPREY_PLANTED_PASSWORD={x}")\n'
    )
    found = source_violations(planted, _reviewed() | {"OSPREY_PLANTED_PASSWORD"})
    assert found == ["_render_env: OSPREY_PLANTED_PASSWORD matches the secret name test"]


def test_the_reviewed_list_is_read_whole_not_by_a_prefix(tmp_path: Path) -> None:
    """A reviewed key is a whole key: `OSPREY_PLANTED` on the list passes no longer key."""
    configs = _shape_configs(tmp_path)
    with _planted("OSPREY_PLANTED_THING=x"):
        assert boundary_violations(configs, _reviewed() | {"OSPREY_PLANTED"})
