"""`python -m harness <subcommand> ...` — the headless CLI dispatch `harness/Dockerfile`'s own
`ENTRYPOINT` uses, and the shape `CLAUDE.md`'s own Conventions section already names: "the shape
an eventual CLI subcommand would wrap, not a shortcut around one." Each subcommand below is the
exact same `python -m harness.<name>` entrypoint already built and tested on its own, reached
through one name instead of remembering six.

`05_DEPLOYMENT.md` §2's own bootstrap command runs this image. `07_BUILD_PLAN.md`'s Stage 2 §5b
brief named six subcommands; five remain: render, preflight, apply, backup, restore. The sixth,
`bundle`, left this package when the product folder was made to stand on its own: building a
bundle is a release step of the developer repository, not something a deployment runs
(`06_DECISIONS.md` ADR-114 Amendment 2).

**No subcommand starts nothing** (`06_DECISIONS.md` ADR-114 decision 3, the owner's ruling "Remove
them outright"): the Set-up console's screens are the guided install page, served by `ospreyflow
install --gui` only while an install runs. A test that needs the screens' server runs
`python -m harness.webapp` by name.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable

#: `preflight` is a package, not a module, and its own `main()` lives in its
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
}


def _usage() -> str:
    names = ", ".join(sorted(_SUBCOMMANDS))
    return (
        "usage: python -m harness [<subcommand> [args...]]\n"
        f"subcommands: {names}\n"
        "(no subcommand: see `ospreyflow install --gui` — ADR-114 decision 3)"
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(_usage())
        return 0
    if not argv or argv[0].startswith("-"):
        # The Set-up console no longer listens for good (`06_DECISIONS.md` ADR-114 decision 3, the
        # owner's ruling "Remove them outright"): its screens are the guided install page, served
        # by `ospreyflow install --gui` only while an install runs. A test server that needs the
        # screens runs `python -m harness.webapp` by name.
        print(
            "The set-up screens are now the guided install page: run `ospreyflow install --gui`.\n"
            "To start, stop or open an installed deployment: `ospreyflow start`, "
            "`ospreyflow stop`, `ospreyflow open`.",
            file=sys.stderr,
        )
        return 2

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
