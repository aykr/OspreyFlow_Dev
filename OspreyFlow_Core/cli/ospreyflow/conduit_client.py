"""`ospreyflow release` and `ospreyflow run`: thin clients of the Conduit's own routes, so the
command does what the Studio's buttons do and an orchestrator drives a run without taking the load
out of OspreyFlow (`06_DECISIONS.md` ADR-140 Amendment 9 decision 4; ADR-141 decisions 9–12).

    ospreyflow release export <dataset> --name N --release-version V --out DIR
    ospreyflow release import DIR --dataset ID [--dry-run]
    ospreyflow run <dataset> <pipeline> [--version N|latest] --external-run-id ID [--wait]
                   [--fail-on held|rejections>N%]

**Who acts.** A release is a person's act: the bearer token is theirs (`OSPREY_TOKEN`). A run is
triggered by a service identity: its client-credentials token is asked of the deployment's
identity provider (`OSPREY_TOKEN_URL`, `OSPREY_CLIENT_ID`, `OSPREY_CLIENT_SECRET`), and the run
acts as the pipeline's owner, never as the identity (decision 10). No secret is printed: a
refusal names what is missing, never a value.

**Exit codes** (an orchestrator's task reads them): 0 done; 1 refused or failed, in words;
2 the run finished but `--fail-on` was met, or its counts were withheld so it could not be judged
(never judged as passing on counts it could not see, rule 3).
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .home import CommandRefused

# ADR-114 decision 3: the command itself is the standard library and PyYAML alone. httpx is the
# checkout's, imported where a client is made (`client`, reached through `main._conduit_verb`).
if TYPE_CHECKING:
    import httpx

#: The longest `--wait` waits before saying the run is still going (exit 1).
WAIT_SECONDS = 6 * 60 * 60
POLL_SECONDS = 5.0
_FAIL_ON = re.compile(r"^(held|rejections>(\d{1,3}(?:\.\d+)?)%)$")


@dataclass(frozen=True)
class FailOn:
    held: bool = False
    rejections_over: float | None = None


def parse_fail_on(text: str | None) -> FailOn:
    if not text:
        return FailOn()
    found = _FAIL_ON.match(text.strip())
    if found is None:
        raise CommandRefused(
            f"--fail-on {text!r} is not one this command knows: give 'held' or 'rejections>N%'"
        )
    if found.group(2) is not None:
        return FailOn(rejections_over=float(found.group(2)))
    return FailOn(held=True)


def person_token(env: Mapping[str, str]) -> str:
    token = env.get("OSPREY_TOKEN", "").strip()
    if not token:
        raise CommandRefused(
            "Set OSPREY_TOKEN to your own sign-in token: a release is exported and imported as you."
        )
    return token


def service_token(env: Mapping[str, str], http: httpx.Client) -> str:
    """The service identity's token (OAuth 2.0 client credentials), or `OSPREY_TOKEN` if given."""
    if env.get("OSPREY_TOKEN", "").strip():
        return env["OSPREY_TOKEN"].strip()
    missing = [k for k in ("OSPREY_TOKEN_URL", "OSPREY_CLIENT_ID", "OSPREY_CLIENT_SECRET")
               if not env.get(k, "").strip()]  # fmt: skip
    if missing:
        raise CommandRefused(
            f"Set {', '.join(missing)}: a run is triggered by the deployment's service identity."
        )
    answer = http.post(
        env["OSPREY_TOKEN_URL"],
        data={
            "grant_type": "client_credentials",
            "client_id": env["OSPREY_CLIENT_ID"],
            "client_secret": env["OSPREY_CLIENT_SECRET"],
        },
    )
    if answer.status_code != 200:
        raise CommandRefused(
            f"The identity provider refused the service identity's sign-in ({answer.status_code}); "
            "check its client id and secret, and that it may sign in as a service."
        )
    token = answer.json().get("access_token")
    if not isinstance(token, str) or not token:
        raise CommandRefused("The identity provider's answer held no access token.")
    return token


def _words(answer: httpx.Response) -> str:
    try:
        body = answer.json()
    except ValueError:
        return f"the Conduit answered {answer.status_code}"
    if isinstance(body, dict):
        for key in ("refused", "problems"):
            if body.get(key):
                return "; ".join(str(p) for p in body[key])
        if isinstance(body.get("detail"), str):
            return body["detail"]
        if body.get("words"):
            return str(body["words"])
    return f"the Conduit answered {answer.status_code}"


def release_export(
    http: httpx.Client, *, token: str, dataset: str, name: str, version: str, out: Path,
    say: Callable[[str], None] = print,
) -> int:  # fmt: skip
    if out.exists() and any(out.iterdir()):
        raise CommandRefused(f"{out} is not empty: export into a new folder, so nothing is mixed.")
    answer = http.get(
        f"/v1/datasets/{dataset}/release",
        params={"name": name, "version": version},
        headers={"Authorization": f"Bearer {token}"},
    )
    if answer.status_code != 200:
        say(f"The export was refused: {_words(answer)}")
        return 1
    body = answer.json()
    for path, text in body["files"].items():
        target = (out / path).resolve()
        if not target.is_relative_to(out.resolve()):
            raise CommandRefused(f"The bundle names a file outside its folder ({path}).")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    say(f"Exported {len(body['files'])} files to {out}.")
    if body.get("left_out"):
        say(
            f"{body['left_out']} published pipeline(s) are marked above what you may view, so they "
            "are not in this release."
        )
    return 0


def _bundle_files(folder: Path) -> dict[str, str]:
    if not (folder / "release.yaml").is_file():
        raise CommandRefused(f"{folder} holds no release.yaml: give the folder an export made.")
    return {
        p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def release_import(
    http: httpx.Client, *, token: str, dataset: str, folder: Path, dry_run: bool,
    replace_own_draft: int | None = None, say: Callable[[str], None] = print,
) -> int:  # fmt: skip
    params = {"dry_run": "true" if dry_run else "false"}
    if replace_own_draft is not None:
        # CARRIES row 90: the version of the importer's own open model draft they confirm replacing.
        params["replace_own_draft"] = str(replace_own_draft)
    answer = http.post(
        f"/v1/datasets/{dataset}/release/import",
        params=params,
        json={"files": _bundle_files(folder)},
        headers={"Authorization": f"Bearer {token}"},
    )
    if answer.status_code not in (200, 422):
        say(f"The import was refused: {_words(answer)}")
        return 1
    plan = answer.json()
    for problem in plan.get("refused", []):
        say(f"Refused: {problem}")
    if plan.get("refused"):
        say("Nothing was written.")
        return 1
    verb = "Would write" if dry_run else "Wrote"
    for item in plan.get("items", []):
        what = (
            "a new draft"
            if item["action"] == "new_draft"
            else "the draft, in place of the open one"
        )
        say(f"{verb} {item['name']} as {what}.")
    for name in plan.get("missing_connections", []):
        say(f"This environment has no connection named {name!r}: add one before a run.")
    for note in plan.get("notes", []):
        say(f"Note: {note}.")
    say(
        "Nothing was written (a dry run)."
        if dry_run
        else "Everything is a draft: make the model live in the Studio when it is ready."
    )
    return 0


def _judge(status: Mapping[str, Any], fail_on: FailOn) -> str | None:
    """Why `--fail-on` is met, in words; `None` when it is not."""
    if not (fail_on.held or fail_on.rejections_over is not None):
        return None
    if status.get("withheld"):
        return "the run's counts are withheld from this service identity, so --fail-on cannot pass"
    if fail_on.held and (status.get("rows_held") or 0) > 0:
        return f"{status['rows_held']} row(s) are held for review"
    if fail_on.rejections_over is not None:
        read = status.get("rows_read") or 0
        rejected = status.get("rows_rejected") or 0
        share = 100.0 * rejected / read if read else 0.0
        if share > fail_on.rejections_over:
            return f"{share:.1f}% of rows were rejected, over {fail_on.rejections_over:g}%"
    return None


def run(
    http: httpx.Client, *, token: str, dataset: str, pipeline: str, version: str,
    external_run_id: str, wait: bool, fail_on: FailOn,
    say: Callable[[str], None] = print,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> int:  # fmt: skip
    headers = {"Authorization": f"Bearer {token}"}
    answer = http.post(
        "/v1/runs",
        json={
            "dataset_id": dataset,
            "pipeline_id": pipeline,
            "version": "latest" if version == "latest" else int(version),
            "external_run_id": external_run_id,
        },
        headers=headers,
    )
    if answer.status_code not in (200, 201, 202):
        say(f"The run was refused: {_words(answer)}")
        return 1
    status = answer.json()
    if status.get("already_recorded"):
        say(f"The run {external_run_id} was already triggered; nothing more was loaded.")
    started = clock()
    while wait and status["outcome"] == "running":
        if clock() - started > WAIT_SECONDS:
            say(f"The run {status['run_id']} is still going; ask again later.")
            return 1
        sleep(POLL_SECONDS)
        polled = http.get(f"/v1/runs/{status['run_id']}", headers=headers)
        if polled.status_code != 200:
            say(f"The run's status could not be read: {_words(polled)}")
            return 1
        status = polled.json()
    outcome = status["outcome"]
    if outcome in ("refused", "failed"):
        say(f"The run was {outcome}: {status.get('words') or 'no reason was recorded'}")
        return 1
    if outcome == "running":
        say(f"The run {status['run_id']} has started.")
        return 0
    met = _judge(status, fail_on)
    if met is not None:
        say(f"The run succeeded, but --fail-on is met: {met}.")
        return 2
    say(f"The run {status['run_id']} succeeded.")
    return 0


def client(api: str) -> httpx.Client:
    import httpx

    return httpx.Client(base_url=api.rstrip("/"), timeout=60.0)


def api_url(env: Mapping[str, str] | None, default: str) -> str:
    environ = os.environ if env is None else env
    return environ.get("OSPREY_API_URL", "").strip() or default
