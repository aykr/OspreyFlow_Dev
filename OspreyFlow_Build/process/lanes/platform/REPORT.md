# Platform lane · P5 · report (9 November 2026, the owner's map rulings 1, 6 and 8)

P5 (ADR-147 Amendment 2). Reviews so far:

- the lane's own;
- the orchestrator's independent review and its ruling (d): a removal deletes no copy;
- the lane's own, twice;
- the orchestrator's review sending P5 back (round 3), answered here;
- the lane's own over round 3.

Every fix is shown red at its call site in `P5_RED_RECORD.md`. Plants that proved nothing are recorded there and not counted. The session resumed after compaction and found no `HANDOFF.md`. It was rebased onto main `3790da0` for round 3, then onto main `e76cef9` at the end (one conflict, both amendments kept), and is now at head `ce36c3f`.

## The brief

- **Ruling 1, Java in the Conduit:**
  - jlinked Temurin **21.0.13+9**, October 2026's update, pinned by its index digest (`services/api/Dockerfile`). It was repinned in round 3 from 21.0.12.1+1, which `java-runtime-check --latest` refused.
  - The register's one Classpath exception is in `spec/00` §7. `licence-check`'s image leg proves it, with each refusal red (`tests/licence_check/test_runtime_licences.py`).
  - Built on the test server (amd64): the **image is 1.86 GB**, of which `/opt/java` is **62 MB**. planetiler v0.10.2's `--help` **exits 0** under the image's Java (`gates/360c83c.image-repinned.txt`).
  - **trivy does not see a jlinked runtime.** The same image from Temurin 21.0.1 (October 2023, with known CVEs) scans clean, as the current one does: 118 Debian, 12 jar and 58 Python packages, none of them Java (`gates/360c83c.image-old-pin.txt`).
  - In that gap, `tools/java_runtime_check.py`, run by `make trivy-image-api`, holds the image to its declared label. The image's `/opt/java/release` `JAVA_VERSION` must match the label, its `java -version` build must match the label, and the label must be Temurin 21's newest. Over the old image it is red both ways, over the repinned image green. Each branch is red offline (`tests/licence_check/test_java_runtime_check.py`).
  - `java.desktop`'s ten bundled native libraries are registered for the NOTICE (`spec/00` §7). The licences come from the image's own `legal/` notices.
- **Ruling 6, copies in the case's dataset:**
  - Done by `services/api/case_gazetteers.py`, through `PUT`/`DELETE /v1/datasets/{dataset}/gazetteers/{gazetteer}`. Copies are matched on `Provenance.gazetteer`, which is the dataset id of the copy's own unit's gazetteer.
  - Only a place that the gazetteer's dataset holds alone is copied.
  - The addition is audited before the page-by-page copy, so a failed copy is never unaudited.
  - **Each read path is red with its fix removed**, live: `get_node`, `get_nodes` (the seed, which is node detail at the route), store search, suggest by name (no identifier sent), and expansion. Each red is at its own call site in `adapter.py`. The working set's second withholding layer is defence in depth, and no read path depends on it (recorded, not counted).
  - A retracted copy stays a copy, its identifiers withheld and kept (red with `provenance.gazetteer` dropped in `writer._replacement_for`).
  - Ruling (d) stands in place of the brief's removal clause.
- **Ruling 8, the unit a build setting:**
  - *Admin › Maps*' Build, both command-line builds, and now **the set-up console's Build** (`harness/geospatial.py`, the Geospatial screen's "Unit that holds the place names") take the unit. A build without a unit is refused in words, and nothing runs.
  - The console's fake runner parses with the Conduit's own `map_admin.command_parser()`, so it refuses what the container refuses (rule 15). It is red against the old fake.
  - `DEMO_GUIDE.md`'s build line and `map_admin.py`'s docstring carry `--unit`.
- **`git`:** the owner ruled for (b): dulwich, under its Apache-2.0 licence, is studio's carry in L1.7, and then `git` leaves the image. Until then `git` stays declared, and every `licence-check` run names it as awaiting that carry and ruling (`tools/licence_check.py`, `spec/00` §7, the Dockerfile's comment).

## Gates at `ce36c3f` (on main `e76cef9`)

- `make -k ci`: **TO FILL**.
- `make test`, on the server through `stack_lease.sh offline`: **TO FILL**.
- **Live**, platform lease on stack d, through `stack_lease.sh remote`, detached:
  - 18:29–20:25 UTC: the read-path plants, then the delta set with `PORT_CONTRACT.diff` applied: `test_route_rights.py`, the whole graph-port conformance suite, both copy files, `test_gazetteer_ids_withheld_live.py` and `test_gazetteer_place_search_live.py`. **372 passed.** The conformance case is green, and red with the guard's copy clause dropped or the suggest projection dropped.
  - 20:26–20:41 UTC: the two image checks and the retract test.
  - Down and released at 20:44.
  - The full live set ran at `957ef5d`: 702 passed. Since then round 3 changed no live read path.

## Left, for the orchestrator

- The Glass control for a gazetteer (P6).
- The case's dataset picker still offers a gazetteer as a composite (a carry to case).
- The image's source offer and NOTICE (a release step; the register now names what the NOTICE carries).
- The admin guide's `--unit` line (a carry to docs).
- A region of 100,000 places copies in over twenty minutes (a background job is the likely next step).
- trivy 0.76.2 is out (the gate pins 0.76.1).

## Requests

- **Apply `PORT_CONTRACT.diff`.** It regenerates `packages/ports/graph.py`'s docstrings and adds `test_suite.py::test_a_gazetteer_copy_matches_a_case_reader_on_its_name_alone`. It applies clean and was proved live (above).
- **Ratify outside the lane's map:**
  - the `PUT`/`DELETE /v1/datasets/{id}/gazetteers/{id}` routes in `app.py`;
  - `packages/schemas/mapconfig.py`;
  - `services/api/map_admin.py`;
  - `generated/CaseGazetteer*.ts`;
  - `OspreyFlow_Core/Makefile`'s `trivy-image-api` line;
  - `apps/harness` (the Geospatial screen and its client);
  - `services/extract/writer.py` is untouched (only planted and restored);
  - and, as before: `packages/ontology/handling.py`, `packages/adapters/graph_arcadedb/builders.py`, `packages/schemas/{domain,merge}.py`, `test_route_rights.py`, `test_investigation_levels.py`, spec 00, 03 and 06, and `placesByRole.json`.
- **Mark ADR-147 Amendment 2 written** in `ADR_RESERVATIONS.md`.

**Questions:** none. **Running:** nothing; no stack held.
