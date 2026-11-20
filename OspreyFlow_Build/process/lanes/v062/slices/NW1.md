# Slice NW1 · NW1 · A start needs no network once installed (model weights pulled only when absent, the download step offline, a test that starts with every pull refused)

- **Build id:** NW1 (in the plan: "A start needs no network once installed: model weights are pulled only when absent, the download step runs offline, and a test starts the product with every pull refused").
- **Dial setting:** balanced
- **Rounds limit:** 4
- **After:** nothing. It touches no file under apps/workspace. **The owner's order (20 November): cut as a new build, small, beside SE6a; the failing test first (a start with every pull refused); fixed before DC1's wording, with SE6a and SE7 — DC1b and DC1c need SE6a, SE7 and NW1 merged.**
- **Status of this brief:** written by the conductor on 20 November 2026 from a read-only scout of the same day. The scout's line numbers are unchecked: the builder re-reads. Not measured by anyone: nothing was run.

## What the scout found (read, not measured)

On a start with no network, the stack would fail at the weights step, even with the weights already on the machine. `OspreyFlow_Core/harness/render.py` (about lines 1232 to 1254) and the generated compose (`OspreyFlow_Core/deploy/generated/local-lite/compose.yaml`, about lines 248 to 336) have two one-shot jobs that reach outside on **every** start:

- **ollama-models** (compose about lines 248 to 269): a script with `set -e` that runs `ollama pull "$model"` for each model, **unconditionally** (render.py about line 142: a digest check after it and no existence check before it). Nothing depends on it by `depends_on`, but `docker compose up -d --wait` (`harness/apply.py` about lines 1230 and 1677) counts an exited container as a failure unless a service waits on it (render.py about lines 181 to 183), so a failed pull fails the start although ollama itself is up. Whether `ollama pull` of a model already present still contacts the registry is Ollama's behaviour and **not verified**: verify it.
- **whisper-models** (compose about lines 312 to 326): `huggingface-cli download Systran/faster-whisper-tiny.en && chown ...`, with **no offline flag**, restart `no`; the `whisper` service (about lines 327 to 336) waits on it with `service_completed_successfully` and itself runs with `HF_HUB_OFFLINE=1`. If the download exits non-zero, whisper never starts. Whether the CLI falls back to the cache when the hub is unreachable is **not verified**: verify it.
- The proxy joins the egress network; whether an https Small deployment fetches a certificate at start was not read (OspreyFlow_Core/harness/site.py about lines 80 to 92 covers the plain and organisation-certificate branches). `harness/apply.py` about line 1661 runs `build --pull` in the update path: check a plain start does not.
- No test in the repository starts the stack with networking off (`.github/workflows/exit-tests.yml` has no match for offline or network; `tests/harness/test_render_egress.py` asserts the reach-out set statically from the render).

## What

1. **The failing test first, at the real call site (rule 15):** a pure test that renders the compose for the local-lite profile, takes the two jobs' scripts exactly as rendered, and **runs them under `sh` with a PATH of stubs** in which every pull and download command **refuses** (exits non-zero, writes its call to a log, and does what the real ones do on no network: the stubs model the real tools' refusals; where the real tool's offline behaviour is not known, read its documentation or source in the pinned image and say what you found). Case A: the model volumes already hold the models (a temp directory laid out as the real volume): the job exits 0 and makes **no** pull or download call. Case B: a model is absent and the pull is refused: the job exits non-zero **and says so in words** (what is missing, that the network is needed once, what to do). Red on main for the right reason (case A fails: the job exits non-zero or calls the registry).
2. **The fix:** each job pulls or downloads only what is absent, checks before it pulls (with a check that needs no network), sets the offline flag on the download when the file is present, and still fails loudly, in words, when something it needs is absent and the network is refused. A start with everything present and every pull refused succeeds. Keep the digest check after a pull that does happen.
3. **Read and report** (no change unless a fault): whether a plain start fetches anything else (the https Small certificate, `build --pull`, an update check, image pulls when the images are present), with the file and line, so DC1's wording is true.
4. **Spec and guide:** if the specification or the administration guide says a start needs the network, correct it; the administration guide's document-control row follows its rule (a new numbered row; the PDF is made by the conductor at merge, so if `test_docs_pdf` goes red on the changed guide say so and do not edit PDFs).
5. **Not in this slice:** a complete first-install bundle (weights, packages, map tiles): a separate row; the update path.

Binding: process/CLAUDE.md rules 11, 12, 15; spec/00_ARCHITECTURE.md (egress); British English; no client named. You do not edit the Core Makefile, `ci.yml` or any CLAUDE.md. No file under apps/workspace.

## Checks

Pure only (`ARCADEDB_HTTP_PORT=9 POSTGRES_PORT=9`): the new test, `test_render_egress.py`, `test_render_external.py`, the render tests that pin the local-lite compose (`OspreyFlow_Build/tests/harness/test_render*.py`), the generated-compose check if the repository holds one, `ruff check .` in OspreyFlow_Core and the scan-map check for the new test. **Regenerate the checked-in generated compose from the renderer if the repository keeps one** (OspreyFlow_Core/deploy/generated), never by hand. **Before your final report run by hand the cheap checks the conductor will run again before the merge.** A merge attempt costs 25 minutes.
