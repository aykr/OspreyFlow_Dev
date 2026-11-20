# ruff: noqa: E501
"""The owner's key review of 15 November 2026 (`process/lanes/admin-forms/KEY_REVIEW_2026-11-15.md`,
rulings 21 to 28): one plant per fix and per P-item, each at its real call site, in the shape the code
really receives, run red against the test that names it, then the file put back from the text saved
before the plant (never from git). Run from the worktree root after a commit, offline on closed ports,
with OspreyFlow_Core's own venv. P8 (the browser) is run at the orchestrator's slot, not here."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
ADMIN = CORE / "services/api/model_admin.py"
APP = CORE / "services/api/app.py"
KEYS = CORE / "services/api/model_keys.py"
CLI = CORE / "cli/ospreyflow/main.py"
REVIEW = "../OspreyFlow_Build/tests/services/api/test_model_key_review.py"
CHECKS = "../OspreyFlow_Build/tests/services/api/test_model_engine_checks.py"
COMMANDS = "../OspreyFlow_Build/tests/services/api/test_model_keys_commands.py"
VERB = "../OspreyFlow_Build/tests/cli/test_models_verb.py"
PLANTS = [
    # Fix A, rulings 22 and 23.
    ("A(3): a refused model's answer echoes the typed name", ADMIN,
     'words=f"{jobs}: {words}"', 'words=f"{model}: {words}"',
     "said_by_its_job or model_name_box", REVIEW),
    ("A(1): the audit records each typed name, not the job", ADMIN,
     'outcomes = ", ".join(f"{r}: {m.outcome}" for m in result.models for r in m.roles)',
     'outcomes = ", ".join(f"{provider.roles[r]}: {m.outcome}" for m in result.models for r in m.roles)',
     "said_by_its_job", REVIEW),
    ("A(2): any model name taken (ruling 23's shape removed)", ADMIN,
     "    if not _MODEL_NAME.fullmatch(name):\n", "    if False:\n",
     "taken_only_if_it_looks_like_one", REVIEW),
    ("A: a UUID taken as a model name", ADMIN,
     "    if any(model_looks_like_a_key(part) for part in parts) or _UUID.fullmatch(name):\n",
     "    if any(model_looks_like_a_key(part) for part in parts):\n",
     "taken_only_if_it_looks_like_one", REVIEW),
    # Fix B: a field not on the list named by what was sent.
    # Where a sent name reaches `refused_field` (a key under `roles`; an extra field is answered
    # before it, plant 6): its last line is defended by that earlier branch, so a plant there was not
    # caught, and is not the shape a sent name takes.
    ("B: a key sent as a job's name is named back", ADMIN,
     "            if parts[2] not in JOB_WORDS:\n                return \"provider.roles\", JOBS_ARE\n",
     "            if parts[2] not in JOB_WORDS:\n                return f\"provider.roles.{parts[2]}\", JOBS_ARE\n",
     "key_shaped_field_name", REVIEW),
    ("B: an extra field answered by its own name, not in fixed words", APP,
     '        if not e["loc"] or e["type"] in ("extra_forbidden", "json_invalid"):\n            return {"error": error, "detail": refused}\n',
     '        if not e["loc"]:\n            return {"error": error, "detail": refused}\n        if e["type"] == "extra_forbidden":\n            fields.append({"field": ".".join(str(p) for p in e["loc"]), "words": "not allowed"})\n            continue\n',
     "key_shaped_field_name", REVIEW),
    # Fix C: a validator's own words, which may quote what was sent in another form.
    ("C: a validator's words in place of the field's fixed words", APP,
     '        fields.append({"field": named[0], "words": named[1]})\n',
     '        fields.append({"field": named[0], "words": str(e.get("msg", ""))})\n',
     "fixed_words_never_the_validator", REVIEW),
    # Fix D and P3: an unexpected error.
    ("D/P3: a failed gateway call logged with its body", ADMIN,
     '        except httpx.HTTPError:\n            raise ModelAdminRefused(\n                "The model gateway could not be reached; the change was not saved.", status=502\n            ) from None\n        return resp',
     '        except httpx.HTTPError:\n            raise ModelAdminRefused(\n                "The model gateway could not be reached; the change was not saved.", status=502\n            ) from None\n        except Exception:\n            log.warning("the gateway call to %s failed with %s", path, body)\n            raise\n        return resp',
     "unexpected_transport_error", REVIEW),
    ("D/P3: a check's key left when its call fails unexpectedly", ADMIN,
     "            except BaseException:\n                # Its key goes with the refusal; the record too, where it can still be written\n                # (else the sweep removes it, and nothing else of it is left).\n                if not provider.keyless:\n                    await self._gateway.delete_credential(provider.name)\n",
     "            except BaseException:\n                # Its key goes with the refusal; the record too, where it can still be written\n                # (else the sweep removes it, and nothing else of it is left).\n",
     "unexpected_transport_error", REVIEW),
    # P4: what only a record formatted whole, or the process's own output, shows.
    ("P4: a refusal logged with the key in its traceback (exc_info)", ADMIN,
     "                    if not provider.keyless:\n                        await self._gateway.delete_credential(provider.name)\n                    self._save(unchecked)\n",
     "                    if not provider.keyless:\n                        await self._gateway.delete_credential(provider.name)\n                        log.info(\"check refused\", exc_info=RuntimeError(key.get_secret_value() if key else \"\"))\n                    self._save(unchecked)\n",
     "appears_nowhere_it_must_not or odd_shaped", CHECKS + " " + REVIEW),
    ("P4: the key printed to the process's own output", ADMIN,
     "                passed = record.model_copy(update={\"passed\": True})\n",
     "                print(key.get_secret_value() if key else \"\")\n                passed = record.model_copy(update={\"passed\": True})\n",
     "appears_nowhere_it_must_not or odd_shaped", CHECKS + " " + REVIEW),
    # P5: a file beside the models file.
    ("P5: the key left in a temporary beside the models file", ADMIN,
     "                passed = record.model_copy(update={\"passed\": True})\n",
     "                (self._file.path.parent / \".models-check.tmp\").write_text(key.get_secret_value() if key else \"\")\n                passed = record.model_copy(update={\"passed\": True})\n",
     "appears_nowhere_it_must_not or odd_shaped", CHECKS + " " + REVIEW),
    # P6 and P7: the commands.
    ("P6: model_keys set prints the key it set", KEYS,
     '            print(f"key set for {args.name}")\n',
     '            print(f"key set for {args.name}: {key}")\n',
     "set_from_the_variable", COMMANDS),
    ("P7: ospreyflow models key passes the key as an argument", CLI,
     '            [*in_conduit, "-e", engine_keys.KEY_GIVEN, "api", *engine_keys.KEY_PATH,',
     '            [*in_conduit, "-e", f"{engine_keys.KEY_GIVEN}={key}", "api", *engine_keys.KEY_PATH,',
     "refused_key_is_in_no_output", VERB),
    # P9: a key not sent as text, or in the address.
    ("P9: a key body refused with pydantic's own words (the input in them)", APP,
     '    except ValueError:\n        raise HTTPException(\n            status_code=422, detail={"error": "key_refused", "detail": _KEY_BODY_REFUSED}\n        ) from None',
     '    except ValueError as invalid:\n        raise HTTPException(\n            status_code=422, detail={"error": "key_refused", "detail": str(invalid)}\n        ) from None',
     "not_sent_as_text", REVIEW),
    ("P9: a key in the address read past", APP,
     "    if request.url.query:\n", "    if False:\n", "in_the_address", REVIEW),
    # The owner's ruling 25: a Conduit stopped mid-check.
    ("25: the check's key handed over before its record is written", ADMIN,
     "            self._save(current)\n            unchecked = current.model_copy(\n",
     "            unchecked = current.model_copy(\n",
     "stopped_after_its_key", REVIEW),
]
env = {**os.environ, "ARCADEDB_HTTP_PORT": "59991", "POSTGRES_PORT": "59992", "POSTGRES_PASSWORD": "throwaway",
       "VALKEY_PORT": "59993", "CLICKHOUSE_HTTP_PORT": "59994", "MINIO_ENDPOINT": "localhost:59995",
       "OPENSEARCH_PORT": "59999"}
env.pop("OSPREY_LANE", None)
red = 0
for i, (what, path, old, new, k, files) in enumerate(PLANTS, 1):
    saved = path.read_text(encoding="utf-8")
    assert saved.count(old) == 1, what
    path.write_text(saved.replace(old, new), encoding="utf-8")
    try:
        env["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp()
        done = subprocess.run([str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", *files.split(), "-k", k],
                              check=False, cwd=CORE, env=env, capture_output=True, text=True)
        last = done.stdout.strip().splitlines()[-1]
        state = "RED" if done.returncode != 0 and "failed" in last else "GREEN (the plant was not caught)"
        red += state == "RED"
        print(f"plant {i}: {what}\n  -k '{k}': {state} ({last})")
    finally:
        path.write_text(saved, encoding="utf-8")
print(f"{red}/{len(PLANTS)} red")
raise SystemExit(0 if red == len(PLANTS) else 1)
