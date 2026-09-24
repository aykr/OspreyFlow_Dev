"""`python -m harness.preflight` — the headless Preflight screen (`05_DEPLOYMENT.md` §2.3).

Three modes, each answering a different question:

- **bare** — run everything and report. What an operator reads.
- **`--only <check>`** — run one. This *is* the Re-check button §2.1 requires; a screen that
  re-ran everything and filtered the output would be a different, slower thing wearing its name.
- **`--gate`** — exit non-zero while any check fails, printing only the failures. What Stage 2 §3's
  scripted deploy and Stage 2 §6's screen call before enabling Launch.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness.preflight import ALL_CHECKS, CHECKS_BY_NAME
from harness.preflight.context import REPO_ROOT, PreflightContext
from harness.preflight.reduced import accept, offer_for
from harness.preflight.result import CheckResult, Status
from harness.render import DEFAULT_CONFIG_PATH, DEFAULT_OUT_ROOT, load_config

_SYMBOL = {Status.PASS: "PASS", Status.FAIL: "FAIL", Status.SKIP: "SKIP"}


def run(context: PreflightContext, *, only: str | None = None) -> list[CheckResult]:
    """Runs every check, or one. Each check is called independently and a crash inside one is
    reported as that check failing rather than taking the run down — an operator needs the other
    nine results, and a traceback is not an explanation of what to do."""
    modules = ALL_CHECKS if only is None else (CHECKS_BY_NAME[only],)
    results = []
    for module in modules:
        try:
            results.append(module.check(context))
        except Exception as error:  # noqa: BLE001 - a check crashing is a check failing
            results.append(
                CheckResult(
                    check=module.NAME,
                    status=Status.FAIL,
                    what_is_wrong=f"the check itself raised {type(error).__name__}: {error}",
                    what_to_do=(
                        "This is a defect in the check, not necessarily in your environment. "
                        "Report it; the other checks' results above are still valid."
                    ),
                )
            )
    return results


def _print(result: CheckResult) -> None:
    print(f"{_SYMBOL[result.status]:<5} {result.check}  ({result.rechecked_at})")
    for line in result.detail:
        print(f"        {line}")
    if result.status is Status.PASS:
        return
    label = "did not run" if result.status is Status.SKIP else "what is wrong"
    print(f"        {label}: {result.what_is_wrong}")
    if result.status is Status.FAIL:
        print(f"        what to do:    {result.what_to_do}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m harness.preflight",
        description=(
            "Environment checks before Launch (docs/05_DEPLOYMENT.md §2.1). Reads the rendered "
            "deployment under deploy/generated/<profile>/."
        ),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument(
        "--only", choices=sorted(CHECKS_BY_NAME), help="Run one check — this is Re-check."
    )
    parser.add_argument(
        "--gate",
        action="store_true",
        help="Exit non-zero while any check fails. What Launch consults.",
    )
    parser.add_argument(
        "--seeding",
        action="store_true",
        help="Seeding is about to run, so check the DuckDB lock holder.",
    )
    parser.add_argument(
        "--accept-reduced",
        action="store_true",
        help="Accept §3's reduced variant and re-render. The only thing that changes anything.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, context: PreflightContext | None = None) -> int:
    """`context` is an injection point for tests, and exists for one property in particular.

    §3's "offered, not applied silently" cannot be exercised end to end otherwise: the offer only
    appears below a 16 GiB memory reading, and a test cannot lower this machine's RAM. Without this
    seam the only coverage would be of `offer_for()` in isolation — which, since that function has
    no access to the output directory at all, cannot demonstrate the thing that actually matters,
    namely that *the CLI* does not apply the variant on its own. Found by mutation testing: a
    planted silent-apply in this function was caught by nothing until this seam existed.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    config = context.config if context is not None else load_config(args.config)
    out_dir = context.out_dir if context is not None else args.out_root / config.profile.value
    if context is None:
        context = PreflightContext(config=config, out_dir=out_dir, seeding=args.seeding)

    results = run(context, only=args.only)
    failures = [r for r in results if r.status is Status.FAIL]

    if args.gate:
        for result in failures:
            _print(result)
        if failures:
            print(f"\npreflight --gate: {len(failures)} check(s) failing. Launch is blocked.")
            return 1
        print(f"preflight --gate: {len(results)} check(s), none failing. Launch may proceed.")
        return 0

    print(f"preflight: {config.profile.value}, reading {_display(out_dir)}\n")
    for result in results:
        _print(result)

    passes = sum(1 for r in results if r.status is Status.PASS)
    skips = sum(1 for r in results if r.status is Status.SKIP)
    print(f"\n{passes} passed, {len(failures)} failed, {skips} skipped.")
    if skips:
        print("A skipped check did not run. It is not a statement that what it checks is correct.")

    offer = offer_for(results, config)
    if offer is not None and not args.accept_reduced:
        print(offer.render_text())

    if args.accept_reduced:
        if offer is None:
            print(
                "\n--accept-reduced was passed but the reduced variant is not on offer "
                "(memory is at or above the floor, or it is already in force). Nothing changed."
            )
            return 1
        _reduced, written = accept(config, out_dir)
        print("\nACCEPTED — re-rendered through harness.render with search: postgres-fulltext:")
        for path in written:
            print(f"  {_display(path)}")
        print(
            "\nosprey.yaml itself is unchanged: it is your file, reviewed in a pull request. "
            "Record the choice on the Components screen to make it permanent."
        )

    return 1 if failures else 0


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
