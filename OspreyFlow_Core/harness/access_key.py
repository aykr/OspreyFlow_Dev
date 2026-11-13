"""The shared key the front proxy asks for (`06_DECISIONS.md` ADR-114 Amendment 41).

`network.access_key: true` in `osprey.yaml` says a deployment asks every browser for a shared key,
the browser's own user name and key box, on all three names, before any page, asset, sign-in or API
answer. This module is the owner's half on the server:

    python -m harness.access_key set <the deployment's folder> [--user demo]

reads the key twice without echo, hashes it with the proxy image's own `caddy hash-password`
(bcrypt; the key goes in on standard input, never on a command line), and writes
`access-key.caddy.pending` in the deployment's folder, readable by its owner alone (`600`). It
holds the user name, the hash and a new random pass, never the key. `ospreyflow apply` then carries
it into place as `access-key.caddy` and restarts the proxy, which imports it
(`harness.site.render_caddyfile`) and mounts it alone.

**The pass.** A browser that has answered with the key is given a cookie for that name alone
(`osprey_pass`, host-only, HttpOnly, Secure, SameSite=Lax, eight hours), so it is asked once a
name, and its own requests that carry a token of their own (the Glass's API, its WebSocket) or come
from a frame still pass. The pass is a random value of its own, replaced each time the key is set;
it is not the key. The tools on the server that reach the deployment by name read it from the same
file (`harness.site.carry_the_pass`), as the owner who can read the file.

Nothing here prints the key or the hash.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from schemas.deployment import OspreyConfig

#: In the deployment's own folder, beside `compose.yaml`: the file the proxy imports.
ACCESS_KEY_FILE = "access-key.caddy"
#: What `set` writes; `ospreyflow apply` carries it into place (`harness.apply.carry_access_key`).
PENDING_FILE = f"{ACCESS_KEY_FILE}.pending"
#: Where the proxy sees it, read-only.
IN_PROXY = "/etc/caddy/access-key.caddy"
#: The session cookie a browser is given once it has answered with the key.
PASS_COOKIE = "osprey_pass"
#: How long a pass lasts in a browser: a working day. Host-only (no `Domain`), so it is sent back to
#: the one name that gave it, never to another subdomain; each of the three names asks once.
PASS_SECONDS = 8 * 60 * 60
#: The fewest characters a key may have.
SHORTEST = 12

_BCRYPT = re.compile(r"^\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}$")
_USER = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_HEAD = (
    "# Written by `python -m harness.access_key set` (ADR-114 Amendment 41): the shared key's\n"
    "# bcrypt hash and the pass a browser is given once it has answered; never the key itself.\n"
    "# Readable by its owner alone. Set it again with the same command; never edit it by hand.\n"
)


class KeyRefused(Exception):
    """A key, an answer or a file refused, in words that never hold the key or its hash."""


def snippet(user: str, hashed: str, token: str) -> str:
    """The file's whole text: three Caddyfile snippets the rendered Caddyfile imports by name."""
    cookie = f"{PASS_COOKIE}={token}"
    return (
        _HEAD
        + "(osprey_access_key) {\n"
        + f"\t{user} {hashed}\n"
        + "}\n"
        + "(osprey_access_pass) {\n"
        + f"\theader Cookie *{cookie}*\n"
        + "}\n"
        + "(osprey_access_pass_set) {\n"
        + f'\theader @osprey_answered +Set-Cookie "{cookie}; Path=/; Max-Age={PASS_SECONDS}; '
        + "Secure; "
        + 'HttpOnly; SameSite=Lax"\n'
        + "}\n"
    )


_SHAPE = re.compile(
    r"\(osprey_access_key\) \{\n\t(?P<user>\S+) (?P<hash>\S+)\n\}\n"
    r"\(osprey_access_pass\) \{\n\theader Cookie \*" + PASS_COOKIE + r"=(?P<token>[^*\s]+)\*\n"
)


def read(path: Path) -> tuple[str, str, str]:
    """`(user, hash, pass)` from a file `set` wrote, or `KeyRefused` naming what is wrong (never
    its content): not the helper's shape, or not readable by its owner alone."""
    try:
        mode = path.stat().st_mode & 0o777
        text = path.read_text(encoding="utf-8")
    except OSError as unread:
        raise KeyRefused(f"{path} cannot be read ({unread.strerror})") from None
    if mode & 0o077:
        raise KeyRefused(f"{path} is readable by others (mode {mode:o}); it must be 600")
    found = _SHAPE.search(text)
    if found is None:
        raise KeyRefused(f"{path} is not a file `python -m harness.access_key set` wrote")
    user, hashed, token = found["user"], found["hash"], found["token"]
    if not (_USER.match(user) and _BCRYPT.match(hashed) and _TOKEN.match(token)):
        raise KeyRefused(f"{path} is not a file `python -m harness.access_key set` wrote")
    if text != snippet(user, hashed, token):
        raise KeyRefused(f"{path} has been edited by hand; set the key again")
    return user, hashed, token


def pass_token(directory: Path) -> str | None:
    """The pass in the deployment's key file in `directory`, or None (no file, not readable)."""
    try:
        return read(directory / ACCESS_KEY_FILE)[2]
    except KeyRefused:
        return None


def proxy_owner(config: OspreyConfig) -> tuple[int, int] | None:
    """The account the front proxy runs as, when it is not root: on a Small with the organisation's
    own certificate, the owner of `network.tls.key` (ADR-114 Amendment 33, `OSPREY_PROXY_UID`). The
    key file, `600`, must be that account's, or the proxy cannot read it and does not start. None
    when the proxy runs as root (Caddy's own certificates), which reads it whoever owns it."""
    tls = config.network.tls
    if tls is None:
        return None
    owner = Path(tls.key).stat()
    return owner.st_uid, owner.st_gid


def _give(path: Path, owner: tuple[int, int] | None) -> None:
    """`path` handed to `owner`, when it is not already theirs: possible as root (`sudo ospreyflow
    apply`) or as that account itself; otherwise left, and preflight says so in words."""
    if owner is None or not path.is_file():
        return
    held = path.stat()
    if (held.st_uid, held.st_gid) == owner:
        return
    try:
        os.chown(path, *owner)
    except PermissionError:
        pass


def carry_into(stage: Path, out_dir: Path, owner: tuple[int, int] | None = None) -> None:
    """`ospreyflow apply`'s half: the key newly set in the deployment's folder (the pending file),
    else the one in place, copied into the staging folder as the file the proxy imports, its mode
    with it, and handed to the account the proxy runs as (`proxy_owner`). Preflight then reads it
    there, and moving the stage into place puts it beside `compose.yaml`, in place (the proxy mounts
    it); a key newly set differs from the one in place, so the proxy is restarted and reads it.
    Nothing when neither exists. Refused, in words, when a folder stands where the file should be
    (left by an older start without the key)."""
    import shutil

    in_place = out_dir / ACCESS_KEY_FILE
    if in_place.is_dir():
        raise KeyRefused(
            f"{in_place} is a folder, not the key file (left by a start without the key); remove "
            "it, set the key again and run `ospreyflow apply`"
        )
    for source in (out_dir / PENDING_FILE, in_place):
        if source.is_file():
            shutil.copy2(source, stage / ACCESS_KEY_FILE)
            _give(stage / ACCESS_KEY_FILE, owner)
            return


def settle(out_dir: Path, owner: tuple[int, int] | None = None) -> None:
    """Once the stage is in place, the pending key is the key in place: the pending file goes, and
    the key in place is the proxy's account's (a file the move made new is the runner's)."""
    (out_dir / PENDING_FILE).unlink(missing_ok=True)
    _give(out_dir / ACCESS_KEY_FILE, owner)


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def caddy_hasher(run: Runner = subprocess.run, image: str | None = None) -> Callable[[str], str]:
    """Hashes a key with the proxy image's own `caddy hash-password` (bcrypt), so the hash is the
    one the proxy checks against. The key goes in on standard input with its newline, as `caddy`
    reads it (measured against Caddy 2.11.4: without the newline it answers "EOF")."""
    if image is None:
        from harness.site import PROXY_IMAGE

        image = PROXY_IMAGE

    def hasher(key: str) -> str:
        done = run(
            [
                "docker",
                "run",
                "--rm",
                "-i",
                image,
                "caddy",
                "hash-password",
                "--algorithm",
                "bcrypt",
            ],
            input=key + "\n",
            capture_output=True,
            text=True,
            timeout=300,
        )
        if done.returncode != 0:
            raise KeyRefused(
                f"the proxy image ({image}) could not hash the key (exit {done.returncode}); is "
                "Docker running, and the image pulled?"
            )
        return str(done.stdout).strip()

    return hasher


def set_key(
    directory: Path,
    *,
    user: str = "demo",
    ask: Callable[[str], str] = getpass.getpass,
    hasher: Callable[[str], str] | None = None,
) -> Path:
    """Asks for the key twice, hashes it and writes the pending file (`600`) in `directory`.
    Returns its path. Says, on standard output, what to run next; never the key or its hash."""
    if not _USER.match(user):
        raise KeyRefused("the user name is letters, digits, '.', '_' or '-', at most 64")
    first = ask("Shared key: ")
    again = ask("The same key again: ")
    if first != again:
        raise KeyRefused("the two keys did not match; nothing was written")
    if len(first.strip()) < SHORTEST:
        raise KeyRefused(
            f"a key has at least {SHORTEST} characters, not counting spaces at either end"
        )
    if first != first.strip() or "\n" in first or "\r" in first:
        raise KeyRefused("a key has no spaces at either end and no line breaks")
    hashed = (hasher or caddy_hasher())(first)
    if not _BCRYPT.match(hashed):
        raise KeyRefused("the hasher did not answer with a bcrypt hash; nothing was written")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = directory / PENDING_FILE
    from harness.atomic import replace_whole

    # Whole or not at all, `600` from the start; nothing mounts the pending file.
    text = snippet(user, hashed, secrets.token_urlsafe(32))
    replace_whole(target, text.encode("utf-8"), mode=0o600)
    print(
        f"The key's hash is written to {target} (readable by its owner alone).\n"
        "Now run `ospreyflow apply`: it puts the key in place and restarts the front proxy. Give "
        f"people the user name {user!r} and the key, by a route other than this deployment."
    )
    return target


def main(
    argv: list[str] | None = None,
    *,
    ask: Callable[[str], str] = getpass.getpass,
    hasher: Callable[[str], str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m harness.access_key",
        description="Set the shared key the front proxy asks for (ADR-114 Amendment 41).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    setting = commands.add_parser("set", help="ask for the key and write its hash for the proxy")
    setting.add_argument(
        "directory", type=Path, help="the deployment's folder (beside compose.yaml)"
    )
    setting.add_argument("--user", default="demo", help="the user name people give (default: demo)")
    args = parser.parse_args(argv)
    try:
        set_key(args.directory, user=args.user, ask=ask, hasher=hasher)
    except KeyRefused as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
