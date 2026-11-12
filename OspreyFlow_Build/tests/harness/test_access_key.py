"""ADR-114 Amendment 41: a shared key asked for by the product's own proxy, on all three names,
before any page, asset, sign-in or API answer, for a deployment shown to people who are not its users (the
demonstration). Checked against a bcrypt hash the owner sets on the server; the key itself is never
in `osprey.yaml`, the repository, a message or a log.

`network.access_key: true` says the deployment asks; the hash, and the pass a browser is given once
it has answered, live only in `access-key.caddy` in the deployment's own folder (`600`, written by
`python -m harness.access_key set`). The render never reads that file: it imports it into the
Caddyfile and mounts it into the proxy alone, so a render, a diff and a drift report never hold the
hash. Unset, nothing changes (the cases at the end, and `gate/B-unset-renders.raw.txt`).

The real proxy's own answers, on each name, are `test_access_key_proxy.py`'s.
"""

from __future__ import annotations

import io
import os
import stat
import urllib.request
from pathlib import Path

import pytest
from harness import access_key, site
from harness.preflight import access_key as access_key_check
from harness.preflight.context import PreflightContext
from harness.preflight.result import Status
from harness.render import render
from harness.site import render_caddyfile
from pydantic import ValidationError

from schemas.deployment import OspreyConfig

ORIGIN = "https://demo.example.org"
HASH = "$2a$14$" + "a" * 53
TOKEN = "t" * 43


def _config(**network: object) -> OspreyConfig:
    return OspreyConfig.model_validate(
        {"profile": "small", "network": {"public_origin": ORIGIN, **network}}
    )


# --- The setting ----------------------------------------------------------------------------------


def test_a_small_on_https_may_ask_for_the_key() -> None:
    assert _config(access_key=True).network.access_key is True


def test_unset_it_does_not_ask() -> None:
    assert _config().network.access_key is False


def test_the_key_is_never_asked_over_plain_http_since_basic_sends_it_on_every_request() -> None:
    """A Small's address is always https:// (the profile's own rule), and only a Small may ask."""
    with pytest.raises(ValidationError, match="is plain HTTP"):
        OspreyConfig.model_validate(
            {"profile": "small", "network": {"public_origin": "http://demo.example.org",
                                             "access_key": True}}
        )  # fmt: skip


def test_the_key_is_for_a_small_alone() -> None:
    raw = {"profile": "local-lite", "network": {"public_origin": ORIGIN, "access_key": True}}
    with pytest.raises(ValidationError, match="network.access_key is for Small"):
        OspreyConfig.model_validate(raw)


# --- The render -----------------------------------------------------------------------------------


def _sites(caddyfile: str) -> dict[str, str]:
    """Each site block's text, by its address line."""
    blocks: dict[str, str] = {}
    current: str | None = None
    depth = 0
    for line in caddyfile.splitlines():
        if current is None and line.endswith("{") and not line.startswith(("\t", " ", "{")):
            current, depth, blocks[line] = line, 1, ""
            continue
        if current is not None:
            depth += line.count("{") - line.count("}")
            if depth == 0:
                current = None
                continue
            blocks[current] += line + "\n"
    return blocks


def test_the_render_imports_the_key_file_and_never_holds_the_hash() -> None:
    caddyfile = render_caddyfile(_config(access_key=True))
    assert f"import {access_key.IN_PROXY}\n" in caddyfile
    assert "$2a$" not in caddyfile and "basic_auth" in caddyfile


@pytest.mark.parametrize("name", ["demo.example.org", "id.demo.example.org", "bi.demo.example.org"])
def test_each_of_the_three_names_asks_for_the_key_and_says_noindex(name: str) -> None:
    config = _config(access_key=True)
    config.reporting.superset = True
    block = _sites(render_caddyfile(config))[f"https://{name} {{"]
    assert '\theader X-Robots-Tag "noindex, nofollow"\n' in block
    assert (
        "\t\tbasic_auth @osprey_locked bcrypt OspreyFlow {\n\t\t\timport osprey_access_key\n"
        in block
    )
    assert f"\t\timport osprey_access_pass_set {config.network.public_origin[8:]}\n" in block


def test_only_the_identity_providers_cross_origin_answers_go_without_the_key() -> None:
    """What the Glass asks the identity provider from its own origin (discovery, the token, its
    keys): a browser sends no stored credential or cookie there, and each answers nothing without
    a code, a refresh token or a signature to check. The sign-in page itself is behind the key."""
    blocks = _sites(render_caddyfile(_config(access_key=True)))
    identity = blocks["https://id.demo.example.org {"]
    glass = blocks["https://demo.example.org {"]
    open_paths = (
        "/realms/osprey/protocol/openid-connect/token /realms/osprey/protocol/openid-connect/certs "
        "/realms/osprey/.well-known/openid-configuration"
    )
    assert f"\t\tnot path {open_paths}\n" in identity
    assert "not path" not in glass
    assert "/protocol/openid-connect/auth" not in identity


def test_the_loopback_doors_and_the_health_answer_are_not_asked() -> None:
    caddyfile = render_caddyfile(_config(access_key=True))
    for address, block in _sites(caddyfile).items():
        if not address.startswith("https://"):
            assert "basic_auth" not in block, address


def test_the_redirect_to_https_says_noindex_too() -> None:
    tls = {"certificate": "/etc/osprey/cert.pem", "key": "/etc/osprey/key.pem"}
    config = _config(access_key=True, tls=tls, redirect_http=True)
    blocks = _sites(render_caddyfile(config))
    redirect = blocks["http://demo.example.org {"]
    assert '\theader X-Robots-Tag "noindex, nofollow"\n' in redirect
    assert "basic_auth" not in redirect


def test_the_key_file_is_mounted_into_the_proxy_alone(tmp_path: Path) -> None:
    import yaml

    rendered = render(_config(access_key=True), allow_unpinned=True)
    services = yaml.safe_load(rendered.artefacts["compose.yaml"])["services"]
    mount = f"./{access_key.ACCESS_KEY_FILE}:{access_key.IN_PROXY}:ro"
    holders = [name for name, svc in services.items() if mount in (svc.get("volumes") or [])]
    assert holders == ["proxy"]
    assert not any(access_key.ACCESS_KEY_FILE in name for name in rendered.artefacts)


def test_unset_the_caddyfile_and_the_proxy_are_as_they_were() -> None:
    caddyfile = render_caddyfile(_config())
    for word in ("import", "basic_auth", "X-Robots-Tag", "osprey_"):
        assert word not in caddyfile


# --- The helper the owner runs on the server ------------------------------------------------------


class _Asked:
    """The owner at the keyboard: each answer in turn, never echoed (`getpass`)."""

    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0)


def _hasher(key: str) -> str:
    assert key == "a long shared key"
    return HASH


def test_the_helper_writes_only_the_hash_and_a_pass_600(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written = access_key.set_key(
        tmp_path, user="demo", ask=_Asked("a long shared key", "a long shared key"), hasher=_hasher
    )
    assert written == tmp_path / access_key.PENDING_FILE
    assert stat.S_IMODE(written.stat().st_mode) == 0o600
    text = written.read_text(encoding="utf-8")
    assert f"\tdemo {HASH}\n" in text
    assert "a long shared key" not in text
    said = capsys.readouterr()
    assert HASH not in said.out + said.err and "a long shared key" not in said.out + said.err
    assert "ospreyflow apply" in said.out


def test_two_answers_that_differ_write_nothing(tmp_path: Path) -> None:
    with pytest.raises(access_key.KeyRefused, match="did not match"):
        access_key.set_key(tmp_path, user="demo", ask=_Asked("a long shared key", "another one!!"),
                           hasher=_hasher)  # fmt: skip
    assert not (tmp_path / access_key.PENDING_FILE).exists()


@pytest.mark.parametrize("key", ["", "short", "   twelve    "])
def test_a_key_of_fewer_than_twelve_characters_is_refused(tmp_path: Path, key: str) -> None:
    with pytest.raises(access_key.KeyRefused, match="at least 12"):
        access_key.set_key(tmp_path, user="demo", ask=_Asked(key, key), hasher=_hasher)
    assert not (tmp_path / access_key.PENDING_FILE).exists()


def test_each_setting_gives_a_new_pass(tmp_path: Path) -> None:
    def ask() -> _Asked:
        return _Asked("a long shared key", "a long shared key")

    access_key.set_key(tmp_path, user="demo", ask=ask(), hasher=_hasher)
    access_key.carry_into(tmp_path, tmp_path)
    first = access_key.pass_token(tmp_path)
    access_key.set_key(tmp_path, user="demo", ask=ask(), hasher=_hasher)
    access_key.carry_into(tmp_path, tmp_path)
    assert first and access_key.pass_token(tmp_path) not in (None, first)


def test_a_hash_that_is_not_bcrypt_is_never_written(tmp_path: Path) -> None:
    with pytest.raises(access_key.KeyRefused, match="bcrypt"):
        access_key.set_key(tmp_path, user="demo", ask=_Asked("a long shared key", "a long shared key"),
                           hasher=lambda _key: "$argon2id$v=19$m=47104,t=1,p=1$abc")  # fmt: skip


def test_the_proxy_images_own_hasher_is_given_the_key_on_standard_input_alone() -> None:
    seen: dict[str, object] = {}

    def run(argv: list[str], **kwargs: object) -> object:
        seen["argv"], seen["input"] = argv, kwargs.get("input")

        class Done:
            returncode = 0
            stdout = HASH + "\n"
            stderr = ""

        return Done()

    assert access_key.caddy_hasher(run=run)("a long shared key") == HASH
    assert "a long shared key" not in " ".join(seen["argv"])  # type: ignore[arg-type]
    assert seen["input"] == "a long shared key\n"
    assert seen["argv"][-3:] == ["hash-password", "--algorithm", "bcrypt"]  # type: ignore[index]


# --- Preflight ------------------------------------------------------------------------------------


def _written(directory: Path) -> Path:
    """Set, then carried into place as `ospreyflow apply` does."""
    access_key.set_key(directory, user="demo", ask=_Asked("a long shared key", "a long shared key"),
                       hasher=_hasher)  # fmt: skip
    access_key.carry_into(directory, directory)
    return directory / access_key.ACCESS_KEY_FILE


# --- `ospreyflow apply` carries it into place -----------------------------------------------------


def test_apply_carries_a_newly_set_key_into_the_stage_600_and_settles_it_after(
    tmp_path: Path,
) -> None:
    live, stage = tmp_path / "live", tmp_path / "stage"
    stage.mkdir()
    access_key.set_key(live, user="demo", ask=_Asked("a long shared key", "a long shared key"),
                       hasher=_hasher)  # fmt: skip
    access_key.carry_into(stage, live)
    carried = stage / access_key.ACCESS_KEY_FILE
    assert stat.S_IMODE(carried.stat().st_mode) == 0o600
    assert carried.read_bytes() == (live / access_key.PENDING_FILE).read_bytes()
    access_key.settle(live)
    assert not (live / access_key.PENDING_FILE).exists()


def test_apply_carries_the_key_in_place_when_none_is_newly_set(tmp_path: Path) -> None:
    live, stage = tmp_path / "live", tmp_path / "stage"
    stage.mkdir()
    _written(live)
    access_key.carry_into(stage, live)
    assert (stage / access_key.ACCESS_KEY_FILE).read_bytes() == (
        live / access_key.ACCESS_KEY_FILE
    ).read_bytes()


def test_a_key_set_again_restarts_the_proxy(tmp_path: Path) -> None:
    """`services_to_restart` restarts a service whose mounted file changed between the deployment
    and its stage: a new key is such a change, so the proxy reads it."""
    from harness.apply import services_to_restart

    live, stage = tmp_path / "live", tmp_path / "stage"
    rendered = render(_config(access_key=True), allow_unpinned=True)
    for folder in (live, stage):
        folder.mkdir()
        for name, text in rendered.artefacts.items():
            (folder / name).write_text(text, encoding="utf-8")
    _written(live)
    access_key.set_key(live, user="demo", ask=_Asked("a long shared key", "a long shared key"),
                       hasher=_hasher)  # fmt: skip
    access_key.carry_into(stage, live)
    assert "proxy" in services_to_restart(live, stage)


def _preflight(directory: Path, config: OspreyConfig) -> object:
    return access_key_check.check(PreflightContext(config=config, out_dir=directory))


def test_preflight_passes_a_deployment_that_does_not_ask(tmp_path: Path) -> None:
    assert _preflight(tmp_path, _config()).status is Status.SKIP


def test_preflight_refuses_a_deployment_that_asks_with_no_key_set(tmp_path: Path) -> None:
    result = _preflight(tmp_path, _config(access_key=True))
    assert result.status is Status.FAIL
    assert "python -m harness.access_key set" in result.what_to_do


def test_preflight_refuses_a_key_file_others_may_read(tmp_path: Path) -> None:
    os.chmod(_written(tmp_path), 0o640)
    result = _preflight(tmp_path, _config(access_key=True))
    assert result.status is Status.FAIL and "600" in result.what_is_wrong


def test_preflight_refuses_a_file_not_written_by_the_helper_and_never_quotes_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / access_key.ACCESS_KEY_FILE
    path.write_text(f"basic_auth {{\n\tdemo {HASH}\n}}\n", encoding="utf-8")
    os.chmod(path, 0o600)
    result = _preflight(tmp_path, _config(access_key=True))
    assert result.status is Status.FAIL
    assert HASH not in result.what_is_wrong + result.what_to_do + " ".join(result.detail)


def test_preflight_passes_the_helpers_file(tmp_path: Path) -> None:
    _written(tmp_path)
    assert _preflight(tmp_path, _config(access_key=True)).status is Status.PASS


# --- The tools on the server pass it as a browser does --------------------------------------------


def _https_handler() -> urllib.request.HTTPSHandler:
    """The HTTPS handler of an opener as `urlopen` builds one: its own `https_request`."""
    opener = urllib.request.build_opener()
    return next(h for h in opener.handlers if isinstance(h, urllib.request.HTTPSHandler))


def test_a_host_tool_presents_the_pass_to_the_deployments_names_alone(tmp_path: Path) -> None:
    _written(tmp_path)
    token = access_key.pass_token(tmp_path)
    site.carry_the_pass(_config(access_key=True), tmp_path)
    try:
        handler = _https_handler()
        for host, carried in (("demo.example.org", True), ("id.demo.example.org", True),
                              ("bi.demo.example.org", True),
                              ("elsewhere.example.org", False)):  # fmt: skip
            request = urllib.request.Request(f"https://{host}/x")
            handler.https_request(request)
            cookie = request.get_header("Cookie") or ""
            assert (f"{access_key.PASS_COOKIE}={token}" in cookie) is carried, host
    finally:
        site.forget_the_passes()


def test_a_tool_that_cannot_read_the_file_carries_nothing(tmp_path: Path) -> None:
    site.carry_the_pass(_config(access_key=True), tmp_path)  # no file
    try:
        request = urllib.request.Request("https://demo.example.org/x")
        _https_handler().https_request(request)
        assert request.get_header("Cookie") is None
    finally:
        site.forget_the_passes()


def test_the_helpers_own_words_never_hold_the_key_or_hash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = access_key.main(["set", str(tmp_path), "--user", "demo"],
                           ask=_Asked("a long shared key", "a long shared key"), hasher=_hasher)  # fmt: skip
    said = capsys.readouterr()
    assert code == 0
    assert HASH not in said.out + said.err and "a long shared key" not in said.out + said.err
    assert io.StringIO(said.out).read().strip()


def test_every_tool_that_finds_the_deployment_by_its_settings_carries_the_pass(
    tmp_path: Path,
) -> None:
    """Backup, restore and the sign-in registration find the identity provider through
    `deployment_origins`; it carries the pass of the deployment whose settings it reads."""
    import yaml

    _written(tmp_path)
    (tmp_path / "osprey.yaml").write_text(
        yaml.safe_dump(
            {"profile": "small", "network": {"public_origin": ORIGIN, "access_key": True}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "deployment.env").write_text("OSPREY_IDENTITY_ORIGIN=https://id.demo.example.org\n",
                                             encoding="utf-8")  # fmt: skip
    try:
        assert (
            site.deployment_origins(tmp_path / "deployment.env")[1] == "https://id.demo.example.org"
        )
        request = urllib.request.Request("https://id.demo.example.org/admin/realms/osprey")
        _https_handler().https_request(request)
        assert (
            request.get_header("Cookie")
            == f"{access_key.PASS_COOKIE}={access_key.pass_token(tmp_path)}"
        )
    finally:
        site.forget_the_passes()


def test_unset_no_dump_of_the_settings_names_it() -> None:
    """The cluster's and the cloud platform's values carry `osprey.yaml` as dumped: a deployment
    that does not ask renders byte for byte what it did (found by `gate/B-unset-renders.py`)."""
    assert "access_key" not in _config().model_dump(mode="json", exclude_none=True)["network"]
    assert _config(access_key=True).model_dump(mode="json")["network"]["access_key"] is True
