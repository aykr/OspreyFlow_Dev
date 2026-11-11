"""The `cloud-platform` render with its backups (ADR-148 Amendment 7), for the tests.

The two calls that put `harness.cloud_platform_backups` into the render are the platform lane's
(`process/lanes/case/P9_render.diff`, ADR-142 Amendment 8 decision 3). Until that diff is applied
the render has no `backups`, and these tests apply the same two functions to its output, exactly as
the diff calls them; once it is, they read the render's own, and `test_backups_render.py`'s
`test_the_render_carries_the_backups_itself` (skipped until then) holds the render to them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from harness import cloud_platform_backups as backups
from harness.cloud_platform.settings import load_platform
from harness.render import load_config, render
from tools.cp_policy_check import FIXTURES, Target, _resolver


def config(fixture: str = "development") -> Any:
    return load_config(FIXTURES / f"{fixture}.yaml")


def artefacts(fixture: str = "development") -> dict[str, str]:
    return render(config(fixture), resolver=_resolver).artefacts


def has_the_diff(fixture: str = "development") -> bool:
    return "backups" in yaml.safe_load(artefacts(fixture)["values.yaml"])


def values(fixture: str = "development") -> dict[str, Any]:
    """The render's values, with the backups as the diff writes them."""
    found: dict[str, Any] = yaml.safe_load(artefacts(fixture)["values.yaml"])
    if "backups" not in found:  # P9_render.diff not applied: the one hook it adds, called here
        cfg = config(fixture)
        assert cfg.cloud_platform is not None
        backups.add_backups(cfg, load_platform(cfg.cloud_platform.platform), found)
    return found


def terraform(fixture: str = "development") -> str:
    files = artefacts(fixture)
    if "terraform/backups.tf" in files:
        return files["terraform/backups.tf"]
    cfg = config(fixture)
    assert cfg.cloud_platform is not None
    found: dict[str, Any] = yaml.safe_load(files["values.yaml"])
    return backups.add_backups(cfg, load_platform(cfg.cloud_platform.platform), found)["terraform/backups.tf"]


def target(fixture: str = "development") -> Target:
    """What `make cp-policy-check` holds `fixture` to, its values with the backups."""
    cfg = config(fixture)
    assert cfg.cloud_platform is not None and cfg.cloud_platform.registry and cfg.cloud_platform.namespace
    platform = load_platform(cfg.cloud_platform.platform)
    return Target(
        values=yaml.safe_dump(values(fixture), sort_keys=False, width=4096),
        registry=cfg.cloud_platform.registry,
        namespace=cfg.cloud_platform.namespace,
        controller_namespace=platform.ingress.controller_namespace,
    )


def fixtures() -> list[str]:
    return sorted(p.stem for p in Path(FIXTURES).glob("*.yaml"))
