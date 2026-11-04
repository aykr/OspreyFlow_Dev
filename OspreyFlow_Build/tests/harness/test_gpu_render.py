"""The local engine on an NVIDIA GPU (`06_DECISIONS.md` ADR-135 Amendment 1): `resources.gpu` in
`osprey.yaml`, and what the render does with it.

What a mistake would do, and the case that catches it:
- a GPU accepted for a cloud's server, which ADR-114 sizes without one —
  `test_a_gpu_is_refused_in_words_for_a_cloud`;
- a GPU refused on Lite, which may set it on a Linux computer, because `resources` is otherwise
  Small's alone — `test_a_gpu_is_taken_on_lite_and_on_a_small_of_your_own`;
- a misspelt GPU silently meaning none — `test_a_gpu_other_than_nvidia_is_refused`.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from schemas.deployment import OspreyConfig

OWN_SERVER: dict[str, Any] = {
    "profile": "small",
    "network": {"public_origin": "https://osprey.example.internal"},
}
CLOUD_SMALL: dict[str, Any] = {
    "profile": "small",
    "network": {"public_origin": "https://osprey.example.org"},
    "external": {"postgres": {"host": "db.example.org"}},
}
CLUSTER: dict[str, Any] = {
    "profile": "cluster",
    "network": {"public_origin": "https://osprey.example.org"},
    "components": {"storage": {"ingest": "/srv/ingest", "tiles": "/srv/tiles"}},
    "cluster": {"shared_storage_class": "efs-sc"},
    "external": {
        "postgres": {"host": "db.example.org"},
        "valkey": {"host": "cache.example.org"},
        "object_store": {"endpoint": "s3.eu-west-2.amazonaws.com", "region": "eu-west-2"},
    },
}


def _with_gpu(raw: dict[str, Any], gpu: str = "nvidia") -> OspreyConfig:
    return OspreyConfig.model_validate({**raw, "resources": {"gpu": gpu}})


def test_no_gpu_is_the_default() -> None:
    assert OspreyConfig().resources.gpu == "none"
    assert OspreyConfig.model_validate(CLUSTER).resources.gpu == "none"


def test_a_gpu_is_taken_on_lite_and_on_a_small_of_your_own() -> None:
    assert _with_gpu({}).resources.gpu == "nvidia"
    assert _with_gpu(OWN_SERVER).resources.gpu == "nvidia"
    # It sizes nothing, so it is not "the stores sized to the server" that Lite is refused.
    assert not _with_gpu({}).resources.any


@pytest.mark.parametrize("raw", [CLOUD_SMALL, CLUSTER], ids=["small-in-a-cloud", "enterprise"])
def test_a_gpu_is_refused_in_words_for_a_cloud(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as refused:
        _with_gpu(raw)
    said = str(refused.value)
    assert "resources.gpu" in said
    assert "without a GPU" in said


def test_a_gpu_other_than_nvidia_is_refused() -> None:
    # Refused as a value of the field, not as a key the schema does not know.
    with pytest.raises(ValidationError, match="'none' or 'nvidia'"):
        _with_gpu({}, "amd")
