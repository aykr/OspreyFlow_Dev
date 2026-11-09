# Platform lane · P5 · report (9 November 2026, the owner's map rulings 1, 6 and 8)

P5 (ADR-147 Amendment 2). Reviews:

- the lane's own;
- the orchestrator's independent review and its ruling (d): a removal deletes no copy;
- the lane's own, twice;
- **the orchestrator's review sending P5 back (round 3)**;
- **the lane's own review of round 3**, which sent it back again (defects 1–14), all answered.

Every fix is shown red at its call site in `P5_RED_RECORD.md`. Plants that proved nothing are recorded there and not counted. The session resumed after compaction and found no `HANDOFF.md`. **Head `HEAD_FILL`, rebased onto main `b368f86`.**

## The brief

- **Ruling 1, Java in the Conduit:**
  - jlinked Temurin **21.0.13+9**, October 2026's update, pinned by its index digest (`services/api/Dockerfile`). It was repinned from 21.0.12.1+1, which the new version gate refused.
  - The register's one Classpath exception is in `spec/00` §7, proved by `licence-check`'s image leg (`test_runtime_licences.py`, each refusal red).
  - Built on the test server (amd64): the **image is 1.86 GB** (1,858,898,417 bytes), of which **`/opt/java` is 62 MB**. planetiler v0.10.2's `--help` **exits 0** under the image's Java.
  - **trivy does not see a jlinked runtime.** The same image from Temurin 21.0.1 (2023, with known CVEs) scans clean, exit 0, as the current one does. trivy names no package of the runtime.
  - In its place, **`tools/java_runtime_check.py`**: the Dockerfile's `org.ospreyflow.runtime.java.version` label must match the image's `/opt/java/release` `JAVA_VERSION` and its `java -version` build, and must be Temurin 21's newest (Adoptium's API).
    - Anything it cannot read is a refusal in words.
    - Over the old image it is red both ways; over the repinned image, green.
    - Every branch is red offline, through `main` and the fetch's own code.
    - **Policy:** CI goes red when Adoptium publishes a newer Temurin 21, until the image is repinned.
    - It runs in Build's `make ci` after `core-check`, through **`JAVA_RUNTIME_CI.diff`**. Core's Makefile stands alone (ADR-114 Amendment 2), so the first draft's line there was withdrawn, after `test_core_stands_alone` went red on it.
  - `java.desktop`'s ten bundled native libraries are registered for the NOTICE (`spec/00` §7), from the image's own notices.
- **Ruling 6, copies in the case's dataset** (`services/api/case_gazetteers.py`, `PUT`/`DELETE /v1/datasets/{dataset}/gazetteers/{gazetteer}`):
  - Copies are matched on `Provenance.gazetteer`, the dataset id of the copy's own unit's gazetteer.
  - Only a place the gazetteer's dataset holds alone is copied.
  - The addition is audited before the copy. *Admin › Audit* files both actions under *Datasets*, as main's census requires; only the dataset's id is shown.
  - **Every read path withholds a copy's identifiers:**
    - five are red live with their fix removed: `get_node`, `get_nodes` (the seed, node detail at the route), search, suggest by name, and expansion;
    - every deserialiser call in the adapter is held structurally to their own caller's principal (`test_every_read_withholds_by_its_principal.py`), red at each of the ten remaining call sites in turn.
  - A retracted copy stays a copy, withheld, with its identifiers kept.
  - Ruling (d) stands in place of the brief's removal clause.
- **Ruling 8, the unit a build setting:**
  - *Admin › Maps*, both command-line builds and **the set-up console** (its Geospatial screen's "Unit that holds the place names") take the unit.
  - The console takes any unit the Conduit can name (`org_unit`'s 1 to 60 characters), and refuses only none, an option or a control character. A null counts as none.
  - Its fake runner refuses with the Conduit's own parser, and refuses an unknown unit in the Conduit's own words (`UNKNOWN_UNIT`), which the screen shows.
- **`git`:** the owner ruled for (b): dulwich, under Apache-2.0, as studio's carry in L1.7, and then `git` leaves the image. Until then every `licence-check` run names it as **not yet passed**, with that ruling and carry (asserted). This is in the ADR, `spec/00` §7 and the Dockerfile.

## Gates (`gates/README.md`, round 3)

- **`make -k ci`** at `1c1d2aa`: **green but this machine's Docker socket** (the eight image scans, `opentofu-check` and `chart-check`; Docker Desktop is off here). The harness axe run passed, the Geospatial screen included. `b9d5aeb` after it changes only the audit census lines.
- **`make test`**, on the server through `stack_lease.sh offline`, at `b9d5aeb`: **9762 passed, 2 failed, none the branch's** (the server's GPU preflight case and the Valkey offline pin). test-js: workspace 2814 passed, 1 failed (the Matrix first-frame timing under load; alone, it passes); harness 47 passed.
- **Live**, platform lease on stack d through `stack_lease.sh remote`, detached:
  - the read-path plants;
  - the delta set with `PORT_CONTRACT.diff` applied: `test_route_rights.py`, the whole graph-port conformance suite, both copy files, and the gazetteer identifier and place-search files. **372 passed.**
  - the image checks and the retract test.
  - Released at 20:44 UTC.
  - Since then the read paths are unchanged. The fixes after the live runs are offline: the version gate, the console's unit, the audit census and the structural read test.

## Left, for the orchestrator

- The Glass control for a gazetteer (P6).
- The case's dataset picker still offers a gazetteer as a composite (a carry to case).
- The image's source offer and NOTICE (a release step; the register names what it carries).
- The admin guide's `--unit` line (a carry to docs).
- A region of 100,000 places copies in over twenty minutes (a background job is the likely next step).
- `MAP_PATH` is defined in both `harness/geospatial.py` and `cli/ospreyflow/maps.py`. Neither imports the other, so it is left as it is.
- trivy 0.76.2 is out (the gates pin 0.76.1).

## Requests

- **Apply at merge:**
  - `JAVA_RUNTIME_CI.diff`: Build's `java-runtime-check` target, in `ci` after `core-check`. It needs Docker and the network, as the image scans do.
  - `PORT_CONTRACT.diff`: `ports/graph.py`'s docstrings and the conformance case `test_a_gazetteer_copy_matches_a_case_reader_on_its_name_alone`. It applies clean and was proved live.
- **Ratify outside the lane's map:**
  - `services/api/app.py`'s `PUT`/`DELETE` gazetteer routes;
  - `packages/schemas/mapconfig.py` and `generated/CaseGazetteer*.ts`;
  - `services/api/map_admin.py`;
  - `services/api/Dockerfile`;
  - `services/api/audit_section.py` and `test_audit_kinds.py` (admin's census: the two actions, words shown);
  - `harness/geospatial.py`, `harness/webapp.py` and `apps/harness` (the Geospatial screen, its client and test);
  - `OspreyFlow_Core/DEMO_GUIDE.md`;
  - `tools/licence_check.py` and the new `tools/java_runtime_check.py`;
  - and, as before: `packages/ontology/handling.py`, `packages/adapters/graph_arcadedb/builders.py`, `packages/schemas/{domain,merge}.py`, `test_route_rights.py`, `test_investigation_levels.py`, spec 00, 03 and 06, and `placesByRole.json`.
- **Mark ADR-147 Amendment 2 written** in `ADR_RESERVATIONS.md`.

**Questions:** none. **Running:** nothing; no stack held.
