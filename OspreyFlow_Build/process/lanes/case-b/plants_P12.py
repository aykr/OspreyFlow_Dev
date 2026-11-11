"""P12 part 1's red record, reproducible (rule 15): each plant breaks one refusal or rule at the call site
its test reaches, runs that test, and puts the file back. Run from `OspreyFlow_Core`, offline with the
closed ports pinned (59991-59994):

    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_P12.py            # Conduit's env
    .venv/bin/python ../OspreyFlow_Build/process/lanes/case-b/plants_P12.py --laurium \
        ../OspreyFlow_Build/laurium-env/.venv/bin/python                                # Laurium's env

(`make -C ../OspreyFlow_Build laurium-service` builds Laurium's environment first.) Each row prints the
plant, the tests run and pytest's tally; every plant must fail at least one test, with no error (a plant
that breaks collection proves nothing). A plant whose text is not found is itself a failure.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

B = "../OspreyFlow_Build/tests"
SETTINGS_T = f"{B}/services/laurium/test_settings.py"
SCHEMA_T = f"{B}/services/laurium/test_schema_map.py"
GATE_T = f"{B}/services/laurium/test_licence_gate.py"
ADAPTER_T = f"{B}/adapters/extract_laurium/test_adapter.py"
FINDINGS_T = f"{B}/adapters/extract_laurium/test_findings_inferred.py"
RECORDED_T = f"{B}/licence_check/test_recorded_licence_evidence.py"
NOLC_T = f"{B}/test_no_langchain_check.py"
SERVICE_T = f"{B}/conformance/model_port/test_laurium_service.py"
SUITE_T = f"{B}/conformance/model_port/test_suite_extract.py"
PENDING_T = f"{B}/conformance/model_port/test_laurium_findings_pending.py"
REVIEW = "services/api/review.py"
HTTP = "../OspreyFlow_Build/tests/conformance/model_port/stand_in_http.py"
#: The real store's own write, promoting: what rule 5 forbids, at the one place a candidate is written.
PROMOTE = ("                status=CandidateStatus.PENDING,\n                owning_unit=principal.org_unit,",
           "                status=CandidateStatus.ACCEPTED,\n                owning_unit=principal.org_unit,")
#: Decision 8: a call for the deployment's own models, or outside the routing, sent with the master key.
MASTER_KEY = ("            token = laurium_key(self._master)\n", "            token = self._master\n")

S = "services/laurium/settings.py"
M = "services/laurium/schema_map.py"
G = "services/laurium/licence_gate.py"
APP = "services/laurium/app.py"
A = "packages/adapters/extract_laurium/adapter.py"
KEYS = "packages/adapters/extract_laurium/keys.py"
LC = "../OspreyFlow_Build/tools/licence_check.py"
NL = "../OspreyFlow_Build/tools/no_langchain_check.py"

Plant = tuple[str, str, list[tuple[str, str]], list[str]]

OFFLINE: list[Plant] = [
    # --- the service's start check (ADR-135 Amendment 6 decision 4) ---
    ("a gateway URL of any host accepted", S,
     [("        and parts.hostname == GATEWAY_HOST\n", "")], [SETTINGS_T]),
    ("a credential in the gateway URL accepted", S,
     [("        and parts.username is None\n        and parts.password is None\n"
       "        and \"@\" not in parts.netloc\n", "")], [SETTINGS_T]),
    ("a path or a query on the gateway URL accepted", S,
     [("        and parts.path.rstrip(\"/\") in (\"\", \"/v1\")\n        and not parts.query\n", "")],
     [SETTINGS_T]),
    ("a gateway URL with no port accepted", S,
     [("        and port is not None\n", "")], [SETTINGS_T]),
    ("HTTPS_PROXY not read", S, [('    "HTTPS_PROXY",\n', "")], [SETTINGS_T]),
    ("AWS's endpoints not read", S,
     [("            if key in _HOST_SETTINGS or _AWS_ENDPOINT.match(key):",
       "            if key in _HOST_SETTINGS:")], [SETTINGS_T]),
    ("LangSmith tracing on accepted", S,
     [("            elif key in _TRACING and value.strip().lower() not in _OFF:",
       "            elif False:")], [SETTINGS_T]),
    ("one spelling of a name read, the last", S,
     [("        for name, value in sorted(env.items()):",
       "        for name, value in {k.upper(): (k, v) for k, v in env.items()}.values():")],
     [SETTINGS_T]),
    ("the resolver's own settings not read", S,
     [('    "LOCALDOMAIN",\n    "RES_OPTIONS",\n    "HOSTALIASES",\n', "")], [SETTINGS_T]),
    ("a debug log of each request accepted", S,
     [("            elif key in _LOGGING_SETTINGS:", "            elif False:")], [SETTINGS_T]),
    ("an unknown OSPREY_LAURIUM_ setting ignored", S,
     [("            if name.startswith(_OURS) and name not in _KNOWN:", "            if False:")],
     [SETTINGS_T]),
    ("a setting's value repeated in the words", S,
     [('                        f"{name} is set: it names a host',
       '                        f"{name}={value} is set: it names a host')],
     [SETTINGS_T]),
    # --- the domain model mapped to Laurium's schema (decision 6) ---
    ("an enum given as any string", M,
     [("        return Literal[tuple(values)]", "        return str")], [SCHEMA_T]),
    ("an item allowed properties it does not declare", M,
     [('__config__=ConfigDict(extra="forbid")', '__config__=ConfigDict(extra="ignore")')],
     [SCHEMA_T]),
    ("a top-level property not required accepted", M,
     [("    if missing:\n", "    if False:\n")], [SCHEMA_T]),
    ("an object allowing undeclared properties accepted", M,
     [('    if schema.get("additionalProperties", False) is not False:', "    if False:")],
     [SCHEMA_T]),
    ("an optional property's null kept in the output", M,
     [("            if not (item is None and key not in required)", "            if True")],
     [SCHEMA_T]),
    ("a description's braces left single", M,
     [('        out[name] = words.replace("{", "{{").replace("}", "}}")', "        out[name] = words")],
     [SCHEMA_T]),
    ("a combinator beside a type given as the type alone", M,
     [("    if combined:\n", "    if False:\n")], [SCHEMA_T]),
    # Rule 15's second clause (the orchestrator's review, 11 November): each case now has `required`,
    # so it reaches its own refusal; this one was refused at the top level before `_type` ran.
    ("an enum of anything but strings given to Laurium", M,
     [("        if kind != \"string\" or not values or not all(isinstance(v, str) for v in values):\n"
       "            raise UnsupportedSchema(f\"{name!r}: only an enum of strings is supported\")\n", "")],
     [SCHEMA_T]),
    # --- the thin adapter (decision 3) ---
    ("the request's schema not checked before the call", A,
     [("            Draft202012Validator.check_schema(req.json_schema)\n", "            pass\n")],
     [ADAPTER_T]),
    ("the answer trusted without the request's schema", A,
     [("            Draft202012Validator(req.json_schema).validate(data)\n", "            pass\n")],
     [ADAPTER_T]),
    ("an engine's call sent without its own key", A,
     [("                    token = engine_key(self._master, call.engine)\n", "                    pass\n")],
     [ADAPTER_T]),
    ("a call for the deployment's own models sent with the master key", A, [MASTER_KEY], [ADAPTER_T]),
    ("Laurium's key derived from an empty master key", KEYS,
     [("    if not master.strip():\n        raise ValueError(\"no master key: Laurium's key",
       "    if False:\n        raise ValueError(\"no master key: Laurium's key")],
     [ADAPTER_T]),
    ("Laurium's key made for every model", KEYS,
     [("    if not models:\n        raise ValueError(", "    if False:\n        raise ValueError(")],
     [ADAPTER_T]),
    ("Laurium's key derived as an engine's", KEYS,
     [('_LABEL = b"osprey-service:laurium"', '_LABEL = b"osprey-engine:laurium"'),
      ('    return "sk-osprey-laurium-" + hmac', '    return "sk-osprey-" + hmac')],
     [ADAPTER_T]),
    # Rule 5 (the orchestrator's review, item 6): the real store's write, promoting.
    ("the review queue's write promoting a finding", REVIEW, [PROMOTE], [FINDINGS_T]),
    ("an engine's call sent untagged", A, [('            "tag": tag,\n', '            "tag": None,\n')],
     [ADAPTER_T]),
    ("a limit's refusal not read as a limit", A,
     [("            if limit is not None:\n                return limit\n", "")], [ADAPTER_T]),
    ("a model not offered not told apart", A,
     [("        if status == 404:\n", "        if False:\n")], [ADAPTER_T]),
    ("the gateway's words passed on by the adapter (a 429 not a limit)", A,
     [('            f"The model gateway refused Laurium\'s call for model {model!r} (HTTP {status})."',
       '            f"The model gateway refused: {said}"')], [ADAPTER_T]),
    ("an answer of another shape escaping untyped", A,
     [('        data = answer.get("data") if isinstance(answer, dict) else None',
       '        data = answer.get("data")')], [ADAPTER_T]),
    ("a finding traced to another document", A,
     [("        return ExtractionResult(document_id=req.document_id, model=req.model, data=data)",
       '        return ExtractionResult(document_id="other", model=req.model, data=data)')],
     [FINDINGS_T]),
    # --- the licence record (decision 7) ---
    ("a recorded entry admitting any version", LC,
     [("        key in RECORDED_LICENCE_EVIDENCE\n        and (declared",
       "        any(k[0] == key[0] for k in RECORDED_LICENCE_EVIDENCE)\n        and (declared")],
     [RECORDED_T]),
    ("a recorded entry admitting a declared GPL", LC,
     [("        and not _GPL.search(declared)\n", "")], [RECORDED_T]),
    ("a recorded entry admitting a declared LGPL", LC,
     [("        and not _LGPL.search(declared)\n", "")], [RECORDED_T]),
    ("a recorded entry admitting any other declared licence", LC,
     [('        and (declared in ("", "unknown") or bool(_word("mit").search(declared)))\n', "")],
     [RECORDED_T]),
    ("the image's gate tool installed without hashes", "services/laurium/Dockerfile",
     [("RUN pip install --require-hashes --only-binary :all: --no-deps -r licence-gate.txt",
       "RUN pip install pip-licenses==5.5.5")], [GATE_T]),
    ("a recorded name matched only as spelt", LC,
     [('    key = (_normalised(package.get("Name", "")),', '    key = (package.get("Name", ""),')],
     [RECORDED_T]),
    ("the recorded entries not consulted", LC,
     [("        if not is_allowed(p[\"License\"], package=p.get(\"Name\")) and not recorded(p)",
       "        if not is_allowed(p[\"License\"], package=p.get(\"Name\"))")], [RECORDED_T]),
    ("the image gate letting the encoder's packages through", G,
     [("        and (encoder(p) or not (is_allowed", "        and (not (is_allowed")], [GATE_T]),
    ("the image gate's entries parting from the repository's", G,
     [('    ("tiktoken", "0.14.0"): "MIT, its full text', '    ("tiktoken", "0.15.0"): "MIT, its full text')],
     [GATE_T]),
    # --- no LangChain without Laurium (decision 1) ---
    ("Laurium's folder left in the Conduit's context unnoticed", NL,
     [("    if kept:\n", "    if False:\n")], [NOLC_T]),
    ("only the folder's own spelling read, not the matcher (as it was)", NL,
     [("    kept = [path for path in _laurium_files(core) if not spec.match_file(path)]",
       '    kept = [] if "services/laurium" in text.splitlines() else ["services/laurium"]')],
     [NOLC_T]),
    ("a file a negation puts back not looked at", NL,
     [('_LAURIUM_FILES = ("Dockerfile", "requirements.txt", "requirements.in", "app.py")',
       '_LAURIUM_FILES = ("Dockerfile", "requirements.txt", "requirements.in")')], [NOLC_T]),
    ("the source leg run in an image step", NL,
     [("    problems = [] if args.image else source_problems()", "    problems = source_problems()")],
     [NOLC_T]),
    ("LangChain or Laurium in the Conduit's lock unnoticed", NL,
     [("if _FORBIDDEN_IN_SOURCE.match(n))", "if False)")], [NOLC_T]),
    ("another Dockerfile or requirements file naming LangChain unnoticed", NL,
     [("        if bad:\n            relative", "        if False:\n            relative")], [NOLC_T]),
    ("requirements files not read", NL,
     [('        for pattern in ("*requirements*.txt", "*requirements*.in")',
       "        for pattern in ()")], [NOLC_T]),
    ("Laurium's own folder not passed", NL,
     [('    return parts[:2] != ("services", "laurium") and', "    return")], [NOLC_T]),
    ("an image's LangChain unnoticed", NL,
     [("            if _FORBIDDEN.match(_normalised(str(row[\"name\"])))", "            if False")],
     [NOLC_T]),
    ("an unreadable image passed", NL,
     [("        raise Unreadable(f\"the image's installed distributions could not be read: {exc}\") from None",
       "        return []")], [NOLC_T]),
]

LAURIUM: list[Plant] = [
    ("the service serving with a refused setting", APP,
     [("    print(str(refused), file=sys.stderr, flush=True)\n    raise SystemExit(78) from None",
       "    SETTINGS = Settings(gateway_url=\"http://litellm:4000\")")], [SERVICE_T]),
    ("a gateway refusal answered as Laurium's row of Nones", APP,
     [('            return _refused(502, "gateway", **refusal)',
       "            return ExtractAnswer(document_id=ask.document_id, model=ask.model, "
       "data=dict.fromkeys(fields), engine=ENGINE)")], [SERVICE_T, SUITE_T]),
    # Two layers keep the gateway's words (which name part of a key) from the Conduit's errors: the
    # service forwards a 429's error alone, and the adapter answers in fixed words. Both planted.
    ("the gateway's words passed on, by the service and the adapter", APP,
     [("            if exc.status_code == 429:\n                try:",
       "            if True:\n                try:"),
      ('            f"The model gateway refused Laurium\'s call for model {model!r} (HTTP {status})."',
       '            f"The model gateway refused: {said}"', A)], [SERVICE_T]),
    ("the OpenAI client's own retries left on", APP,
     [("    llm.client = llm.root_client.with_options(max_retries=0).chat.completions\n"
       "    llm.async_client = llm.root_async_client.with_options(max_retries=0).chat.completions\n",
       "")], [SERVICE_T]),
    ("a call without the gateway's token sent on", APP,
     [("    if not token:\n", "    if False:\n")], [SERVICE_T]),
    ("a text over the limit read", APP,
     [("    if len(ask.text) > MAX_CHARS:\n", "    if False:\n")], [SERVICE_T]),
    ("an unparseable answer asked once", APP, [("    for _ in range(ATTEMPTS):", "    for _ in range(1):")],
     [SERVICE_T]),
    ("the call's tag not sent to the gateway", APP,
     [('        call["extra_body"] = {"metadata": {"tags": [ask.tag]}}', "        pass")], [SERVICE_T]),
    ("a description's braces left single, through the real prompt", M,
     [('        out[name] = words.replace("{", "{{").replace("}", "}}")', "        out[name] = words")],
     [SERVICE_T, SUITE_T]),
    # Item 4 of the orchestrator's review: another host refused at the call that picks it. Without
    # `openai_api_base`, Laurium's `create_llm` leaves the OpenAI client at its own default host.
    ("the gateway not given to Laurium's chat model", APP,
     [("        openai_api_base=SETTINGS.gateway_url,\n", "")], [SERVICE_T]),
    ("the lookup letting another name resolve (the fixture itself)", HTTP,
     [("        refused.append(host.decode() if isinstance(host, bytes) else str(host))\n"
       "        raise socket.gaierror(socket.EAI_NONAME, \"Name or service not known\")\n",
       "        return real(host, *args, **kwargs)\n")], [SERVICE_T]),
    # Item 1: the `/v1` base the settings accept, as LiteLLM serves it.
    ("the gateway's /v1 route not served (the stand-in as it was)", HTTP,
     [('_V1_ALIASES = ("/v1/chat/completions",)', "_V1_ALIASES = ()")], [SERVICE_T, PENDING_T]),
    # Item 7: the master key never crosses into Laurium's container.
    ("a call for the deployment's own models sent with the master key", A, [MASTER_KEY], [SERVICE_T]),
    # Item 6: rule 5 through the real service and the real store's write.
    ("the review queue's write promoting a finding", REVIEW, [PROMOTE], [PENDING_T]),
]

#: No bytecode is written while a plant is in: found running this, a plant that changed `0.14.0` to
#: `0.15.0` and was put back in the same second left its `.pyc` (same size, same mtime) standing for
#: the restored file, and the next run read the plant.
ENV = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "VALKEY_PORT": "59993",
       "CLICKHOUSE_HTTP_PORT": "59994", "PYTHONDONTWRITEBYTECODE": "1"}  # fmt: skip
ENV.pop("OSPREY_case-b", None)


def run(python: str, tests: list[str]) -> str:
    out = subprocess.run(
        [python, "-m", "pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p", "no:cacheprovider",
         *tests], capture_output=True, text=True, env=ENV, check=False,  # fmt: skip
    )
    tail = [line for line in out.stdout.splitlines() if re.search(r"\d+ (passed|failed|error)", line)]
    return tail[-1] if tail else out.stdout[-300:]


def main() -> int:
    python = sys.executable
    plants = OFFLINE
    if "--laurium" in sys.argv:
        python = sys.argv[sys.argv.index("--laurium") + 1]
        plants = LAURIUM
    start = run(python, sorted({t for _, _, _, tests in plants for t in tests}))
    print(f"green start: {start}")
    if "failed" in start or "error" in start:
        return 1
    bad = 0
    for name, path, edits, tests in plants:
        # An edit is (old, new), in the plant's own file, or (old, new, another file).
        originals: dict[pathlib.Path, str] = {}
        planted: dict[pathlib.Path, str] = {}
        missing = False
        for edit in edits:
            file = pathlib.Path(edit[2] if len(edit) > 2 else path)  # type: ignore[misc]
            originals.setdefault(file, file.read_text())
            text = planted.get(file, originals[file])
            if text.count(edit[0]) != 1:
                print(f"NOT PLANTED  {name}: its text is not in {file} exactly once")
                missing = True
                break
            planted[file] = text.replace(edit[0], edit[1])
        if missing:
            bad += 1
            continue
        try:
            for file, text in planted.items():
                file.write_text(text)
            tally = run(python, tests)
        finally:
            for file, text in originals.items():
                file.write_text(text)
                later = file.stat().st_mtime + 2  # any older bytecode is stale, whatever its size
                os.utime(file, (later, later))
        red = "failed" in tally and "error" not in tally
        bad += not red
        print(f"{'red  ' if red else 'GREEN'}  {name}: {tally}")
    print(f"{len(plants)} plants, {len(plants) - bad} red")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
