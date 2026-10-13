"""The update notice `ospreyflow update --check` writes on the host (ADR-114 Amendment 8 point
2), read from the deployment's `state/` folder, mounted read-only. Read on each request, so a check
needs no restart; a missing or damaged file reads as never checked."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import ValidationError

from schemas.admin import UpdateNotice

NOTICE_FILE = "update.json"


def read_update_notice(state_dir: str | None = None) -> UpdateNotice | None:
    folder = state_dir if state_dir is not None else os.environ.get("OSPREY_STATE_DIR")
    if not folder:
        return None
    try:
        return UpdateNotice.model_validate(
            json.loads((Path(folder) / NOTICE_FILE).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, ValidationError):
        return None
