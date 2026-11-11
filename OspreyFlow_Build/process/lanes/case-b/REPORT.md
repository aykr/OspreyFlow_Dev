# case-b · P12 part 1 (Laurium as its own service) · report, 11 November 2026 (the test server)

**Exit (part 1).**
- **ADR-135 Amendment 6, met**, written first (f6f85fcf), from LICENCE_CHECK's ruling.
- **Laurium's service, met**: `services/laurium/`, Python 3.13 (`python:3.13-slim@sha256:e48f59cd…`), Laurium 0.6.0 and `en-core-web-sm` 3.8.0 (Explosion's release) by hash, every install `--require-hashes`, never the `encoder` extra (the image gate refuses it). Builds; its licence gate passes 126 packages. Another host refused at start, planted: `test_settings.py`, `test_laurium_service.py::test_a_setting_naming_another_host_stops_the_service_at_start`.
- **The adapter, met**: `packages/adapters/extract_laurium/`, schema checked before the call and the answer after, typed refusals in our words, the engine's tag and key. Findings reach the review queue as located candidates (`test_findings_inferred.py`), *inferred* until accepted (rule 5).
- **The suite on both engines, met** through the stand-in served over HTTP as `litellm`: `test_suite_extract.py` (6 cases × 2) plus the service's 14, 26 passed in Laurium's environment (`make laurium-service`). The stand-in is the measured one, unchanged.
- **No LangChain without Laurium, met** at the source (`tools/no_langchain_check.py`, `make ci` via `P12_MAKEFILE.diff`), the image leg in `P12_CI.diff`. **Licence record, met**: §7 entry, `RECORDED_LICENCE_EVIDENCE` (three entries), MoJ notices.
- **Red record**: 45 offline and 9 live plants, all red (`P12_RED_RECORD.md`, `plants_P12.py`).
- **Lane-reviewer, run**: do not merge, 11 findings, all fixed and planted (SERVER_LOG "The lane-reviewer's round").

**Gates** (main unmoved, at 459ae1d4): make test at 310648a1 5 failed / 10982 passed. make -k ci at a5fa3c1b failed only in core-check. Each failure explained in `gates/`: the scratch venv; main's libxslt; the server's own; a11y not run.

**Left, and why.** Not run here, since each asks for approval: `docker run` of the image (its start refusal; the image leg on real images), `trivy` on Laurium's image, a11y with slot 3. Not done yet: Laurium's request against the real gateway (rule 15), and the Superset image's LangChain. Part 2 waits for P7 and P11 part 1.

**Commits**: f6f85fcf…a5fa3c1b on `lane/case-b-p12`, never pushed.

**Requests**: apply both diffs at merge; accept the `pyproject.toml` mypy override and the `harness/service_inventory.py` row; `rm -rf OspreyFlow_Core/services/laurium/.venv`.

**Questions for the owner**: none that stop the work (SERVER_LOG, "Questions held"). Nothing of mine is still running.
