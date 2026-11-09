# Platform lane · P5 · report (9 November 2026, the owner's map rulings 1, 6 and 8)

P5 (ADR-147 Amendment 2). Reviews: the lane's own, then the orchestrator's independent one and its ruling (d)
(a removal deletes no copy), then the lane's own over that round, twice. Every fix is shown red at its call
site in `P5_RED_RECORD.md`; plants that proved nothing are recorded there and not counted. After a pause the
session resumed. It found no `HANDOFF.md` and a clean tree, so there was no `wip` commit to rewrite. It
rebased onto main `3be89a7` (one conflict, both amendments kept), then gated and ran the live set.

- **Ruling 1, Java in the Conduit:** jlinked Temurin 21 pinned by digest (`services/api/Dockerfile`). The
  register's one Classpath exception is in `spec/00` §7. `licence-check`'s image leg proves it in
  `tests/licence_check/test_runtime_licences.py`: a plain GPL-2.0 Java is refused, and so are GPL-3.0 with the
  exception, another exception, the exception for another runtime, and an undeclared Java. Each is red by its
  plant. `tests/test_conduit_image_java_licence.py` covers the image itself. **Image size:** +61 MB, the image
  1.33 GB (arm64). Met, but the image scan is open (below).
- **Ruling 6, copies in the case's dataset:** `services/api/case_gazetteers.py`, through
  `PUT`/`DELETE /v1/datasets/{dataset}/gazetteers/{gazetteer}` (`run_pipelines`). The copies are matched on
  their provenance (`Provenance.gazetteer`), never on a dataset name. Proved live:
  - `test_case_gazetteer_copies_live.py`: no identifier on node detail, expansion or search; never matched by
    `osm_id` or `uprn`; found by name at its point; a SECRET place absent; a re-build refreshes without a
    second set; a case's own write is kept.
  - `test_case_gazetteer_routes_live.py`: the case stays one dataset and still loads; search, seed, expansion
    and suggest hold no identifier.

  Offline, `test_case_gazetteers_routes.py` (18 cases) and `test_map_places_route.py`. Met, with ruling (d) in
  place of the brief's removal clause.
- **Ruling 8, the unit a build setting:** *Admin › Maps*' Build takes a unit, and both command-line builds
  take `--unit` (required). An unknown unit is refused in words before anything runs (`UNKNOWN_UNIT`), and a
  re-build for another unit is refused (`OTHER_UNIT`). The tests are `test_geospatial_admin_routes.py`,
  `test_gazetteer_build_registration_order.py`, `test_gazetteer_dataset_registration.py`,
  `tests/cli/test_map_verb.py` and `Maps.test.tsx`. Met.
- **Gates** at `957ef5d` on main `3be89a7` (`gates/README.md`), with Docker Desktop off on this machine:
  - `make -k ci`: green but its `docker` targets (the image scans, `opentofu-check`, `chart-check`).
  - `make test`: 9498 passed. The known six failed, and every other failure is at the Docker socket.
  - test-js: 2765 + 45 passed. The Matrix timing case failed under load and passed alone.

  **Live:** LIVE_LINE
- **Decisions taken** (in ADR-147 Amendment 2):
  - adding a gazetteer is a dataset-level action, under `run_pipelines`;
  - the gazetteer must be of the dataset's unit, and another unit's is answered as none;
  - copying in pages of 500;
  - a copy the case has made its own is never written over;
  - a removal deletes nothing (the orchestrator's ruling (d));
  - every refresh failure is said without naming a dataset, and never fails a committed build;
  - the place search takes the removal records as a dependency (503);
  - `git` is declared and named as awaiting the owner on every `licence-check` run.
- **Open:**
  - **The api image with Java has not been scanned by trivy at any P5 gate:** Docker Hub's 429 at round 2,
    no daemon here now. It wants one `make trivy-image-api` where Docker runs.
  - `git` under GPL-2.0-only in the image awaits the owner.
  - planetiler itself has not been run in the built image (no release jar; tier 1 only).
  - A region of 100,000 places copies in over twenty minutes (a background job is the likely next step).
- **Left, for the orchestrator:**
  - the Glass control for a gazetteer (P6);
  - the case's dataset picker still offers a gazetteer as a composite (a carry to case);
  - the port's own contract for 3b on a copy (`PORT_CONTRACT.diff`);
  - the image's source offer and NOTICE (a release step);
  - ADR-147 Amendment 2 to be marked written in `ADR_RESERVATIONS.md`.
- **Commits:** `f1c4fe7` (the schemas) to `e624b0b`, rebased onto `3be89a7`: schemas, generated TypeScript,
  ruling 8, ruling 6, ruling 1, the amendment, then each review's fixes, then gates, records and this report.
- **Requests:**
  - apply `PORT_CONTRACT.diff`;
  - ratify `packages/ontology/handling.py`, `packages/adapters/graph_arcadedb/builders.py`,
    `packages/schemas/{domain,merge}.py`, `test_route_rights.py`, `test_investigation_levels.py`, spec 00, 03
    and 06, and `placesByRole.json`;
  - mark Amendment 2 written;
  - run the api image's scan where Docker runs.
- **Questions:** none new. **Running:** nothing; no stack held.
