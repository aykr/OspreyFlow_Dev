"""`06_DECISIONS.md` ADR-049 Stage 2 §6 / `DECISIONS.md` ruling R1 — "its server side is a Python
HTTP layer inside the harness package, in the existing harness image, exposing the existing engine
as JSON." This is that layer, part A's own scope: the Profile/Components/Models screens.

**§2.3's own rule, checked at every route below: "the UI never has a capability the headless path
lacks."** Every route here is a JSON wrapper around a function `apps/harness` could not otherwise
reach and a human already can from the CLI — never a capability invented for the browser alone.
The map, current as of this round:

| Route | Headless equivalent |
| --- | --- |
| `GET /api/config` | `harness.render.load_config` (schema defaults if no file yet) |
| `PUT /api/config` | Hand-editing `osprey.yaml`, re-validated — `OspreyConfig.model_validate` |
| `GET /api/profile-options/{profile}` | `harness.screens.profile_options` — a §1 table lookup |
| `POST /api/consequences` | `harness.screens.consequences_for` — a pure computation |
| `GET /admin` | A placeholder for `Stage 2 §6` part B's console, gated already |

Preflight, Apply, Backup, Restore and Bundle are not exposed here — those screens are not this
round's scope (queue brief: "Not in this round: Governance, Geospatial, Preflight, Launch").
"""

from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from harness.render import DEFAULT_CONFIG_PATH
from harness.screens import (
    Consequences,
    ProfileFootprint,
    consequences_for,
    invalid_components_for_profile,
    profile_options,
)
from harness.webapp_auth import loopback_only_middleware, require_admin_role
from schemas.deployment import OspreyConfig, Profile

#: The built frontend's own output directory — `apps/harness/dist`, present once `npm run build`
#: has run. Absent on a bare checkout (e.g. every Python-only test in this file), and that is a
#: real state, not an error: `create_app` serves the API alone until it exists, the same
#: "everything it produces is a file in the repo" property `05_DEPLOYMENT.md` §2.5 already states.
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "apps" / "harness" / "dist"


def _read_config(config_path: Path) -> OspreyConfig:
    if not config_path.exists():
        return OspreyConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return OspreyConfig.model_validate(raw)


def _write_config(config_path: Path, config: OspreyConfig) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json", exclude_none=True), sort_keys=False),
        encoding="utf-8",
    )


def _footprint_json(footprint: ProfileFootprint) -> dict[str, Any]:
    return {
        "label": footprint.label,
        "machines": footprint.machines,
        "memory_gb_floor": footprint.memory_gb_floor,
        "orchestrator": footprint.orchestrator,
        "allowed_graph_stores": [g.value for g in footprint.allowed_graph_stores],
        "allowed_analytics_engines": [a.value for a in footprint.allowed_analytics_engines],
    }


def _consequences_json(consequences: Consequences) -> dict[str, Any]:
    return {
        "profile": consequences.profile.value,
        "machines": consequences.machines,
        "memory_gb_floor": consequences.memory_gb_floor,
        "orchestrator": consequences.orchestrator,
        "graph_store": consequences.graph_store.value,
        "analytics_engine": consequences.analytics_engine.value,
        "egress_exception": consequences.egress_exception,
        "egress_detail": consequences.egress_detail,
    }


def create_app(*, config_path: Path = DEFAULT_CONFIG_PATH) -> FastAPI:
    app = FastAPI(title="OspreyFlow setup harness")

    # Setup mode's own second layer of defence — R2, `webapp_auth.loopback_only_middleware`'s own
    # docstring has the full reasoning (the bootstrap command's `-p 127.0.0.1:...` is the first).
    app.middleware("http")(loopback_only_middleware)
    # The browser app and this API are same-origin once `apps/harness/dist` is served alongside it
    # (below); CORS is permissive only for `npm run dev`'s own separate Vite port during
    # development, and setup mode's own loopback-only refusal already bounds who can reach either.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5190", "http://127.0.0.1:5190"],
        allow_methods=["GET", "PUT", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/config")
    def get_config() -> dict[str, Any]:
        return _read_config(config_path).model_dump(mode="json", exclude_none=True)

    @app.put("/api/config")
    def put_config(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
        """Merge semantics, not replace: `05_DEPLOYMENT.md` §2.1's own screens are "navigable in
        any order", each writing its own top-level section (`profile`, `components`, `models`, ...)
        — a screen submitting its own answer must not erase what another screen already wrote.
        Unknown top-level keys are rejected by `OspreyConfig`'s own `extra="forbid"` once merged,
        the same schema-only validation `05_DEPLOYMENT.md` §2.1 asks for; the response is that
        validation's own error, shown next to the field it named."""
        current = _read_config(config_path).model_dump(mode="json", exclude_none=True)
        merged = copy.deepcopy(current)
        for key, value in patch.items():
            merged[key] = value
        try:
            config = OspreyConfig.model_validate(merged)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc

        # §2.1's own filtering rule, not expressible in `ComponentsConfig` alone (it has no
        # `profile` field to check against) — checked here, the one place both fields are in
        # scope together.
        problems = invalid_components_for_profile(
            config.profile, config.components.graph_store, config.components.analytics_engine
        )
        if problems:
            raise HTTPException(status_code=422, detail=problems)

        _write_config(config_path, config)
        return config.model_dump(mode="json", exclude_none=True)

    @app.get("/api/profile-options/{profile}")
    def get_profile_options(profile: Profile) -> dict[str, Any]:
        return _footprint_json(profile_options(profile))

    @app.post("/api/consequences")
    def post_consequences(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            config = OspreyConfig.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        return _consequences_json(consequences_for(config))

    @app.get("/admin", dependencies=[Depends(require_admin_role)])
    def admin_placeholder() -> dict[str, str]:
        """`Stage 2 §6` part B builds the real console; this is the route amendment 22's own
        access-control test protects starting now, so part B adds screens behind an already-proven
        gate rather than building the gate and the console in the same change."""
        return {"status": "post-launch admin console not yet built (Stage 2 §6 part B)"}

    if FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")

    return app


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness",
        description="The browser setup harness — Stage 2 §6. No subcommand starts this server.",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",  # noqa: S104 - see the docstring below for why this is the correct default
        help=(
            "05_DEPLOYMENT.md §2's own bootstrap command restricts reachability at the docker "
            "port-publish (`-p 127.0.0.1:7000:7000`, per ruling R2), not at this process's own "
            "bind — found running the real image: bridge-mode port publishing cannot deliver "
            "traffic to a process bound only to loopback inside its own container network "
            "namespace, which made the documented command serve nothing at all."
        ),
    )
    parser.add_argument("--port", type=int, default=7000, help="05_DEPLOYMENT.md §2's own default.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    args = _parse_args(argv if argv is not None else sys.argv[1:])
    app = create_app(config_path=args.config)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
