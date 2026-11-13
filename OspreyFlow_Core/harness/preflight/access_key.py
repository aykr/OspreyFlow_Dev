"""The shared key is set before a deployment that asks for it starts (`06_DECISIONS.md` ADR-114
Amendment 41).

`network.access_key: true` renders a Caddyfile that imports `access-key.caddy` from the deployment's
folder; without it the proxy does not start, so the deployment answers nothing at all. This check
says so before anything starts, and refuses a file others may read or one the helper did not write.
It never quotes the file: what it holds is the key's hash and the pass.
"""

from __future__ import annotations

from harness.access_key import ACCESS_KEY_FILE, KeyRefused, proxy_owner, read
from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped, warned
from harness.site import sites

#: Second-level names under which a registrable domain has three labels (a short list, not the
#: public suffix list: enough to tell `demo.example.co.uk` from `example.co.uk`).
_TWO_LABEL_SUFFIXES = {"co.uk", "org.uk", "gov.uk", "ac.uk", "ltd.uk", "plc.uk", "nhs.uk",
                       "police.uk", "com.au", "co.nz"}  # fmt: skip


def registrable(host: str) -> bool:
    """Whether `host` is itself an organisation's registrable domain (`example.org`,
    `example.co.uk`), so a cookie for it reaches every name the organisation has under it."""
    labels = host.lower().rstrip(".").split(".")
    if len(labels) <= 2:
        return True
    return len(labels) == 3 and ".".join(labels[1:]) in _TWO_LABEL_SUFFIXES


NAME = "access-key"

_SET = (
    "Set the key on this server: `python -m harness.access_key set <the deployment's folder>`, "
    "then run `ospreyflow apply` again."
)


def check(context: PreflightContext) -> CheckResult:
    if not context.config.network.access_key:
        return skipped(NAME, reason="this deployment does not ask for a shared key")
    path = context.out_dir / ACCESS_KEY_FILE
    if not path.exists():
        return failed(
            NAME,
            what_is_wrong=(
                "network.access_key asks for a shared key, and none is set: the front proxy would "
                "not start"
            ),
            what_to_do=_SET,
        )
    try:
        user, _hash, _pass = read(path)
    except KeyRefused as refused:
        return failed(NAME, what_is_wrong=str(refused), what_to_do=_SET)
    owner = proxy_owner(context.config)
    held = path.stat()
    if owner is not None and held.st_uid != owner[0]:
        return failed(
            NAME,
            what_is_wrong=(
                f"the front proxy runs as uid {owner[0]} (the owner of network.tls.key), and "
                f"the key file belongs to uid {held.st_uid}: readable by its owner alone, the "
                "proxy could not read it and would not start"
            ),
            what_to_do=(
                "Run `ospreyflow apply` with sudo, which hands the file to the proxy's account, "
                "or "
                f"run `chown {owner[0]}:{owner[1]}` on {ACCESS_KEY_FILE} in the deployment's "
                "folder."
            ),
        )
    said = f"the front proxy asks for the shared key (user name {user!r})"
    host = sites(context.config).host
    if registrable(host):
        # ADR-114 Amendment 42: the pass is kept for the deployment's base name, and here that is
        # the organisation's whole domain.
        return warned(
            NAME,
            what_is_wrong=(
                f"the deployment's address, {host}, is a whole domain: the pass a browser is given "
                f"once it has answered the key is sent to every name under {host}, including names "
                "other services answer, any of which could pass it on"
            ),
            what_to_do=(
                "Give this deployment an address of its own under the domain (for example "
                f"demo.{host}), or accept that every name under {host} is trusted with the pass."
            ),
            detail=(said,),
        )
    return passed(NAME, detail=(said,))
