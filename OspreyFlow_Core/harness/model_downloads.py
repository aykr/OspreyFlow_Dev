"""A newly chosen model fetched before the services that use it start again (ADR-114 Amendment 33,
"as found on the first server", defect 9).

The local engine's weights are fetched by the one-shot step `ollama-models` (ADR-114 Amendment 7),
which pulls and verifies what its `command` names and then idles (`exec sleep infinity`, so `up
--wait` does not read its exit as a failure). A changed extraction model (`resources.gpu: nvidia`
choosing the 14b, or `models.extraction` changed by hand) changes that command.

Found on the first server, 4 November 2026: `ospreyflow apply` rendered the 14b into the pull
script, the routing table and `OSPREY_EXTRACTION_MODEL`, and started the gateway, the Conduit and
the model server again — but a run-once step is never among the services `apply` restarts, and
Compose leaves a one-shot step alone unless it is named, so the 14b was never fetched and every Ask
went to a model that was not there.

So whoever changes the files runs `fetch_argvs` first, when `steps_to_fetch` names the step, before
anything that uses the model starts again: the step is started again by name, then waited on with
`exec` until its first process is the `sleep` its script ends in (every pull done and verified). A
failed pull exits the container (`set -e`), which ends the `exec` with a non-zero code.

`whisper-models` is not among them: the speech model has one allowed value
(`schemas.deployment.TranscriptionModel`), so no setting changes what it downloads, and `whisper`
waits on it through `depends_on` whenever it is started with its dependencies.

Only the command is compared, not the image: a new image of the same pulls (a release moving the
pinned Ollama) fetches nothing new, and an offline update must not fail on a pull it does not need.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

#: The one-shot steps whose downloads a setting can change (`harness/render.py`, Amendment 7).
MODEL_DOWNLOAD_STEPS = ("ollama-models",)

#: The longest a fetch is waited on: the 14b is about 9 GB.
FETCH_TIMEOUT_SECONDS = 4 * 3600

#: Waits inside the step's container until its first process is the `sleep` its script ends in.
_UNTIL_IDLE = 'until [ "$(cat /proc/1/comm)" = sleep ]; do sleep 2; done'


def _steps(compose_file: Path) -> dict[str, Mapping[str, Any]]:
    if not compose_file.is_file():
        return {}
    document = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    services = document.get("services") or {}
    return {
        name: services[name]
        for name in MODEL_DOWNLOAD_STEPS
        if isinstance(services.get(name), dict)
    }


def commands(compose_file: Path) -> dict[str, Any]:
    """Each download step's `command`, as the compose file names it."""
    return {name: step.get("command") for name, step in _steps(compose_file).items()}


def steps_to_fetch(before: Mapping[str, Any], after_compose: Path) -> list[str]:
    """The steps of `after_compose` whose command differs from `before` (`commands` of the
    deployment as it was), or that are new: each pulls something not yet fetched."""
    return [
        name for name, command in commands(after_compose).items()
        if before.get(name) != command
    ]  # fmt: skip


def fetch_argvs(
    compose: list[str], steps: list[str], *, force: bool, extra: tuple[str, ...] = ()
) -> list[list[str]]:
    """The commands that fetch `steps`, to run in order; the last returns only once every pull is
    done, and fails (a non-zero exit) when one was refused. `compose` is `docker compose
    --env-file … -f <compose file>`. `force` recreates the step whatever Compose thinks of its
    definition; without it, the changed command is what makes Compose recreate it."""
    recreate = ["--force-recreate"] if force else []
    argvs: list[list[str]] = []
    for step in steps:
        argvs.append([*compose, "up", "-d", "--no-deps", *recreate, *extra, step])
        argvs.append([*compose, "exec", "-T", step, "sh", "-c", _UNTIL_IDLE])
    return argvs


def failed_words(steps: list[str]) -> str:
    named = ", ".join(steps)
    return (
        f"the model download ({named}) did not finish. `ospreyflow logs {steps[0]}` has the "
        "reason (a download refused, or a model's tag moved upstream: ADR-020)"
    )
