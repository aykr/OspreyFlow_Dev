"""`python -m harness <subcommand> ...` — the headless CLI dispatch `harness/Dockerfile`'s own
`ENTRYPOINT` uses, and the shape `CLAUDE.md`'s own Conventions section already names: "the shape
an eventual CLI subcommand would wrap, not a shortcut around one." Each subcommand below is the
exact same `python -m harness.<name>` entrypoint already built and tested on its own, reached
through one name instead of remembering six.

`05_DEPLOYMENT.md` §2's own bootstrap command runs this image. `07_BUILD_PLAN.md`'s Stage 2 §5b
brief names the six subcommands this dispatcher wires: render, preflight, apply, backup, restore,
bundle. `bundle` is the one exception to "its own `harness.<name>`" — it wraps
`scripts.osprey_bundle`, which predates this dispatcher and is deliberately not part of the
`harness` package itself (`06_DECISIONS.md` ADR-049: "wraps `scripts/osprey_bundle.py`... rather
than writing a second implementation").

Once `Stage 2 §6` exists, `python -m harness` with no subcommand becomes the browser setup harness
this package's own docstring names. Today, with no subcommand, it prints usage and exits 2 —
nothing to serve exists yet, and a silent no-op would be a worse answer than a named refusal.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

#: `bundle` maps to `scripts.osprey_bundle`, the one deliberate exception — see the module
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
    "bundle": "scripts.osprey_bundle",
}


def _usage() -> str:
    names = ", ".join(sorted(_SUBCOMMANDS))
    return (
        "usage: python -m harness <subcommand> [args...]\n"
        f"subcommands: {names}\n"
        "(the browser setup harness itself is Stage 2 §6, not yet built — "
        "there is no subcommand-less mode yet)"
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(_usage(), file=sys.stderr)
        return 2
    if argv[0] in ("-h", "--help"):
        print(_usage())
        return 0

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
