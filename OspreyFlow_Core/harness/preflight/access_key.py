"""The shared key is set before a deployment that asks for it starts (`06_DECISIONS.md` ADR-114
Amendment 41).

`network.access_key: true` renders a Caddyfile that imports `access-key.caddy` from the deployment's
folder; without it the proxy does not start, so the deployment answers nothing at all. This check
says so before anything starts, and refuses a file others may read or one the helper did not write.
It never quotes the file: what it holds is the key's hash and the pass.
"""

from __future__ import annotations

from harness.access_key import ACCESS_KEY_FILE, KeyRefused, read
from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed, skipped

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
    return passed(NAME, detail=(f"the front proxy asks for the shared key (user name {user!r})",))
