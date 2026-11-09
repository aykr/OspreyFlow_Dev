# Platform lane · P5 · report (9 November 2026, the owner's map rulings 1, 6 and 8)

P5 (ADR-147 Amendment 2). Reviews:

- the lane's own;
- the orchestrator's independent review and its ruling (d): a removal deletes no copy;
- the lane's own, twice;
- **the orchestrator's review sending P5 back (round 3)**;
- **the lane's own review of round 3**, which sent it back again (defects 1–14), all answered;
- **the orchestrator's re-review** (items 1, 3, 5–8 confirmed), whose four items and minors are answered here.

Every fix is shown red at its call site in `P5_RED_RECORD.md`. Plants that proved nothing are recorded there and not counted. The session resumed after compaction and found no `HANDOFF.md`. **Head: this commit's, the code gated at `d9b0818`, rebased onto main `15d0d24`.**

## The brief

- **Ruling 1, Java in the Conduit:**
  - jlinked Temurin **21.0.13+9**, October 2026's update, pinned by its index digest (`services/api/Dockerfile`). It was repinned from 21.0.12.1+1, which the new version gate refused.
  - The register's one Classpath exception is in `spec/00` §7, proved by `licence-check`'s image leg (`test_runtime_licences.py`, each refusal red).
  - Built on the test server (amd64): the **image is 1.86 GB** (1,858,960,446 bytes at `dc11181`), of which **`/opt/java` is 62 MB**. planetiler v0.10.2's `--help` **exits 0** under the image's Java.
  - **trivy does not see a jlinked runtime.** The same image from Temurin 21.0.1 (2023, with known CVEs) scans clean, exit 0, as the current one does. trivy names no package of the runtime.
  - In its place, **`tools/java_runtime_check.py`**, which fails closed: anything it cannot read is a refusal in words. Every branch is red offline, through `main` and the fetch's own code.
    - `--image`: the Dockerfile's `org.ospreyflow.runtime.java.version` label must match the built image's `/opt/java/release` `JAVA_VERSION` and its `java -version` build. **This is CI's step** in the `trivy-image-api` job, after its build (**`P5_ci.diff`**, the owner's file). Its own command (`uv run`) on the server: exit 1 over a Temurin 21.0.1 image, exit 0 over the current one.
    - `--current`: the Java stage's pinned digest must be the one `eclipse-temurin:21-jdk` resolves to on Docker Hub now. **The orchestrator's call, over Adoptium's release list:** the tag moves only once an image exists to repin to. So CI is never red for days with nothing to take, and an old commit re-run is red only if its pin is no longer the tag's. On the server: exit 0 on the committed pin, exit 1 on the previous digest. It runs in Build's `make ci` after `core-check` (**`JAVA_RUNTIME_CI.diff`**), never in Core's Makefile, which stands alone. The first draft's line there broke `test_core_stands_alone` and was withdrawn.
    - The image is now built as CI's job builds it, without `--pull`: Docker Hub answered `--pull`'s manifest request with 429 on the server.
  - `java.desktop`'s ten bundled native libraries are registered for the NOTICE (`spec/00` §7), from the image's own notices.
- **Ruling 6, copies in the case's dataset** (`services/api/case_gazetteers.py`, `PUT`/`DELETE /v1/datasets/{dataset}/gazetteers/{gazetteer}`):
  - Copies are matched on `Provenance.gazetteer`, the dataset id of the copy's own unit's gazetteer.
  - Only a place the gazetteer's dataset holds alone is copied.
  - The addition is audited before the copy. *Admin › Audit* files both actions under *Datasets*, as main's census requires. Only the dataset's id is shown, and a test pins it (`test_a_gazetteer_s_addition_shows_its_dataset_alone`).
  - **Every read path withholds a copy's identifiers:**
    - five are red live with their fix removed: `get_node`, `get_nodes` (the seed, node detail at the route), search, suggest by name, and expansion;
    - every deserialiser call in the adapter's whole package is held structurally to its own caller's principal, through a module or not. An import under another name, or a deserialiser handed on as a value, is refused (`test_every_read_withholds_by_its_principal.py`). Red at each of the ten remaining call sites in turn, and at an aliased import.
  - A retracted copy stays a copy, withheld, with its identifiers kept.
  - Ruling (d) stands in place of the brief's removal clause.
- **Ruling 8, the unit a build setting:**
  - *Admin › Maps*, both command-line builds and **the set-up console** (its Geospatial screen's "Unit that holds the place names") take the unit.
  - The console takes any unit the Conduit can name (`org_unit`'s 1 to 60 characters), and refuses only none, an option or a control character. A null counts as none.
  - Its fake runner refuses with the Conduit's own parser, and refuses an unknown unit in the Conduit's own words (`UNKNOWN_UNIT`), which the screen shows.
  - **A fresh install builds its first basemap from *Admin › Maps*.** With no case or dataset yet, the command line and the console refuse every unit, and *Admin › Maps* admits the administrator's own (recorded in the ADR, pinned by a test). If the console must build first, a tiles-only build is the likely next step.
  - The builder's words in *Admin › Maps* name `--unit`.
- **`git`:** the owner ruled for (b): dulwich, under Apache-2.0, as studio-b's carry in L1.7a, and then `git` leaves the image. Until then every `licence-check` run names it as **not yet passed**, with that ruling and carry (asserted). This is in the ADR, `spec/00` §7 and the Dockerfile.

## Gates (`gates/README.md`, round 3 and the re-review)

- **`make -k ci`** at `d9b0818`: **green but this machine's Docker socket** (the eight image scans, `opentofu-check` and `chart-check`; Docker Desktop is off here). The harness axe run passed, the Geospatial screen in dark and light.
- **`make test`**, on the server through `stack_lease.sh offline`, at `d9b0818`: **9774 passed, 2 failed, none the branch's** (the server's GPU preflight case and the Valkey offline pin). test-js: workspace 2814 passed, 1 failed (the Matrix first-frame timing under load, as at every gate; alone it passes); harness 47 passed.
- **Live**, platform lease on **stack e** through `stack_lease.sh remote`, detached, 21:57–22:12 UTC at `dc11181` (code identical to `d9b0818`), on main `15d0d24` (`gates/dc11181.*`):
  - `test_route_rights.py` and both case-gazetteer live files: **15 passed**;
  - the image check: CI's step and `--current`, red and green (above); planetiler `--help` exit 0; trivy exit 0 over both images;
  - `PORT_CONTRACT.diff`'s case green; red with the guard's copy clause dropped, and at the page's `more=True` with the case's earlier checks removed.
  - Released at 22:12.
- Before that, on stack d: the read-path plants, the delta set (372 passed), the retract test.

## Left, for the orchestrator

- The Glass control for a gazetteer (P6).
- The case's dataset picker still offers a gazetteer as a composite (a carry to case).
- The image's source offer and NOTICE (a release step; the register names what it carries).
- The admin guide's `--unit` line (a carry to docs).
- A region of 100,000 places copies in over twenty minutes (a background job is the likely next step).
- `MAP_PATH` is defined in both `harness/geospatial.py` and `cli/ospreyflow/maps.py`. Neither imports the other, so it is left as it is.
- trivy 0.76.2 is out (the gates pin 0.76.1).
- studio-b's `L1.7a_git_leaves_image.diff` is to be applied when dulwich lands (after studio-b's L1.7a merges), not before. Until then `git` stays declared.

## Requests

- **Apply at merge:**
  - `P5_ci.diff`, for the owner (`ci.yml` is theirs): the `trivy-image-api` job's `setup-uv` and `java_runtime_check --image ospreyflow/api:ci` step, after the build.
  - `JAVA_RUNTIME_CI.diff`: Build's `java-runtime-check` target (`--image … --current`), in `ci` after `core-check`. It needs Docker and the network, as the image scans do.
  - `PORT_CONTRACT.diff`: `ports/graph.py`'s docstrings and the conformance case `test_a_gazetteer_copy_matches_a_case_reader_on_its_name_alone`, now with a page's `more`. It applies clean and was proved live.
- **Ratify outside the lane's map:**
  - `services/api/app.py`'s `PUT`/`DELETE` gazetteer routes;
  - `packages/schemas/mapconfig.py` and `generated/CaseGazetteer*.ts`;
  - `services/api/map_admin.py`;
  - `services/api/Dockerfile`;
  - `services/api/audit_section.py`, `test_audit_kinds.py` and `test_audit_section_routes.py` (admin's census: the two actions, the dataset's id alone shown);
  - `harness/geospatial.py`, `harness/webapp.py` and `apps/harness` (the Geospatial screen, its client and test);
  - `OspreyFlow_Core/DEMO_GUIDE.md`;
  - `tools/licence_check.py` and the new `tools/java_runtime_check.py`;
  - and, as before: `packages/ontology/handling.py`, `packages/adapters/graph_arcadedb/builders.py`, `packages/schemas/{domain,merge}.py`, `test_route_rights.py`, `test_investigation_levels.py`, spec 00, 03 and 06, and `placesByRole.json`.
- **Mark ADR-147 Amendment 2 written** in `ADR_RESERVATIONS.md`.

**Questions:** none. **Running:** nothing; no stack held.
