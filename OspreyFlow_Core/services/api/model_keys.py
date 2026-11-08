"""The Conduit's own key path for the command line (`06_DECISIONS.md` ADR-135 Amendment 2 decisions
3 and 8): `ospreyflow models key`, `models remove-key` and the first `apply` of a deployment whose
keys are still in `deployment.env` run this inside the Conduit's container, so the gateway's admin
API, the models file and the audit are the same code as *Admin › Models*'.

    python -m services.api.model_keys set <name> --by <who>      # the key in OSPREY_MODEL_KEY_GIVEN
                                                                  # or on standard input
    python -m services.api.model_keys remove <name> --by <who>
    python -m services.api.model_keys move --by <who>            # NAME=KEY lines on standard input
    python -m services.api.model_keys status                      # name, set|none|lost per line

A key is read from `OSPREY_MODEL_KEY_GIVEN` (passed by name into the container) or standard input,
never from an argument (which `ps` would show), and never printed. Every answer is in fixed words;
the exit status is 0 on success, 1 when refused.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence

import httpx
from pydantic import SecretStr

from adapters.model_litellm.client import LiteLLMConfig

from .config import DeploymentModels, PostgresConfig
from .model_admin import (
    GatewayAdmin,
    Installed,
    ModelAdmin,
    ModelAdminRefused,
    ModelSettingsFile,
    PostgresModelAdminAudit,
)

#: Where `ospreyflow models key` puts the key for this command (ADR-135 Amendment 2 decision 8).
KEY_VARIABLE = "OSPREY_MODEL_KEY_GIVEN"


async def _admin(
    *, reconcile: bool = True
) -> tuple[ModelAdmin, httpx.AsyncClient, PostgresModelAdminAudit]:
    gateway = LiteLLMConfig.from_env()
    http = httpx.AsyncClient(
        base_url=gateway.base_url, headers={"Authorization": f"Bearer {gateway.api_key}"}
    )
    audit = await PostgresModelAdminAudit.connect(PostgresConfig.from_env().dsn)
    admin = ModelAdmin(
        installed=Installed.from_env(DeploymentModels.from_env(), os.environ),
        settings_file=ModelSettingsFile.from_env(),
        gateway=GatewayAdmin(http),
        audit=audit,
    )
    if reconcile:  # `status` only reads: it changes neither the gateway nor the file
        await admin.start()
    return admin, http, audit


async def move_keys(
    admin: ModelAdmin, lines: Sequence[str], by: str
) -> tuple[list[str], list[str]]:
    """Each `NAME=KEY` line's key into the gateway (decision 3, existing deployments and every
    install): the engines are the deployment's (the models file's, else `osprey.yaml`'s). Returns
    the names moved and those **skipped**: an engine no longer enabled (removed in *Admin ›
    Models*) has no use for a key, so its line is dropped and named rather than failing every
    `apply` that follows."""
    pairs: dict[str, SecretStr] = {}
    for line in lines:
        name, sep, value = line.strip().partition("=")
        if sep and value:
            pairs[name.strip().lower()] = SecretStr(value.strip())
    enabled = {p.name for p in admin.settings.providers}
    skipped = sorted(set(pairs) - enabled)
    moved = sorted(set(pairs) & enabled)
    for name in moved:
        await admin.set_key(by, name, pairs[name], action="key_moved")
    return moved, skipped


async def _run(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m services.api.model_keys")
    parser.add_argument("verb", choices=("set", "remove", "move", "status"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("--by", default="cli")
    args = parser.parse_args(argv)
    admin, http, audit = await _admin(reconcile=args.verb != "status")
    by = args.by if args.by.startswith("cli:") else f"cli:{args.by}"
    try:
        if args.verb == "status":
            view = admin.view()
            for engine in view.engines:
                print(f"{engine.provider.name} {engine.key_state}")
            for role, engine_name in sorted(view.defaults.items()):
                print(f"default:{role} {engine_name}")
        elif args.verb == "move":
            moved, skipped = await move_keys(admin, sys.stdin.read().splitlines(), by)
            print(f"moved into the gateway: {', '.join(moved) or 'none'}")
            if skipped:
                print(f"dropped, no longer enabled engines: {', '.join(skipped)}")
        elif args.name is None:
            print("name the engine", file=sys.stderr)
            return 1
        elif args.verb == "set":
            # From the environment the command line passes by name (`docker compose exec -e`,
            # never an argument), else standard input.
            key = os.environ.pop(KEY_VARIABLE, "").strip() or sys.stdin.readline().strip()
            if not key:
                print("no key was given on standard input; nothing was changed", file=sys.stderr)
                return 1
            await admin.set_key(by, args.name, SecretStr(key))
            print(f"key set for {args.name}")
        else:
            await admin.remove_key(by, args.name)
            print(f"key removed for {args.name}")
        return 0
    except ModelAdminRefused as refused:
        print(refused.words, file=sys.stderr)
        return 1
    finally:
        await admin.close()  # its retry, if the gateway was not answering, stops here
        await http.aclose()
        await audit.close()


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_run(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
