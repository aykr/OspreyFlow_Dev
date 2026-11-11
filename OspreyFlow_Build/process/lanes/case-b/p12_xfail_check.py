"""P12 part 1, round 3 (the orchestrator's confirmation of d02aea8, item 1): the strict xfail on
Laurium's conforming-answer case (`tests/conformance/model_port/test_suite.py`) holds for the
unparseable refusal alone. Run in Laurium's own 3.13 environment, from `OspreyFlow_Core`, offline:

    ../OspreyFlow_Build/laurium-env/.venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/p12_xfail_check.py

The case runs through `laurium_live_adapter`, its real factory, pointed at the gateway's stand-in
served over HTTP on 127.0.0.1 (`LITELLM_*`), so no real gateway is reached. Four runs, each with the
outcome it must have, read off pytest's own summary line for that case:

1. the stand-in answering what no parser reads: **XFAIL** (the ruled finding);
2. the stand-in answering a conforming finding: **FAILED**, as a strict XPASS;
3. a gateway refusal planted at the adapter's call site (its token one the gateway does not hold,
   answered 401): **FAILED**, not XFAIL;
4. the same plant under round 2's mark (`raises=ExtractionFailedError`) and its plain call, restored
   for the run: **XFAIL**,
   which is the hole the round-3 mark closes.

Each plant is put back after its run, and no bytecode is written while one is in.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

sys.path[:0] = [".", "packages", "cli", "../OspreyFlow_Build"]

from tests.conformance.model_port.laurium_in_process import MASTER, stand_in  # noqa: E402
from tests.conformance.model_port.stand_in_http import serve  # noqa: E402

CASE = (
    "../OspreyFlow_Build/tests/conformance/model_port/test_suite.py::"
    "test_extract_returns_data_conforming_to_the_requested_schema[extract_laurium]"
)
ADAPTER = pathlib.Path("packages/adapters/extract_laurium/adapter.py")
SUITE = pathlib.Path("../OspreyFlow_Build/tests/conformance/model_port/test_suite.py")
UNKNOWN_TOKEN = (
    "            token = laurium_key(self._master)\n",
    '            token = "sk-planted-not-held-by-the-gateway"\n',
)
OLD_MARK = ("    raises=LauriumCouldNotRead,\n", "    raises=ExtractionFailedError,\n")
#: Round 2's call, as it was: no reading of the refusal's words (found running this: restoring the
#: mark alone left round 3's except clause turning the 401 into an AssertionError, so run 4 proved
#: nothing about round 2's mark).
ROUND_2_CALL = (
    """        try:
            result = await adapter.extract(req)
        except ExtractionFailedError as exc:
            if factory.label == "extract_laurium" and UNPARSEABLE in str(exc):
                raise LauriumCouldNotRead(str(exc)) from exc
            raise AssertionError(f"extract failed for another reason: {exc}") from exc
""",
    "        result = await adapter.extract(req)\n",
)


def run(answer: str) -> str:
    gateway = stand_in(answer=answer)
    with serve(gateway) as port:
        env = {**os.environ, "LITELLM_HOST": "127.0.0.1", "LITELLM_PORT": str(port),
               "LITELLM_API_KEY": MASTER, "PYTHONDONTWRITEBYTECODE": "1",
               "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
               "CLICKHOUSE_HTTP_PORT": "59994"}  # fmt: skip
        env.pop("OSPREY_LANE", None)
        env.pop("MINIO_ENDPOINT", None)
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-p",
             "no:cacheprovider", "-rA", "-q", CASE],
            capture_output=True, text=True, env=env, check=False,
        )  # fmt: skip
    lines = [ln for ln in out.stdout.splitlines() if re.match(r"(XFAIL|XPASS|FAILED|PASSED|ERROR) ", ln)]
    why = [ln for ln in out.stdout.splitlines() if ln.startswith("E ")][:2]
    return (lines[-1] if lines else f"NO OUTCOME (exit {out.returncode}): {out.stdout[-400:]}") + (
        "\n      " + "\n      ".join(why) if why else ""
    )


def planted(edits: list[tuple[pathlib.Path, tuple[str, str]]], answer: str) -> str:
    originals = {path: path.read_text() for path, _ in edits}
    try:
        for path, (old, new) in edits:
            text = path.read_text()
            if text.count(old) != 1:
                return f"NOT PLANTED: its text is not in {path} exactly once"
            path.write_text(text.replace(old, new))
        return run(answer)
    finally:
        for path, text in originals.items():
            path.write_text(text)


def main() -> int:
    conforming = '{"name": "Owen Wilson"}'
    results = [
        ("1. an answer no parser reads", "XFAIL", run("this is not an answer in any schema")),
        ("2. a conforming answer", "FAILED", run(conforming)),
        ("3. a gateway refusal (401) planted at the adapter", "FAILED",
         planted([(ADAPTER, UNKNOWN_TOKEN)], conforming)),
        ("4. the same refusal under round 2's mark", "XFAIL",
         planted([(ADAPTER, UNKNOWN_TOKEN), (SUITE, OLD_MARK), (SUITE, ROUND_2_CALL)], conforming)),
    ]  # fmt: skip
    bad = 0
    for name, want, got in results:
        ok = got.startswith(want + " ")
        bad += not ok
        print(f"{'ok  ' if ok else 'BAD '} {name}: want {want}; got {got}")
    print(f"{len(results) - bad} of {len(results)} as they must be")
    print(f"adapter put back: {ADAPTER.read_text().count(UNKNOWN_TOKEN[0])}; "
          f"mark put back: {SUITE.read_text().count(OLD_MARK[0])}")  # fmt: skip
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
