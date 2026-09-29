"""`OIDC_AUDIENCE` must be set in the rendered environment — `06_DECISIONS.md` ADR-050 objection 1's
resolution, restated as a gate rather than a promise.

**Why this lives in Preflight and not in `services/api/auth.py`.** The Conduit's own
`PrincipalResolver.resolve()` already verifies the audience unconditionally *whenever one is
configured* — that code is correct and untouched by this ADR. The gap ADR-050 found was
operational, not logical: no rendered deployment ever set `OIDC_AUDIENCE` at all, so `verify_aud`
was always off in practice, and a public client (the Glass) makes that reachable from a browser
in a way two confidential clients we control never did. The fix is that every rendered deployment
carries the variable — `harness/render.py`'s `_render_env` writes it — and this check is what makes
a deployment that somehow doesn't fail *before* Launch rather than silently accept any token the
realm signs.

A missing `OIDC_AUDIENCE` is a **Preflight fail**, not a silent fallback to off: `CLAUDE.md` rule 15
names exactly this shape — a check that could not detect its own violation is not a check.
"""

from __future__ import annotations

from pathlib import Path

from harness.preflight.context import PreflightContext
from harness.preflight.result import CheckResult, failed, passed
from harness.realm import CONDUIT_CLIENT_ID

NAME = "oidc-audience"


def _read_env_value(env_path: Path, variable: str) -> str | None:
    if not env_path.is_file():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{variable}="):
            return line.split("=", 1)[1].strip()
    return None


def check(context: PreflightContext) -> CheckResult:
    env_path = context.out_dir / "deployment.env"
    value = _read_env_value(env_path, "OIDC_AUDIENCE")

    if not value:
        return failed(
            NAME,
            what_is_wrong=(
                f"OIDC_AUDIENCE is not set in {env_path} — the Conduit's own `verify_aud` check "
                "is off, so it accepts a token the realm signs for any client, not only the Glass "
                "and the Conduit's own service account. `06_DECISIONS.md` ADR-050 objection 1."
            ),
            what_to_do=(
                "Re-render this deployment (`python -m harness.render` or `python -m "
                "harness.apply`) — a current renderer always writes OIDC_AUDIENCE. If it is still "
                "missing after a fresh render, this is a defect in the renderer, not something to "
                "work around here."
            ),
        )

    if value != CONDUIT_CLIENT_ID:
        return failed(
            NAME,
            what_is_wrong=(
                f"OIDC_AUDIENCE is {value!r} in {env_path}, not the Conduit's own client id "
                f"{CONDUIT_CLIENT_ID!r} — the realm's audience mapper on the Glass client "
                "(harness/realm.py's own `_audience_mapper`) names the Conduit specifically, so a "
                "different value here means every real sign-in is refused, not only a forged token."
            ),
            what_to_do="Re-render this deployment rather than hand-editing the environment file.",
        )

    return passed(NAME, detail=(f"OIDC_AUDIENCE={value}",))
