"""A deployment's own PostgreSQL allows what `osprey.yaml` says (ADR-114 Amendment 49, slice PL2b).

`resources.postgres_max_connections`: an optional whole number; unset, the computed 660 of
Amendment 43 exactly as before; set, rendered on the deployment's own PostgreSQL (Lite, and Small
with every store in a container) and kept by a refresh of an existing deployment. Below the floor
(420: the same sum with one Conduit), refused in words; under the `cluster` and `cloud-platform`
profiles, whose databases OspreyFlow does not render, refused in words too.

Rule 12, each invariant and the test that fails without it:

- **The floor is applied.** `test_a_value_below_the_floor_is_refused_in_words[419]` fails if the
  schema accepts 419 (no floor, or a floor lower than 420), and
  `test_the_floor_the_schema_applies_is_the_constant_not_a_copy_of_it` fails if the schema holds
  its own 420 instead of reading `harness.profiles`' constant.
- **The ceiling is applied** (what the real PostgreSQL refuses, rule 15): PostgreSQL 16 stops at
  start-up when `max_connections` plus its other server processes passes 262143.
  `test_a_value_above_the_ceiling_is_refused_in_words[262122]` fails if the schema accepts it (no
  ceiling, or one above 262121), and `test_the_ceiling_is_what_postgres_16_leaves_for_connections`
  fails if the ceiling is not read from the named constants.
- **The floor follows the pools**: `test_the_floor_follows_the_constants_it_is_made_of` (raise
  `KEYCLOAK_POOL_MAX` in a copy of `profiles.py`; the floor and the default rise with it).
- **Unset changes nothing**: `test_unset_is_the_computed_number_exactly_as_before` and
  `test_a_deployment_that_sets_nothing_renders_the_same_with_or_without_the_field`.
- **A set value reaches every reader**: `test_a_set_value_reaches_the_rendered_command`,
  `test_a_refresh_applies_a_changed_value_and_keeps_a_set_one`, and
  `test_no_reader_of_the_computed_number_is_left_beside_the_setting` (a reader added later that
  takes the constant instead of the setting fails it).
- **Never silently ignored**: `test_the_setting_is_refused_where_the_database_is_not_rendered`.
- **Documented, and in the generated types**: `test_the_setting_is_documented_and_generated`.

Each case goes through the real call site: `OspreyConfig` validation, `harness.render.render` and
`scripts.refresh.files_up_to_date`, not a helper alone. Pure: nothing is started, no network.
"""

from __future__ import annotations

import re
import sys
import types
from pathlib import Path
from typing import Any

import pytest
import yaml
from harness import profiles
from harness.cloud_platform.connections import POSTGRES_MAX_CONNECTIONS as RDS_MAX_CONNECTIONS
from harness.keycloak_theme import write_login_theme
from harness.render import render
from pydantic import ValidationError
from scripts import refresh
from tools.cp_policy_check import FIXTURES, _resolver
from tools.layout import BUILD, CORE

from schemas.deployment import OspreyConfig

LITE: dict[str, Any] = {"profile": "local-lite"}
SMALL: dict[str, Any] = {
    "profile": "small",
    "network": {"public_origin": "https://demo.example.org"},
}
CLUSTER: dict[str, Any] = {
    "profile": "cluster",
    "network": {"public_origin": "https://osprey.example.org"},
    "cluster": {"shared_storage_class": "efs-sc"},
    "components": {"analytics_engine": "clickhouse"},  # a cluster's Conduits share ClickHouse
    "external": {
        "postgres": {"host": "osprey.cluster-x.eu-west-2.rds.amazonaws.com"},
        "valkey": {"host": "osprey.x.cache.amazonaws.com", "tls": True},
        "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
    },
}
DEFAULT = 660  # Amendment 43's number, pinned: a change to it is a change to every deployment
FLOOR = 420


def _with(raw: dict[str, Any], **resources: Any) -> dict[str, Any]:
    return {**raw, "resources": {**raw.get("resources", {}), **resources}}


def _cloud_platform(name: str = "development") -> dict[str, Any]:
    return yaml.safe_load((FIXTURES / f"{name}.yaml").read_text(encoding="utf-8"))


def _artefacts(raw: dict[str, Any]) -> dict[str, str]:
    config = OspreyConfig.model_validate(raw)
    return render(config, resolver=_resolver).artefacts


def _command(raw: dict[str, Any]) -> list[str]:
    return yaml.safe_load(_artefacts(raw)["compose.yaml"])["services"]["postgres"]["command"]


def _refusal(raw: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as refused:
        OspreyConfig.model_validate(raw)
    return str(refused.value)


# ---- unset: today's output, exactly -------------------------------------------------------------


def test_unset_is_the_computed_number_exactly_as_before() -> None:
    assert OspreyConfig().resources.postgres_max_connections is None
    assert profiles.POSTGRES_MAX_CONNECTIONS == DEFAULT
    assert _command(LITE) == ["postgres", "-c", f"max_connections={DEFAULT}"]
    assert _command(SMALL) == ["postgres", "-c", f"max_connections={DEFAULT}"]
    assert _command(_with(SMALL, memory_gib=64)) == [
        "postgres", "-c", f"max_connections={DEFAULT}",
        "-c", "shared_buffers=2048MB", "-c", "effective_cache_size=6144MB",
    ]  # fmt: skip
    # The function a refresh uses, called as it was: the default, and the file as before.
    services: dict[str, Any] = {"postgres": {"command": ["postgres"]}}
    assert profiles.postgres_command() == ["postgres", "-c", f"max_connections={DEFAULT}"]
    assert profiles.postgres_connections_up_to_date(services) is True
    assert services["postgres"]["command"] == ["postgres", "-c", f"max_connections={DEFAULT}"]


@pytest.mark.parametrize(
    "raw",
    [LITE, SMALL, _with(SMALL, memory_gib=64), CLUSTER, _cloud_platform(), _cloud_platform("poc"),
     _cloud_platform("production")],
    ids=["lite", "small", "small-sized", "cluster", "cp-development", "cp-poc", "cp-production"],
)  # fmt: skip
def test_a_deployment_that_sets_nothing_renders_the_same_with_or_without_the_field(
    raw: dict[str, Any],
) -> None:
    """Every profile's whole output, the field absent and the field named `null`: identical."""
    named = {**raw, "resources": {**raw.get("resources", {}), "postgres_max_connections": None}}
    assert OspreyConfig.model_validate(named).resources.postgres_max_connections is None
    assert _artefacts(named) == _artefacts(raw)


def test_the_cloud_platforms_database_keeps_the_owners_1000() -> None:
    assert RDS_MAX_CONNECTIONS == 1000
    terraform = "\n".join(
        text for name, text in _artefacts(_cloud_platform()).items() if name.endswith(".tf")
    )
    assert re.search(r'"max_connections"\s+value\s*=\s*"1000"', terraform), terraform[:400]


# ---- set: rendered, and kept by a refresh ----------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [LITE, SMALL, _with(SMALL, memory_gib=64)],
    ids=["lite", "small", "small-sized"],
)
def test_a_set_value_reaches_the_rendered_command(raw: dict[str, Any]) -> None:
    command = _command(_with(raw, postgres_max_connections=900))
    unset = _command(raw)
    assert command[:3] == ["postgres", "-c", "max_connections=900"]
    # Only that part moved: the sized settings after it are the same as without the setting.
    assert command[3:] == unset[3:]
    assert f"max_connections={DEFAULT}" not in " ".join(command)


def test_the_setting_alone_does_not_size_the_stores() -> None:
    """It names a limit, not a memory: Lite takes it, and the stores keep their fixed sizes."""
    config = OspreyConfig.model_validate(_with(LITE, postgres_max_connections=900))
    assert config.resources.any is False
    assert _command(_with(LITE, postgres_max_connections=900)) == [
        "postgres", "-c", "max_connections=900",
    ]  # fmt: skip


def test_the_floor_itself_is_accepted_on_lite_and_small() -> None:
    for raw in (LITE, SMALL):
        config = OspreyConfig.model_validate(_with(raw, postgres_max_connections=FLOOR))
        assert config.resources.postgres_max_connections == FLOOR
        assert _command(_with(raw, postgres_max_connections=FLOOR))[2] == f"max_connections={FLOOR}"


def test_the_function_a_refresh_uses_takes_the_setting() -> None:
    """A file holding 660 is out of date against 900, and then holds 900; one holding 900 is
    current, and is not corrected back to 660 by the function's default."""
    old: dict[str, Any] = {
        "postgres": {"command": ["postgres", "-c", f"max_connections={DEFAULT}"]}
    }
    assert profiles.postgres_connections_up_to_date(old, 900) is True
    assert old["postgres"]["command"] == ["postgres", "-c", "max_connections=900"]
    assert profiles.postgres_connections_up_to_date(old, 900) is False
    # The setting taken away: the computed number comes back, which is a change.
    assert profiles.postgres_connections_up_to_date(old, None) is True
    assert old["postgres"]["command"] == ["postgres", "-c", f"max_connections={DEFAULT}"]


def _deployment(tmp_path: Path, raw: dict[str, Any], holding: int) -> tuple[Path, Path]:
    """A Lite deployment as an earlier apply left it, its compose file holding `holding`, and the
    `osprey.yaml` beside it as the owner has it now. `refresh.files_up_to_date` runs on it."""
    repo = tmp_path / "repo"
    out = repo / "deploy" / "generated" / "local-lite"
    out.mkdir(parents=True)
    tokens = repo / "apps" / "workspace" / "src" / "design" / "tokens.css"
    tokens.parent.mkdir(parents=True)
    tokens.write_text(":root { --brass: #c08a34; }\n", encoding="utf-8")
    write_login_theme(out, tokens_css=tokens.read_text(encoding="utf-8"))
    config = OspreyConfig.model_validate(raw)
    (repo / "osprey.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    (out / "osprey.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    artefacts = render(config, allow_unpinned=True).artefacts
    compose = artefacts["compose.yaml"]
    document = yaml.safe_load(compose)
    document["services"]["postgres"]["command"] = ["postgres", "-c", f"max_connections={holding}"]
    banner = compose[: compose.index("\nname:") + 1]
    (out / "compose.yaml").write_text(
        banner + yaml.safe_dump(document, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    required = sorted(set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?", compose)))
    env = artefacts["deployment.env"] + "".join(f"{n}=held-{n.lower()}\n" for n in required)
    (out / "deployment.env").write_text(env, encoding="utf-8")
    (out / "litellm.yaml").write_text("model_list: []\n", encoding="utf-8")
    (out / "Caddyfile").write_text(artefacts["Caddyfile"], encoding="utf-8")
    return repo, out


def _held(out: Path) -> list[str]:
    document = yaml.safe_load((out / "compose.yaml").read_text(encoding="utf-8"))
    return document["services"]["postgres"]["command"]


def test_a_refresh_applies_a_changed_value_and_keeps_a_set_one(tmp_path: Path) -> None:
    # 660 in the file, 900 in osprey.yaml: the refresh brings the file to 900, then leaves it.
    repo, out = _deployment(tmp_path / "a", _with(LITE, postgres_max_connections=900), DEFAULT)
    assert _held(out) == ["postgres", "-c", f"max_connections={DEFAULT}"]
    refresh.files_up_to_date(repo)
    assert _held(out) == ["postgres", "-c", "max_connections=900"]
    settled = (out / "compose.yaml").read_bytes()
    refresh.files_up_to_date(repo)
    assert (out / "compose.yaml").read_bytes() == settled

    # 900 in the file and in osprey.yaml: current, never corrected back to 660.
    repo, out = _deployment(tmp_path / "b", _with(LITE, postgres_max_connections=900), 900)
    before = (out / "compose.yaml").read_bytes()
    refresh.files_up_to_date(repo)
    assert (out / "compose.yaml").read_bytes() == before
    assert _held(out) == ["postgres", "-c", "max_connections=900"]

    # Nothing set: 900 left in the file by hand goes back to the computed number, as before.
    repo, out = _deployment(tmp_path / "c", LITE, 900)
    refresh.files_up_to_date(repo)
    assert _held(out) == ["postgres", "-c", f"max_connections={DEFAULT}"]


def test_no_reader_of_the_computed_number_is_left_beside_the_setting() -> None:
    """With the setting set, no rendered file of a profile that renders a database names 660; and no
    file of the product reads the computed number or builds the command without the setting."""
    for raw in (LITE, SMALL, _with(SMALL, memory_gib=64)):
        for name, text in _artefacts(_with(raw, postgres_max_connections=900)).items():
            assert f"max_connections={DEFAULT}" not in text, name
    readers = {
        path.relative_to(CORE).as_posix()
        for path in CORE.rglob("*.py")
        if "node_modules" not in path.parts
        and ".venv" not in path.parts
        and "POSTGRES_MAX_CONNECTIONS" in path.read_text(encoding="utf-8")
        and "cloud_platform" not in path.parts
    }
    # `profiles.py` defines it; the schema names it in the refusal's words (the computed number);
    # `refresh.py` and `render.py` take the setting beside it, and never the constant.
    assert readers == {"harness/profiles.py", "packages/schemas/deployment.py"}, readers
    callers = {
        path.relative_to(CORE).as_posix()
        for path in CORE.rglob("*.py")
        if "node_modules" not in path.parts
        and ".venv" not in path.parts
        and re.search(
            r"\b(postgres_command|postgres_connections_up_to_date)\(",
            path.read_text(encoding="utf-8"),
        )
        and path.name != "profiles.py"
    }
    assert callers == {"harness/render.py", "scripts/refresh.py"}, callers
    for relative in sorted(callers):
        text = (CORE / relative).read_text(encoding="utf-8")
        assert "postgres_max_connections" in text, f"{relative} does not read the setting"


# ---- refused, in words -----------------------------------------------------------------------


@pytest.mark.parametrize("value", [FLOOR - 1, 100, 1])
def test_a_value_below_the_floor_is_refused_in_words(value: int) -> None:
    for raw in (LITE, SMALL):
        said = _refusal(_with(raw, postgres_max_connections=value))
        assert "resources.postgres_max_connections" in said
        assert f"is {value}" in said and f"below {FLOOR}" in said  # the value and the floor
        assert str(DEFAULT) in said  # the computed default
        for part in ("Conduit", "Keycloak", "gateway", "Superset", "operator"):
            assert part in said, part  # what the floor is made of
        assert "remove" in said or "set it to" in said  # how to fix it


CEILING = (
    262121  # PostgreSQL 16's MAX_BACKENDS (262143) less the 22 other server processes at default
)


@pytest.mark.parametrize("value", [CEILING + 1, 300_000, 10**12])
def test_a_value_above_the_ceiling_is_refused_in_words(value: int) -> None:
    for raw in (LITE, SMALL):
        said = _refusal(_with(raw, postgres_max_connections=value))
        assert "resources.postgres_max_connections" in said
        assert f"is {value}" in said and f"above {CEILING}" in said  # the value and the ceiling
        assert "262143" in said  # what the ceiling is made of
        assert str(DEFAULT) in said  # the computed default
        assert "remove" in said or "set it to" in said  # how to fix it


def test_the_ceiling_is_what_postgres_16_leaves_for_connections() -> None:
    assert profiles.POSTGRES_MAX_BACKENDS == 0x3FFFF == 262143
    assert profiles.POSTGRES_MAX_CONNECTIONS_CEILING == CEILING
    for value in (CEILING, FLOOR):  # the ceiling itself is the PostgreSQL range's, so accepted
        raw = _with(LITE, postgres_max_connections=value)
        assert _command(raw)[2] == f"max_connections={value}"


def test_the_ceiling_the_schema_applies_is_the_constant_not_a_copy_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profiles, "POSTGRES_MAX_CONNECTIONS_CEILING", 1000)
    said = _refusal(_with(LITE, postgres_max_connections=1001))
    assert "above 1000" in said
    assert OspreyConfig.model_validate(_with(LITE, postgres_max_connections=1000))


@pytest.mark.parametrize(
    "value", [0, -1, -660, 900.5, 900.0, "900", "many", True, [900]],
    ids=["zero", "negative", "large-negative", "fraction", "float", "string", "words", "bool",
         "list"],
)  # fmt: skip
def test_what_is_not_a_whole_number_above_zero_is_refused_in_words(value: Any) -> None:
    said = _refusal(_with(LITE, postgres_max_connections=value))
    assert "resources.postgres_max_connections" in said
    assert "whole number" in said
    assert "Input should be" not in said  # our words, not the validator's own


@pytest.mark.parametrize("raw", [CLUSTER, _cloud_platform()], ids=["cluster", "cloud-platform"])
def test_the_setting_is_refused_where_the_database_is_not_rendered(raw: dict[str, Any]) -> None:
    said = _refusal(_with(raw, postgres_max_connections=900))
    assert (
        "this profile's database is not rendered by OspreyFlow: set max_connections where the "
        "database is run"
    ) in said
    assert "resources.postgres_max_connections" in said
    # And the rendered file of each is what it was without the field (not a silent change).
    assert OspreyConfig.model_validate(raw).resources.postgres_max_connections is None


def test_a_small_on_a_managed_database_is_refused_too() -> None:
    managed = {**SMALL, "external": {"postgres": {"host": "db.example.org"}}}
    said = _refusal(_with(managed, postgres_max_connections=900))
    assert "not rendered by OspreyFlow" in said and "where the database is run" in said


# ---- the floor follows what it is made of -----------------------------------------------------


def _profiles_with(old: str, new: str) -> types.ModuleType:
    """`harness/profiles.py` read from the file, one line changed, run as a module of its own: the
    real arithmetic with a changed pool, in the test's own copy (rule 15)."""
    source = Path(profiles.__file__).read_text(encoding="utf-8")
    assert old in source, old
    module = types.ModuleType("profiles_planted")
    module.__file__ = profiles.__file__
    sys.modules[module.__name__] = module  # a dataclass in it looks its own module up
    try:
        exec(compile(source.replace(old, new, 1), "profiles_planted.py", "exec"), module.__dict__)
    finally:
        del sys.modules[module.__name__]
    return module


def test_the_floor_is_one_conduit_where_the_default_is_two() -> None:
    made = (
        profiles.CONDUIT_POOL_CEILING + profiles.RUNNING_LOADS_ALLOWED
        + profiles.KEYCLOAK_POOL_MAX + profiles.GATEWAY_POOL_MAX
        + profiles.SUPERSET_AND_REPORT_SYNC_MAX + profiles.OPERATOR_RESERVE
    )  # fmt: skip
    assert profiles.POSTGRES_MAX_CONNECTIONS_FLOOR == made == FLOOR
    assert profiles.POSTGRES_MAX_CONNECTIONS == made + (
        profiles.CONDUIT_POOL_CEILING + profiles.RUNNING_LOADS_ALLOWED
    )


def test_the_floor_follows_the_constants_it_is_made_of() -> None:
    planted = _profiles_with("KEYCLOAK_POOL_MAX = 100", "KEYCLOAK_POOL_MAX = 150")
    assert planted.POSTGRES_MAX_CONNECTIONS_FLOOR == FLOOR + 50
    assert planted.POSTGRES_MAX_CONNECTIONS == DEFAULT + 50
    other = _profiles_with("CONDUIT_POOL_CEILING = 220", "CONDUIT_POOL_CEILING = 240")
    assert other.POSTGRES_MAX_CONNECTIONS_FLOOR == FLOOR + 20  # one Conduit
    assert other.POSTGRES_MAX_CONNECTIONS == DEFAULT + 40  # two


def test_the_floor_the_schema_applies_is_the_constant_not_a_copy_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(profiles, "POSTGRES_MAX_CONNECTIONS_FLOOR", 500)
    said = _refusal(_with(LITE, postgres_max_connections=450))
    assert "below 500" in said
    assert OspreyConfig.model_validate(_with(LITE, postgres_max_connections=500))


# ---- documented, specified and generated -------------------------------------------------------

GUIDES = (
    BUILD / "spec" / "10_ADMINISTRATION_GUIDE.md",
    CORE / "docs" / "administration-guide.md",
)


@pytest.mark.parametrize("guide", GUIDES, ids=lambda p: p.parent.name)
def test_the_setting_is_documented_in_appendix_a_of_both_guides(guide: Path) -> None:
    text = guide.read_text(encoding="utf-8")
    appendix = text[text.index("<!-- options:begin -->") : text.index("<!-- options:end -->")]
    row = next(
        line
        for line in appendix.splitlines()
        if line.startswith("| `resources.postgres_max_connections`")
    )
    assert "int or none" in row and "none" in row
    assert str(FLOOR) in row and str(DEFAULT) in row


def test_the_setting_is_documented_and_generated() -> None:
    generated = (CORE / "packages" / "schemas" / "generated" / "ResourcesConfig.ts").read_text(
        encoding="utf-8"
    )
    assert "postgres_max_connections?: PostgresMaxConnections;" in generated
    assert "export type PostgresMaxConnections = number | null;" in generated
    guide = (CORE / "docs" / "administration-guide.md").read_text(encoding="utf-8")
    table = guide[guide.index("## Document control") : guide.index("<!-- document-control:end -->")]
    assert "postgres_max_connections" in table  # a row in the version table
    row_190 = next(line for line in table.splitlines() if line.startswith("| 1.90 |"))
    assert "at least 750" not in row_190  # the stale sentence: the RDS is set to 1000 (row 1.92)
    assert "max_connections` of 1000" in row_190


def test_the_amendment_is_written_and_reserved() -> None:
    decisions = (BUILD / "spec" / "06_DECISIONS.md").read_text(encoding="utf-8")
    start = decisions.index("### ADR-114, Amendment 49 (")
    body = decisions[start : decisions.index("\n### ", start + 10)]
    for words in ("resources.postgres_max_connections", "420", "660", "Amendment 43", "cluster",
                  "cloud-platform"):  # fmt: skip
        assert words in body, words
    reservations = (BUILD / "spec" / "ADR_RESERVATIONS.md").read_text(encoding="utf-8")
    row = next(
        line for line in reservations.splitlines() if line.startswith("| ADR-114 Amendment 49 |")
    )
    assert "v062 PL2b" in row and row.rstrip().endswith("| written |")
    deployment = (BUILD / "spec" / "05_DEPLOYMENT.md").read_text(encoding="utf-8")
    assert "resources.postgres_max_connections" in deployment
