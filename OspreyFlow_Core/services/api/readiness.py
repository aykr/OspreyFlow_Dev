"""Whether the deployment's models are present (`06_DECISIONS.md` ADR-095 decision 1, Amendment 2).

The deployment does not wait for its models at start: pulling them is gigabytes, and gating
`docker compose up --wait` on it made a CI gate ten times slower (`05_DEPLOYMENT.md` §2.1.1). So the
deployment reports readiness instead: this asks Ollama's own list for each model the Conduit serves
with through it, and says ready only when every one is there. Transcription is the Whisper
sidecar's, not Ollama's, and is not in the list.

Behind a principal like every `/v1` route: which models a deployment runs is not for an anonymous
caller (`/healthz`'s own reasoning), and it touches no store.
"""

from __future__ import annotations

import os

import httpx
from pydantic import BaseModel

from .config import DeploymentModels

#: How long the Conduit waits for Ollama's list before saying it did not answer.
TIMEOUT_SECONDS = 3.0


class ModelState(BaseModel):
    role: str
    name: str
    present: bool


class Readiness(BaseModel):
    ready: bool
    models: list[ModelState]
    #: Set when the model server could not be asked; the models are then reported as not present.
    problem: str | None = None


def _tagged(name: str) -> str:
    """Ollama lists a model under `name:tag`; a bare name is its `latest`."""
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"


def ollama_roles(models: DeploymentModels) -> list[tuple[str, str]]:
    return [
        ("extraction", models.extraction),
        ("vision", models.vision),
        ("embedding", models.embedding),
    ]


async def check_models(models: DeploymentModels, http: httpx.AsyncClient) -> Readiness:
    roles = ollama_roles(models)
    try:
        response = await http.get("/api/tags", timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        listed = {_tagged(str(m.get("name", ""))) for m in response.json().get("models", [])}
    except (httpx.HTTPError, ValueError):
        return Readiness(
            ready=False,
            models=[ModelState(role=r, name=n, present=False) for r, n in roles],
            problem="The model server did not answer.",
        )
    states = [ModelState(role=r, name=n, present=_tagged(n) in listed) for r, n in roles]
    return Readiness(ready=all(s.present for s in states), models=states)


async def deployment_readiness() -> Readiness:
    """The deployment's own models, asked of the Ollama the renderer names (`OSPREY_OLLAMA_URL`)."""
    models = DeploymentModels.from_env()
    base_url = os.environ.get("OSPREY_OLLAMA_URL")
    if not base_url:
        return Readiness(
            ready=False,
            models=[ModelState(role=r, name=n, present=False) for r, n in ollama_roles(models)],
            problem="No model server is configured for this deployment.",
        )
    async with httpx.AsyncClient(base_url=base_url) as http:
        return await check_models(models, http)
