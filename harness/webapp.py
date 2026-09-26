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
| `GET /api/real-data-exceptions` | `scripts.real_data_exceptions.load_exceptions` |
| `POST /api/real-data-exceptions` | `scripts.real_data_exceptions.add_exception` (CLI's `add`) |
| `DELETE /api/real-data-exceptions/{dataset}` | `scripts.real_data_exceptions.remove_exception` |
| `POST /api/geospatial/register-provider` | `harness.geospatial.register_provider_step` (real) |
| `POST /api/geospatial/build-basemap` | `harness.geospatial.build_basemap_step` — always 501 |
| `POST /api/geospatial/verify` | `harness.geospatial.verify_step` — always 501 |
| `GET /api/preflight/stream` | `harness.preflight.__main__.run_streaming` — real, live |
| `POST /api/artefacts/generate` | `harness.render.render` + `diff_for` + `write` |
| `GET /api/artefacts` | The last `generate`'s own result, held in `app.state` |
| `GET /api/artefacts/{name}` | One artefact's own content, for download |
| `POST /api/artefacts/confirm` | No CLI equivalent — an acknowledgement gate over state above |
| `GET /admin` | A placeholder for `Stage 2 §6` part B's console, gated already |

The Governance screen's own config fields (`identity_provider`, `handling_scheme`, `ontology`,
`real_data_exceptions` path) need no new route — they are a `GovernanceConfig` section like any
other, written through the existing `PUT /api/config`. Only the exceptions panel over
`scripts/real_data_exceptions.py` (ADR-049 Stage 2 §6, "hosts the real-data exceptions panel")
needs its own routes, above.

**This module never admits a real dataset itself.** The three routes above read and write
`config/real_data_exceptions.yaml` at the path `scripts.real_data_exceptions.CONFIG_PATH` already
uses — the owner's own local, gitignored file — the same fail-closed module `CLAUDE.md` rule 9 and
`06_DECISIONS.md` ADR-035 §C3 already govern. `load_exceptions` raises (`KeyError` for an entry
missing a required field, `ValueError` for one that fails a field's own format check) rather than
silently dropping a malformed entry; `get_real_data_exceptions` surfaces that verbatim as a 422
rather than swallowing it, per `CLAUDE.md` rule 2. **Any entry in an existing local
`config/real_data_exceptions.yaml` that predates `decision_record` (added 26 September 2026,
`06_DECISIONS.md` ADR-049 Stage 2 §6 ruling 3) is invalid until the owner adds it by hand — this
module cannot see that gitignored file from here and must not try to migrate it.**

`build-basemap` and `verify` always return 501 — `harness/geospatial.py`'s own docstring has the
real, confirmed-by-import reason (both real functions pull in `services`/`adapters` modules
`harness/Dockerfile` does not copy into this image), recorded as **Proposed, not decided** in
`07_BUILD_PLAN.md`'s Stage 2 §6 part-B entry rather than silently worked around.

**Preflight streams as Server-Sent Events, not a polled job.** Every check
(`harness.preflight.ALL_CHECKS`) is already a plain, fast, synchronous function of a
`PreflightContext` — there is no job to poll for, no cancellation, no work worth doing between
polls, and `harness.preflight.__main__.run_streaming` (this round's own addition, alongside the
existing `run`) already yields one `CheckResult` per check as it completes. `text/event-stream`
turns that generator into the wire format with nothing invented in between; a browser's native
`EventSource` (or a plain `fetch` reading the body, used here so `?only=`/`?seeding=` query
parameters and a same-origin request need no second mechanism) is exactly "each check appears as
it completes" (`05_DEPLOYMENT.md` §2.1), not a screen-only capability.

**The artefacts diff, before anything runs.** `POST /api/artefacts/generate` calls
`harness.render.render` (the real digest resolver by default — `--allow-unpinned`'s own webapp
equivalent is not exposed, so a machine with no reachable Docker daemon gets the same
`UnpinnedImagesError` the CLI would, not a silently permissive default), computes `diff_for`
against whatever is already on disk **before** writing (§2.4's own "before it runs, as a diff
against the current state"), then writes. `GET /api/artefacts`/`GET /api/artefacts/{name}` read
back what the last `generate` produced, held in `app.state` — nothing here is a second copy of the
rendered content, only a reference to it. `POST /api/artefacts/confirm` has no CLI equivalent and
is not a §2.3 violation for lacking one: it invents no capability over the deployment, only an
acknowledgement flag Launch (round 03d) will consult, the same kind of interactive-only state a
"Save" button's own click already is.

Launch, Backup and Restore are not exposed here — those screens are not this round's scope (queue
brief: `queue/03c-screens-B-preflight-diff.md` covers items 3–4 only; Launch is `03d`).
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from scripts.real_data_exceptions import (
    CONFIG_PATH as REAL_DATA_EXCEPTIONS_PATH,
)
from scripts.real_data_exceptions import (
    RealDataException,
    add_exception,
    load_exceptions,
    remove_exception,
)

from harness.geospatial import (
    GeospatialError,
    build_basemap_step,
    register_provider_step,
    verify_step,
)
from harness.images import DigestResolver
from harness.preflight import CHECKS_BY_NAME
from harness.preflight.__main__ import run_streaming
from harness.preflight.context import PreflightContext
from harness.render import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_OUT_ROOT,
    ClusterRendererNotBuilt,
    MissingDockerfileError,
    UnpinnedImagesError,
    diff_for,
    render,
    write,
    write_config_copy,
)
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


def create_app(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    real_data_exceptions_path: Path = REAL_DATA_EXCEPTIONS_PATH,
    out_root: Path = DEFAULT_OUT_ROOT,
    render_resolver: DigestResolver | None = None,
) -> FastAPI:
    app = FastAPI(title="OspreyFlow setup harness")
    app.state.last_artefacts = None
    app.state.artefacts_confirmed = False

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

    @app.get("/api/real-data-exceptions")
    def get_real_data_exceptions() -> dict[str, Any]:
        try:
            entries = load_exceptions(config_path=real_data_exceptions_path)
        except (KeyError, ValueError) as exc:
            # Never swallowed — `CLAUDE.md` rule 2 and this module's own docstring: an existing
            # local entry missing `decision_record` (or malformed) is invalid, and the panel says
            # so verbatim rather than showing an empty or partial list.
            raise HTTPException(
                status_code=422,
                detail=f"config/real_data_exceptions.yaml: {exc}",
            ) from exc
        return {"exceptions": [e.to_dict() for e in entries]}

    @app.post("/api/real-data-exceptions", status_code=201)
    def post_real_data_exception(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            entry = RealDataException(
                dataset=str(body.get("dataset", "")),
                approved_uses=tuple(body.get("approved_uses", ())),
                added_by=str(body.get("added_by", "")),
                added_date=date.today(),
                device=str(body.get("device", "")),
                justification=str(body.get("justification", "")),
                decision_record=str(body.get("decision_record", "")),
                revisit=str(body["revisit"]) if body.get("revisit") else None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            add_exception(entry, config_path=real_data_exceptions_path)
        except ValueError as exc:  # duplicate dataset — scripts.real_data_exceptions's own message
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return entry.to_dict()

    @app.delete("/api/real-data-exceptions/{dataset}")
    def delete_real_data_exception(dataset: str) -> dict[str, str]:
        if not remove_exception(dataset, config_path=real_data_exceptions_path):
            raise HTTPException(
                status_code=404, detail=f"{dataset!r} was not in the exceptions list."
            )
        return {"status": "removed", "dataset": dataset}

    @app.post("/api/geospatial/register-provider")
    def post_register_provider(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            provider_id = str(body["provider_id"])
            label = str(body["label"])
            pmtiles_path = str(body["pmtiles_path"])
        except KeyError as exc:
            raise HTTPException(status_code=422, detail=f"missing field: {exc}") from exc
        try:
            config = register_provider_step(
                config_path,
                provider_id=provider_id,
                label=label,
                pmtiles_path=Path(pmtiles_path),
                make_default=bool(body.get("make_default", True)),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors()) from exc
        return config.model_dump(mode="json", exclude_none=True)

    @app.post("/api/geospatial/build-basemap")
    def post_build_basemap(_body: dict[str, Any] = Body(default={})) -> None:
        try:
            build_basemap_step()
        except GeospatialError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc

    @app.post("/api/geospatial/verify")
    def post_verify_map(_body: dict[str, Any] = Body(default={})) -> None:
        try:
            verify_step()
        except GeospatialError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc

    def _out_dir() -> Path:
        return out_root / _read_config(config_path).profile.value

    def _preflight_events(context: PreflightContext, *, only: str | None) -> Iterator[bytes]:
        for result in run_streaming(context, only=only):
            payload = {
                "check": result.check,
                "status": result.status.value,
                "what_is_wrong": result.what_is_wrong,
                "what_to_do": result.what_to_do,
                "rechecked_at": result.rechecked_at,
                "detail": list(result.detail),
            }
            yield f"data: {json.dumps(payload)}\n\n".encode()
        yield b"event: complete\ndata: {}\n\n"

    @app.get("/api/preflight/stream")
    def get_preflight_stream(only: str | None = None, seeding: bool = False) -> StreamingResponse:
        # Validated here, before the stream starts, rather than left to raise mid-generator: once
        # a `StreamingResponse` has sent its 200 and its first bytes, an exception inside it is a
        # broken connection to the client, not a clean error — an unknown check name gets the same
        # synchronous 422 every other route's own bad input already does.
        if only is not None and only not in CHECKS_BY_NAME:
            raise HTTPException(status_code=422, detail=f"unknown check {only!r}")
        context = PreflightContext(
            config=_read_config(config_path), out_dir=_out_dir(), seeding=seeding
        )
        return StreamingResponse(
            _preflight_events(context, only=only), media_type="text/event-stream"
        )

    @app.post("/api/artefacts/generate")
    def post_generate_artefacts() -> dict[str, Any]:
        config = _read_config(config_path)
        out_dir = _out_dir()
        try:
            result = render(config, resolver=render_resolver)
        except ClusterRendererNotBuilt as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except MissingDockerfileError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except UnpinnedImagesError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        diffs = diff_for(result, out_dir)
        write(result, out_dir)
        write_config_copy(config_path, out_dir)
        app.state.last_artefacts = result.artefacts
        app.state.artefacts_confirmed = False
        return {
            "profile": result.profile.value,
            "osprey_yaml": config_path.read_text(encoding="utf-8") if config_path.exists() else "",
            "artefacts": result.artefacts,
            "diffs": diffs,
            "confirmed": False,
        }

    @app.get("/api/artefacts")
    def get_artefacts() -> dict[str, Any]:
        if app.state.last_artefacts is None:
            raise HTTPException(
                status_code=404, detail="Nothing generated yet — click Generate first."
            )
        return {"artefacts": app.state.last_artefacts, "confirmed": app.state.artefacts_confirmed}

    @app.get("/api/artefacts/{name}")
    def get_artefact_download(name: str) -> PlainTextResponse:
        artefacts: dict[str, str] | None = app.state.last_artefacts
        if artefacts is None or name not in artefacts:
            raise HTTPException(status_code=404, detail=f"{name!r} not found — generate first.")
        return PlainTextResponse(
            artefacts[name],
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.post("/api/artefacts/confirm")
    def post_confirm_artefacts() -> dict[str, Any]:
        if app.state.last_artefacts is None:
            raise HTTPException(
                status_code=422, detail="Nothing generated yet — click Generate first."
            )
        app.state.artefacts_confirmed = True
        return {"confirmed": True}

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
    parser.add_argument(
        "--real-data-exceptions",
        type=Path,
        default=REAL_DATA_EXCEPTIONS_PATH,
        help=(
            "Path to the local, gitignored real-data exceptions file the Governance screen's own "
            "panel reads and writes — default: scripts.real_data_exceptions.CONFIG_PATH, the "
            "owner's own device-local file. Override only for a scratch/test run (a keyboard spec, "
            "e.g.) that must never touch the real file — CLAUDE.md rule 9 / ADR-035 §C3."
        ),
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=DEFAULT_OUT_ROOT,
        help=(
            "Where the Preflight/artefacts-diff screen's own `Generate` writes — default: "
            "harness.render.DEFAULT_OUT_ROOT (deploy/generated/). Override only for a scratch/test "
            "run that must not write into the real checkout's own generated output."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    import uvicorn

    args = _parse_args(argv if argv is not None else sys.argv[1:])
    app = create_app(
        config_path=args.config,
        real_data_exceptions_path=args.real_data_exceptions,
        out_root=args.out_root,
    )
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
