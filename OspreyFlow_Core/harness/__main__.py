"""`python -m harness <subcommand> ...` — the headless CLI dispatch `harness/Dockerfile`'s own
`ENTRYPOINT` uses, and the shape `CLAUDE.md`'s own Conventions section already names: "the shape
an eventual CLI subcommand would wrap, not a shortcut around one." Each subcommand below is the
exact same `python -m harness.<name>` entrypoint already built and tested on its own, reached
through one name instead of remembering six.

`05_DEPLOYMENT.md` §2's own bootstrap command runs this image. `07_BUILD_PLAN.md`'s Stage 2 §5b
brief names the six subcommands this dispatcher wires: render, preflight, apply, backup, restore,
bundle. `bundle` is the one exception to "its own `harness.<name>`" — it wraps
`tools.osprey_bundle`, which predates this dispatcher and is deliberately not part of the
`harness` package itself (`06_DECISIONS.md` ADR-049: "wraps `tools/osprey_bundle.py`... rather
than writing a second implementation").

**No subcommand is now the browser setup harness** (`Stage 2 §6` part A) — `05_DEPLOYMENT.md` §2's
own bootstrap command (`docker run ... ghcr.io/ospreyflow/harness:latest`, no arguments) reaches
`harness.webapp.main`, which serves the Profile/Components/Models screens' own API (and the built
`apps/harness` frontend, once `dist/` exists) on loopback, per ruling R2. `-h`/`--help` still shows
the subcommand list below, since those remain real, separate commands the browser app itself calls
into rather than replaces.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

#: `bundle` maps to `tools.osprey_bundle`, the one deliberate exception — see the module
#: docstring. `preflight` is a package, not a module, and its own `main()` lives in its
#: `__main__.py` (what `python -m harness.preflight` itself resolves via `runpy`, not a plain
#: `import_module` of the package's `__init__.py` — found the moment this dispatcher first ran:
#: `AttributeError: module 'harness.preflight' has no attribute 'main'`). Every other name is
#: `harness.<name>`, kept as a literal mapping rather than a string-formatted `f"harness.{name}"`
#: so a typo in this dict is the only way to reach the wrong module, not a naming-convention
#: assumption about the whole package.
_SUBCOMMANDS: dict[str, str] = {
    "render": "harness.render",
    "preflight": "harness.preflight.__main__",
    "apply": "harness.apply",
    "backup": "harness.backup",
    "restore": "harness.restore",
    "bundle": "tools.osprey_bundle",
}


def _usage() -> str:
    names = ", ".join(sorted(_SUBCOMMANDS))
    return (
        "usage: python -m harness [<subcommand> [args...]]\n"
        f"subcommands: {names}\n"
        "(no subcommand: the browser setup harness, Stage 2 §6 — see harness.webapp)"
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(_usage())
        return 0
    if not argv or argv[0].startswith("-"):
        # No subcommand, or a flag meant for the webapp itself (`--host`/`--port`/`--config` —
        # `harness.webapp._parse_args`'s own options) rather than a subcommand name, which is
        # always a bare word. Found needing this: `apps/harness/keyboard/playwright.config.ts`'s
        # own test server passes `--config` to point the webapp at a scratch file rather than this
        # checkout's real `osprey.yaml` — the empty-argv-only version of this branch silently
        # discarded that flag and always served the real file.
        from harness.webapp import main as webapp_main

        return webapp_main(argv)

    subcommand, rest = argv[0], argv[1:]
    module_name = _SUBCOMMANDS.get(subcommand)
    if module_name is None:
        print(f"unknown subcommand: {subcommand!r}\n\n{_usage()}", file=sys.stderr)
        return 2

    module = importlib.import_module(module_name)
    entry: Callable[[list[str] | None], int] = module.main
    return entry(rest)


if __name__ == "__main__":
    raise SystemExit(main())
