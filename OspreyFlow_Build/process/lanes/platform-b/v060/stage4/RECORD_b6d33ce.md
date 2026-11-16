# v0.6.0 stage 4 · the package test on candidate `b6d33ce` · the record

Run by platform-b on 16 November 2026, 12:56–14:00Z, on R1's kind cluster on the test server (stack b's lease), from a
copy of `b6d33ce` (the Glass candidate: `fb7f336` plus case's notes-scroll fix 436aa04, workspace only; pushed by case
as deputy orchestrator) whose `OspreyFlow_Core` was the candidate's exactly and whose `OspreyFlow_Build` carried the
run's tooling fixes (`lane/platform-b-v060-chart-before-listing`, to merge after the release). Per
`PACKAGE_TEST_SHEET.md`. Every record is on the server in `~/osprey-runs/platform-b.c8/stage4-b6d33ce/` (74 files) and
R1's `records/`; the samples in `memory-samples.b6d33ce.jsonl`. The run on `fb7f336` before it stopped after row 5 on
case's word ([`RECORD_fb7f336.md`](RECORD_fb7f336.md)).

**Before it (stage 3 on b6d33ce): PASS.** VERSION v0.6.0; `changelog_check --tag v0.6.0`; the four guides v0.6.0
(architecture 1.6, developer 1.39, user 1.74, administration 2.24), `test_docs_pdf.py` 18 passed; the publication
check 0 new, the citations clean; the warm release dry run from a hash-checked archive, rc 0 (12:49:23–12:50:33Z):
seven images built with the 2026-11-16 stamp, seven trivy scans clean, the lock refusing only our five, the chart
packaged; the scan tags removed. `make chart-check cp-policy-check` against the run copy: 393 passed.

## The owner's ruling (16 November): this run stands for `529f0f4`

CI 43869826530 on b6d33ce was red on two items: a records slip (`test_lanes_groups`, fixed on main in 6a99cb0) and two
keyboard cases whose harness never loaded the product's faces (fixed test-only in 4fefa51). The next C, `529f0f4`
(529f0f4be623ae929050b743ee7c571a0a98b53b), was compared with b6d33ce by platform-b for the ruling:

- `git diff b6d33ce 529f0f4`: **2 files under `OspreyFlow_Core`**, `apps/workspace/keyboard/case-line-type.spec.ts`
  and `places-harness.tsx`, and **8 under `OspreyFlow_Build/process/`**; nothing else. VERSION, the CHANGELOG, the
  guides and their PDFs, the chart, every Dockerfile, `.dockerignore`, the package manifests and lock, and every
  service, package, harness and command file unchanged: **nothing in a build input** but the one context below.
- The one image whose context takes the folder in is the workspace's builder stage (`COPY apps/workspace`). Its build is
  `vite build` (no tsc); built on the test server from the hash-checked b6d33ce copy, then with 529f0f4's two files in
  place: **the dist byte for byte identical**, 59 files each, every file's sha256 the same, **tree hash
  `afd0a61e71b4ff28`** both times. The image copies only that dist. (`~/osprey-runs/platform-b.c8/dist-compare/`; the
  copy restored and its files sha-checked afterwards.)
- What differs downstream is only the product repository's published tree (release step 6 compares C's
  `OspreyFlow_Core`): it carries the two new test files, as intended.

**The owner accepts stage 4 on b6d33ce for 529f0f4** (through case as deputy and the orchestrator; `v060/RULINGS.md`,
"Stage 4 on b6d33ce stands for 529f0f4"). No rows were run again. CI on 529f0f4 must still be fully green before
"release-ready".

## Known issue, for the release notes

- **report-sync restarts once if the Conduit is unreachable during a pass; it recovers on its own.** (Row 6; case's
  ruling: v0.6.1, low, not a regression: the same code is in v0.5.1. The fix: `services/report_sync/sync.py`'s
  case-list and feed GETs catch `httpx.HTTPError` as a recorded failure, as its token request does, red first with a
  stand-in Conduit refusing connections. It joins v0.6.1's item on the report sync surviving a Valkey error.)

## The rows

| # | Result | What it showed |
| --- | --- | --- |
| 0, 0m | PASS (119 s) | the 32 GiB node; `registry: osprey-r1-registry started (empty)`; the stand-ins; the sampler every 15 s |
| 1 | PASS (363 s) | the cold INSTALL, every block; **step 6's block reads every api pod** (`logs -l app.kubernetes.io/name=api --since=24h --tail=-1 --prefix`) and said "no sign-in refused for its token version so far"; the search rebuild Job Completed; the Glass answers |
| 2 | PASS | R1's 37 checks |
| 3 | PASS | the dashboards check, 41 checks and 2 RECORD lines (as on ea5fc61: a builder reads the whole mart, ADR-148 Amendment 21; the other-unit mirror; OspreyReader live) |
| 4, 4b, 4c | PASS | spec 08 on poc: 14 passed, 15 skipped; its seed-free halves 3 passed; both plants red, as built green |
| 5 | PASS | a set; a change after it gone after the restore; the rebuild (225/225) and the drift check (none) |
| 6 | PASS, one recorded rerun of the verify | INSTALL step 9's seed as written (`seed: done, hmp, fixture-corp, scenarios`; the index 1517/1517); a picture written through the analyst's door and read back; the manifest verify **51 of 51** on its rerun. Attempt 1: 50 of 51, `workloads.report-sync: ready 0 of 1`: its pass fell while step 9 had scaled the api to 0, `httpx.ConnectTimeout` escaped the case-list GET and the process exited (13:16:01Z); restarted, its next pass pulled 1 board with 0 failed, Ready 13:17:20Z; the verify had run 13:16:54–13:17:08Z. The known issue above (`row6-rerun-reason.txt`, `row6-attempt1.log`, `row6-report-sync-*.log`) |
| 7 | PASS | the soak and the sampler's report (below) |
| 8 | PASS | DECOMMISSION with no choice refused in the product's words ("there is no default"); with keep from block 9, every block, "backups: kept" |
| 9 | PASS | `remake` kept the registry and 11 images (`registry: osprey-r1-registry kept, reused`); the warm INSTALL 244 s (cold 363 s); R1's 37 checks |
| 9b | **PASS, both shapes** | (below) |
| 10 | PASS | a set, then DECOMMISSION with destroy: the key's deletion scheduled for 2026-12-16; "backups: destroyed"; "0 thing(s) left behind". The run waited for the minute to turn between the sheet's backup and the DECOMMISSION, so the same-minute name collision (v0.6.1, low; ea5fc61's row 10) was not met; no rerun |
| 11 | PASS | `down`: no cluster, no `osprey-r1-*` container, no `localhost:5001` image, no sampler |

### Row 9b: the token version live, in both shapes (`row9b.sh`, `row9b.log`)

The stand-in at v1.0 and the Conduit restarted; then:

- **Shape 1, the api as R1 renders it (one replica).** A Glass sign-in (the PKCE token as the Glass gets it, `ver
  1.0`) refused on `/v1/me` in Amendment 18's words ("… issues v1.0 access tokens … set requestedAccessTokenVersion to
  2 …"); the pod's log holds one `token version:` line; INSTALL step 6's block printed it with its pod
  (`[pod/api-…/api] token version: …`) and stopped (exit 1).
- **Shape 2, the api scaled to 2 for this row alone**, restarted so neither pod had said anything. `kubectl logs
  deploy/api` read pod `…x8vl6`; the refusal was made on the other, `…qp2m5`, from inside it (the same 401 and
  words): one line on `…qp2m5`, none on `…x8vl6`. **The old one-pod read found nothing** (the defect ea5fc61's row 9b
  found, shown present in this shape); **step 6's block found the line on `…qp2m5` and stopped** (exit 1).
- Then one replica, the stand-in at 2.0, the Conduit restarted: R1's 37 checks pass.

## Memory (row 7; the sampler's report from the soak's mark)

161 samples, 0 gaps; the node's working set peaked at **14.12 GiB** of 32. Each container's peak and steady state
(MiB): ArcadeDB 6431 / 1448 (the peak at 13:17Z, as step 9's seed and its index rebuild ended), OpenSearch 1138 / 1134, NER 645 / 632, ClickHouse 644 /
569, LiteLLM 518 / 492, Superset 421 / 401, PostgreSQL 349 / 291, the Conduit 327 / 295, the worker 222 / 216, Laurium
198 / 188, the report sync 137 / 77. No OOMKill. Restarts: the worker 2, both during the cold INSTALL (13:03:51 and
13:04:36Z, before INSTALL's own rollout wait for it ended; the same on 09f1fbe, ea5fc61 and fb7f336, so
`RECORD_ea5fc61.md`'s "step 9's scaling" for its worker restart is corrected here: it was the INSTALL's start); the
report sync 1 (row 6). Nothing here changes a size (the owner's ruling: item 23 is out of v0.6.0).

## The search index's lag (row 4; ADR-150 Amendment 3)

A record just loaded or a grid just drawn was found 0.1 to 2.2 s later; a read after a redraw settled at 5.6 s. The
same as ea5fc61.

## Reruns, each for a recorded reason

Row 6's manifest verify, once, on case's ruling (above). No other.
