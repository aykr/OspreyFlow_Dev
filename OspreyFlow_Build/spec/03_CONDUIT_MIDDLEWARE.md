# 03 — The Conduit (Middleware)

## 1. What the Conduit is and is not

It is a stateless orchestration layer: FastAPI on Python 3.12, uvicorn workers, async
throughout. It translates analyst intent into port calls, enforces access control, and manages
the working set.

It is **not** a place where data lives. Any Conduit instance can serve any request for any
session; kill one mid-investigation and the analyst notices nothing. Session and working-set
state live in Valkey; durable state lives in the Vault. This is the property that lets the
Conduit scale horizontally to a large concurrent user base independently of the Vault, which is
the whole point of the tier.

It is also **not** a pass-through to Gremlin. The Conduit owns query construction. An analyst
never submits a traversal and the Glass never contains one. That is both an access-control
boundary (a hand-written traversal cannot be filtered reliably) and the reason a future move
from Gremlin to SQL/PGQ is an adapter change.

## 2. Service decomposition

One deployable API process plus three worker pools. Workers share the codebase and the ports;
they differ in what queue they consume.

| Service | Scales on | Consumes |
| --- | --- | --- |
| `api` | Concurrent analysts | HTTP / WebSocket |
| `worker-ingest` | Data volume | `ingest` queue |
| `worker-extract` | Unstructured volume, GPU availability | `extract` queue |
| `worker-compute` | Working-set size and metric complexity | `compute` queue |

Queue is Valkey Streams in `local-lite`, NATS JetStream (Apache-2.0) in `cluster`. Both behind
a `QueuePort` so the swap is a config value. Job state, progress and failure are first-class:
every job is addressable, has a progress stream, and reports partial results where partial
results are meaningful.

## 3. API surface

REST for request/response, Server-Sent Events for job progress, WebSocket for working-set
deltas. Not GraphQL: the response shapes here are few and large, the clients are one, and the
cost of a flexible query layer on top of an access-filtered graph is not worth paying.

### 3.0 Liveness

```
GET    /healthz                                is this process up
GET    /v1/readiness                           whether the deployment's models are present (signed in; ADR-095 Amendment 2)
```

**Owner's decision, 24 September 2026.** One unauthenticated route, outside `/v1` because it is
not part of the API surface a client uses — it exists so an orchestrator can tell a started process
from a healthy one. `docker compose up --wait` has nothing to wait on without it, which is what
made the scripted deploy unable to reach its own exit criterion.

**Its body is fixed and says nothing else.** `{"status":"ok"}`, byte for byte, always. No version,
no build, no uptime, no component status, no counts. The reasoning is this document's own §6: an
unauthenticated endpoint that reports which stores are reachable tells an unauthenticated caller
about the deployment's internal topology, and one that reports counts is a count leak with a
friendly name. **It touches no store**, so it stays true when every store is down, which is exactly
when an orchestrator most needs to distinguish "the process is up but its dependencies are not"
from "the process is gone".

**Readiness stays authenticated and is a separate question.** "Can this process serve a request"
and "is this deployment ready to be used" are different, and only the second needs to talk to the
stores it depends on — which is why only the second can be allowed to describe them.

**The test that holds this, per the standing access-control rule:** the anonymous response and the
authenticated response are compared byte for byte and must be identical. A liveness route that
quietly said more to an authenticated caller would be a route with two behaviours, and the
unauthenticated one is the one an attacker gets.

### 3.1 Investigations

```
POST   /v1/investigations                      create
GET    /v1/investigations/{id}                 metadata, not the working set
POST   /v1/investigations/{id}/branch          fork the working set (or a chosen set of its nodes) into a new investigation
PUT    /v1/investigations/{id}/tab             open or close this case's tab, for the caller only
GET    /v1/investigations/{id}/history         addressable step history
POST   /v1/investigations/{id}/history/{step}  restore to a step
```

**Authorization.** Every route above an investigation id checks the calling
`Principal.org_unit` against that investigation's own `owning_unit` — set once at creation (or
branch) from the acting principal's own unit, the same shape as `Handling.owning_unit`
(`01_DOMAIN_MODEL.md` §2.2), not a new concept. This is deliberately *not* `clearance`-gated: a
shared, unit-wide investigation with analysts at different clearances is the ordinary case, not
an edge case, and clearance still gates individual node/edge visibility separately (§4's read-time
handling filter). A principal in the wrong unit gets the same 404 an unknown investigation id
would — never a 403 — extending the existence-leak discipline `00_ARCHITECTURE.md` §5 already
requires at node/edge level up to the investigation id itself.

**Access by level (ADR-052).** The unit check above stays. On top of
it a principal must hold a level on the case: their own grant (Viewer, Editor or Author) or the
case's unit-wide level, whichever is higher. Each route declares the level it needs
(`_authorized_at` in `services/api/app.py`), and `tests/services/api/test_investigation_levels.py`
holds the table below and fails any route that is missing from it or declares a different level. No
level at all is the same 404 as an unknown case; a level that is too low is a 403. A grant never
widens what the unit, clearance and handling rules allow. Cases have a name; the creator is the first
Author; a new case is visible to nobody else until shared; cases that existed before were migrated once
(creator Author, unit Viewer).

| Level | Routes under `/v1/investigations/{id}` |
|---|---|
| Viewer | `GET` the case; `access` (GET: the caller's own level); `tab` (PUT: the caller's own flag, ADR-084); `datasets` (GET, ADR-099); `search`, `suggest`, `paths` (POST, ADR-099); `explore/counts`, `explore/most-connected`, `explore/busiest-links`, `explore/busiest-days`, `explore/groups`, `explore/whats-new`, `explore/starter-questions`, `nodes/{node}/shared-contacts` (GET, ADR-100); `expand/preview`; `patterns/preview`, `patterns/run` (POST), `patterns`, `patterns/{pattern}` (GET); `compute/{metric}`; `resolution/threshold` (GET); `resolution/explain/{cluster}`; `hotlists`, `monitors`, `alerts`, `alerts/{alert}` (GET, ADR-099 Amendment 3); `rules`, `alert-queue`, `alert-queue/{alert}`, `ownership/{node}`, `kyc/{node}` (GET, ADR-109); `questions` (GET, ADR-098); `ingest/candidates` (GET); `dossier/documents/{doc}`; `documents/{doc}/reader`, `documents/{doc}/file` (GET); `history` (GET); `judgements`, `gaps`, `assumptions` (GET); `links/{edge}/notes`, `links/{edge}/history`, `links/{edge}/events` (GET); `link-types` (GET, ADR-090); `sites/{site}` and its `image` (GET); the Ingest Studio's reads (`ingest/source-files`, `ingest/recipes`, `ingest/recipes/{recipe}`, its `profile`, `map/sample-rows/{row}` and `map/handling-preview`, `ingest/recipe-registry`; ADR-099 Amendment 4); the delta stream |
| Editor | `branch`; `seed`; `expand`; `nodes` (DELETE); `nodes/{node}/confirm`, `retract`, `suppression-mark` (POST, DELETE; ADR-099 Amendment 1); `links-among` (ADR-098); `explore/starter-questions/{question}/run`, `nodes/{node}/shared-contacts/{other}/canvas` (ADR-100); `resolution/threshold` (PUT), `link`, `split`; `patterns/save`; `hotlists`, `monitors` (POST), `alerts/{alert}/jump`; `held-rows` (GET, ADR-109); `alert-queue/{alert}/claim`, `release`, `disposition`, `canvas`, `ownership/{node}/canvas` (ADR-109); `questions` (POST) and `questions/candidates/{candidate}/accept`, `reject` (ADR-098); `documents` (POST), `documents/{doc}/extract`, `designations`, and its candidate `accept`, `reject`; `ingest/extract`, its candidate `accept` and `reject`; `links/{edge}/events/documents`, `links/{edge}/events/{event}/extract` and its candidate `accept`, `reject`; `history/{step}` (restore); `judgements`, `gaps`, `assumptions` (POST); `links/{edge}/notes` (POST), `links/{edge}/notes/{note}` (PUT, DELETE), `links/{edge}/change` (POST); `link-types` (POST), `link-types/{proposal}/withdraw` (the proposer or an Author, ADR-090); `export`; `sites` (POST), `control-points`, `grid`; the Ingest Studio's writes (`ingest/source-files` (POST), `ingest/recipes` (POST), `ingest/recipes/{recipe}` (PATCH), its `versions`, `row-template`, `verify`, `publish`, `schedule` and `run`) |
| Author | `PATCH` the case (rename); `DELETE` the case (a soft remove: it then reads as not found to everyone, nothing is deleted, ADR-052 Amendment 7; the unit's `osprey-admin` may too, through the same safety net); `datasets` (PUT: what the case reads, ADR-099 decision 3); `access` (PUT: the unit-wide level, which is none, Viewer or Editor, never Author); `access/grants/{account}` (PUT, DELETE); `access/history`; `rules` (POST), `rules/{rule}/retire`, `rules/audit` (GET; the admin's safety net reaches this one too), `held-rows/reject`, `ingest/recipes/{recipe}/held-rows/release` (ADR-109). An `osprey-admin` in the case's own unit may also use these without holding a level (the safety net, audited as `access_admin_override`); that gives no other access. |

`GET /v1/investigations` lists the cases the caller holds a level on (id, name, their level, created,
created by, branched from, whether the caller has closed the case's tab, and the names of the
datasets it reads). `POST /v1/investigations` takes `dataset_ids`, at least one of the caller's unit;
with none it makes a dataset of the case's own, named after it (ADR-099 decision 3). A branch reads its
parent's datasets. `POST .../branch` takes an optional body (ADR-084): `node_ids` forks only those nodes and the links whose two ends are both
among them, `name` names the new case. Without a body it forks the whole working set, as before. The
copy is filtered for the branching principal like any read, and a choice with nothing left to copy
(every id absent, hidden from the caller, or the list empty) is one `422 nothing_to_branch`, raised
before any case is created and the same whatever the reason (rules 3 and 4). `GET .../access` shows anyone their own level, and shows an Author the
unit-wide level and every grant. A grantee is named by the account name the identity provider knows
them by; a mistyped name grants nothing to anyone (ADR-052 P3).

`POST /v1/investigations` needs no grant. The Glass's case picker and the demo seeds' grants
(`scripts/case_seed.py`) are built; a Share panel in the Glass is not, so a grant is made through the
routes above. The listing has no counts yet; they need the working set read under the caller's handling filter.

### 3.2 Working set

```
WS     /v1/investigations/{id}/stream          bidirectional delta channel
POST   /v1/ws-ticket                           short-lived single-use ticket for the stream above
POST   /v1/investigations/{id}/seed            seed from a search result or saved subgraph
POST   /v1/investigations/{id}/expand          apply an expansion
POST   /v1/investigations/{id}/expand/preview  cardinality only, no mutation
DELETE /v1/investigations/{id}/nodes           remove from the working set (not from the Vault)
```

**`/v1/ws-ticket`, ADR-050 objection 8.** A browser's native `WebSocket` cannot set an
`Authorization` header, so the stream above is opened with `?ticket=<value>` rather than a bearer
token in the URL. This route is the only way to obtain one: authenticated the ordinary way, it
mints a random, single-use value — bound to the calling principal, redeemable exactly once, and
expiring in 30 seconds — and returns it. A bearer token placed in the stream's own URL instead of a
ticket is refused outright, not merely accepted as a fallback. The ticket binds the identity only:
the stream scopes it to its case's datasets when it is redeemed (ADR-099 Amendment 7), as every
case route's principal is, and everything it sends is projected for that reader.

The delta protocol, client-bound:

```json
{"seq": 412, "op": "add",     "nodes": [...], "edges": [...]}
{"seq": 413, "op": "update",  "nodes": [{"id": "...", "properties": {...}}]}
{"seq": 414, "op": "remove",  "node_ids": ["..."]}
{"seq": 415, "op": "reproject", "reason": "resolution_threshold",
 "merged": 3, "split": 1, "affected": 47}
{"seq": 416, "op": "notice",  "level": "warning",
 "message": "6 nodes withheld by handling policy", "count": 6}
{"seq": 417, "op": "snapshot", "nodes": [...], "edges": [...], "filtered_count": 6}
{"seq": 418, "op": "replace_edge", "old_edge_id": "...", "edge": {...}}
```

`replace_edge` (ADR-080) is sent when an analyst changes a link: the client takes the old link out and
puts the new one in at the same step, so no screen shows both or neither.

Sequence numbers are monotonic per investigation. A client that misses a sequence reconnects and
requests a full snapshot rather than attempting to patch — silent divergence between the
server's picture and the analyst's is the failure this protocol exists to prevent. `snapshot` is
that full-state response: the five ops above are this section's own illustrative set, and a
full-snapshot reconnect path is required even though no shape was given for it in that
illustrative set — the same way `GraphPort` grew past its own illustrative sketch
(`00_ARCHITECTURE.md` §2.1). Its `filtered_count` is the same figure `expand`'s response and the
status bar both carry, computed fresh for whichever principal is reconnecting (§4).

The `notice` operation is how withheld items reach the status bar. It carries a count and never
carries the withheld content, not even its identifiers.

Withheld means withheld from this reader by handling, and nothing else. A link whose end has left
the working set (removing a node leaves its links in the store) is left out of every read and not
counted. A delta replayed or pushed alone carries only its own nodes, so its links' ends are judged
against the working set as it stands: a link to a node already on the canvas is sent, and one to a
node this reader may not see is withheld and counted (9 October 2026; `test_hidden_count.py`).

### 3.3 Query and analytics

```
POST   /v1/investigations/{id}/search      federated search across graph, documents, index, within the case's datasets (ADR-099)
GET    /v1/datasets                     the datasets of the caller's unit, for a new case to name (ADR-099)
POST   /v1/datasets                     a new, empty dataset of the caller's unit (`{"name": ...}`), audited (ADR-099); `POST /v1/investigations` takes `dataset_ids`, and with none makes the case a dataset of its own named after it
POST   /v1/investigations/{id}/suggest     type-ahead: nodes whose identifiers start with what is typed (ADR-059), within the case's datasets (ADR-099)
GET    /v1/investigations/{id}/explore/counts          nodes per entity type and links per link type the analyst can see, within the case's datasets (ADR-100)
GET    /v1/investigations/{id}/explore/most-connected  nodes by visible degree, most first, with the total ranked; ?entity_type, ?limit (1-50), ?offset (ADR-100)
GET    /v1/investigations/{id}/explore/busiest-links   links by the records each stands for, most first, each with both ends; ?edge_type, ?limit, ?offset (ADR-100)
GET    /v1/investigations/{id}/explore/busiest-days    the case's days by events, most first, from its daily histogram; ?limit, ?offset (ADR-100)
GET    /v1/investigations/{id}/explore/groups          the case's largest groups and the nodes bridging them, from its link structure; over the working set's caps, limit_exceeded (ADR-100)
GET    /v1/investigations/{id}/explore/whats-new       the latest loads into the case's datasets, and the nodes colleagues confirmed or marked for suppression there, each named only where the reader sees it (ADR-100)
GET    /v1/investigations/{id}/explore/starter-questions    query-builder chains that suit the types the case's datasets hold, as the reader sees them (ADR-100)
POST   /v1/investigations/{id}/explore/starter-questions/{question}/run    an offered question's matches and the links among them onto the canvas; counted first, too_many_matches at the query builder's limit (ADR-100)
GET    /v1/investigations/{id}/nodes/{node}/shared-contacts    who shares (`edge_type` required) at least two of this node's contacts by the link type, most first, counted as the reader (ADR-100)
POST   /v1/investigations/{id}/nodes/{node}/shared-contacts/{other}/canvas    the two (`edge_type` required), their shared contacts and the links among them onto the canvas, all or limit_exceeded, Editor (ADR-100)
POST   /v1/investigations/{id}/paths       k-shortest paths between two entities, within the case's datasets (ADR-099)
POST   /v1/investigations/{id}/patterns/preview   cardinality estimate for a visual query, within the case's datasets (ADR-099)
POST   /v1/investigations/{id}/patterns/run   execute; large results return a job id, which keeps the case's datasets (ADR-099)
POST   /v1/investigations/{id}/patterns/save   persist the calling principal's own pattern, in the case's first dataset (a version bump if it exists, in its own dataset), Editor (ADR-099 Amendment 3)
GET    /v1/investigations/{id}/patterns   the calling principal's own saved patterns of the case's datasets (and any saved before ADR-099 Amendment 3, until placed), Viewer
GET    /v1/investigations/{id}/patterns/{pattern_id}   load one of them (?version= for an older one); another dataset's is 404, as a missing one, Viewer
POST   /v1/analytics/histogram          cross-filter histogram set
POST   /v1/analytics/cross-filter       the same cross-filter, one histogram per requested dimension
POST   /v1/analytics/first-seen         when each node and link first appears in the window, for the timeline's playback (ADR-087)
GET    /v1/investigations/{investigation_id}/links/{edge_id}/events   the events behind one link (the emails between two addresses), newest first, paged, Viewer (ADR-089)
POST   /v1/investigations/{investigation_id}/links/{edge_id}/events/documents   the emails on the link inside a window written as Documents and put on the canvas, or limit_exceeded, or not_documents (422) when no event carries text, Editor (ADR-092)
GET    /v1/investigations/{investigation_id}/documents/{document_id}/reader   a Document's full text with its accepted entities marked, for the full-screen reader, Viewer (ADR-092)
POST   /v1/investigations/{investigation_id}/documents   a file (image, video, text) added to the case as a Document, held by a node if one is named, with a marking and a legal basis, Editor (ADR-094)
GET    /v1/investigations/{investigation_id}/documents/{document_id}/file   a held Document's file (image, video, kept text) from the media store, Viewer (ADR-094)
PUT    /v1/investigations/{investigation_id}/nodes/{node_id}/picture        one entity's own picture, an image Document that DEPICTS it, replacing the one seen before (kept); marking and legal basis required, Editor (ADR-105)
DELETE /v1/investigations/{investigation_id}/nodes/{node_id}/picture        back to its type's picture; its own is kept, no longer shown, Editor (ADR-105)
GET    /v1/investigations/{investigation_id}/nodes/{node_id}/picture        the entity's picture's file, to someone who may see it; one they may not answers as none, Viewer (ADR-105)
POST   /v1/investigations/{investigation_id}/pictures                       which of these entities have a picture of their own the caller may see, Viewer (ADR-105)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/extract   entities from a held Document by kind: text, an image described and read, a video transcribed; `using`: `recogniser` (the default, ADR-098) or `model`, Editor (ADR-094)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/candidates/{candidate_id}/accept   accept one finding from a held Document as an inferred node, Editor (ADR-094)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/designations   words in a Document marked as an entity by the analyst: an asserted node linked to it, Editor (ADR-098)
POST   /v1/investigations/{investigation_id}/links-among   the links among nodes already in the view (all, or the named ones), all or `limit_exceeded`, Editor (ADR-098)
GET    /v1/investigations/{investigation_id}/datasets   the datasets the case reads, in order, Viewer (ADR-099)
PUT    /v1/investigations/{investigation_id}/datasets   what the case reads (`{"dataset_ids": [...]}`, at least one, all of the Author's unit; else 422 `dataset_refused`, one answer for another unit's and a missing one), audited before and after, Author (ADR-099)
POST   /v1/investigations/{investigation_id}/questions   a question to the model about every Document in the case's view the analyst can see, whole; the answer cites them and its proposals are pending findings; past 80,000 characters refused `documents_too_large` (413), none `no_documents` (422), Editor (ADR-098 decision 4)
GET    /v1/investigations/{investigation_id}/questions   the case's questions and answers: citations of Documents the reader can see, proposals of their unit in their present state, Viewer (ADR-098 decision 4)
POST   /v1/investigations/{investigation_id}/questions/candidates/{candidate_id}/accept   one proposal accepted: an inferred node and its `MENTIONED_IN` link onto the canvas, Editor (ADR-098 decision 4)
POST   /v1/investigations/{investigation_id}/questions/candidates/{candidate_id}/reject   one proposal rejected; nothing is written, Editor (ADR-098 decision 4)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/candidates/{candidate_id}/reject   reject one finding from a held Document; nothing is written, Editor (6 October 2026)
POST   /v1/investigations/{investigation_id}/links/{edge_id}/events/{event_id}/extract   entities from one email, pending for a person to accept; `using`: `recogniser` (the default, ADR-098) or `model`, Editor (ADR-089)
POST   /v1/investigations/{investigation_id}/links/{edge_id}/events/{event_id}/candidates/{candidate_id}/accept   accept one of an email's findings as an inferred node, Editor (ADR-089)
POST   /v1/investigations/{investigation_id}/links/{edge_id}/events/{event_id}/candidates/{candidate_id}/reject   reject one of an email's findings; nothing is written, Editor (6 October 2026)
POST   /v1/analytics/geobins            server-side spatial binning
POST   /v1/analytics/sightings          the "snail trail" — device/location sightings over time (B18)
POST   /v1/analytics/geometries         batched geometry lookup — a Location's geometry_ref resolved to WGS84, one round trip for a whole working set
POST   /v1/investigations/{id}/compute/{metric}   submit a metric job over that investigation's own working set
GET    /v1/jobs/{id}/events             SSE progress stream
```

**The analytics reads are case reads (ADR-084 Amendment 2).** `histogram`, `cross-filter`,
`first-seen`, `geobins` and `sightings` carry their case in the body (`EventFilter.investigation_scope`)
and take the same gate as every case route, at Viewer: a case the account holds no level on answers
404 and reads nothing, and the refusal is audited. On a branch, the Conduit widens the read to the
events of each case it came from that the account can see, **on the links the branch holds only**
(`EventFilter.inherited`), and the same rule holds for the events behind one link and an email
extracted from one. `inherited` is always set by the Conduit; a value sent by a caller is discarded.
`geometries` is reference data, not case data, and is unchanged.

**Saved patterns are private to the principal who saved them.** `GET /v1/investigations/{id}/patterns` lists only
the calling principal's own — `PatternStore.list_authorized` filters by owner in the query itself, not
after fetching everything, and `GET /v1/investigations/{id}/patterns/{pattern_id}` applies the same authorization to a single
load. Since ADR-099 Amendment 3 a saved pattern belongs to the dataset of the case it was saved in
and is found only in a case reading that dataset, the dataset clause in the same query. `POST /v1/investigations/{id}/patterns/save` raises the identical
`PatternNotFoundError` (404) when `pattern_id` names a pattern the caller does not own — the same
existence-leak collapse every other route in this surface uses, enforced inside the save itself
rather than a separate ownership check beforehand.

**`POST .../compute/{metric}` is nested under an investigation** — a metric job runs over one
investigation's own working set, never a principal-wide one, so the investigation id is part of
the path, not a body field. Submits a `ComputePort` job (Tier 1 in-process for `local-lite`, a
queued worker for `cluster`) and returns immediately with a job id; `GET /v1/jobs/{id}/events`
streams its progress.

### 3.4 Ingest, extraction, assessment

```
POST   /v1/ingest/upload                multipart; returns a document id and a job id
POST   /v1/ingest/connector/{name}/run  trigger a configured connector
GET    /v1/handling-scheme              the active deployment's classification/handling-code vocabulary
GET    /v1/yardstick                    the active deployment's probability yardstick (01_DOMAIN_MODEL.md §5)
GET    /v1/documents/{id}               metadata, provenance, extraction results
GET    /v1/documents/{id}/content       original bytes, access-checked, audited
POST   /v1/documents/{id}/reextract     re-run with a different model version

POST   /v1/investigations/{id}/judgements
GET    /v1/investigations/{id}/judgements   list visible judgements — ADR-046's own hide-in-full rule applies
POST   /v1/investigations/{id}/gaps
GET    /v1/investigations/{id}/gaps         list
POST   /v1/investigations/{id}/assumptions
GET    /v1/investigations/{id}/assumptions  list
GET    /v1/investigations/{id}/links/{edge}/notes   notes on one link, newest first — 404 `link_not_found` unless the link is in the working set and the caller may see it (ADR-075)
POST   /v1/investigations/{id}/links/{edge}/notes   add a note (`{"body": "..."}`), 201; 422 `invalid_note` for empty or over 4,000 characters
PUT    /v1/investigations/{id}/links/{edge}/notes/{note}      change the caller's own note; 403 `note_not_yours` for anyone else's
DELETE /v1/investigations/{id}/links/{edge}/notes/{note}      remove the caller's own note, 204; 403 `note_not_yours` for anyone else's
POST   /v1/investigations/{id}/links/{edge}/change   change a link's type and/or details (`{"reason": "...", "type"?, "properties"?, "interval"?, "occurrences"?}`) by superseding it; 200 with the new link, the `replace_edge` step and the change record; 404 `link_not_found` as for notes; 422 `invalid_link_change` (no reason, over 1,000 characters, or the ontology refuses), `nothing_changed`, `resolution_link` for a same-as or not-the-same link, either way round (ADR-080); `handling`? and `confirm_lower`? (ADR-102): a raise is an Editor's, a lower handling in any part is an Author's with `confirm_lower`, else 403 `lowering_needs_author` or 409 `confirm_lower_handling`; a handling that moves the units, is above the analyst's own, or names a code the scheme lacks is 422 `invalid_link_change`
GET    /v1/investigations/{investigation_id}/link-types   the relationship types a link in the case may take: the ontology's (the OspreyFlow default dataset's), and those analysts proposed in a case reading one of this case's datasets (`proposal_id` set; a proposal made before ADR-099 Amendment 3 keeps ADR-090's case, branch and in-view rule), Viewer (ADR-090, ADR-099 Amendment 3)
POST   /v1/investigations/{investigation_id}/link-types   propose a type when none fits (`{"name", "from_types", "to_types", "directed"?, "label"?, "colour"?, "thickness"?, "reason"}`): usable at once in every case reading this case's first dataset, probabilistic (ADR-099 Amendment 3); 422 `proposal_refused` for a name the ontology has or the case already offers, or one that is not a type name, Editor (ADR-090)
POST   /v1/investigations/{investigation_id}/link-types/{proposal_id}/withdraw   withdraw a pending proposal of a dataset the case reads (`{"reason"}`), its proposer or an Author; 404 `proposal_not_found`, Editor (ADR-090)
GET    /v1/investigations/{id}/links/{edge}/history  every earlier version of one link and the changes between them, newest first, at most 100 steps (`truncated` says so) — 404 `link_not_found` unless the caller may see the link (ADR-080)
POST   /v1/investigations/{id}/export    runs the handling gate; may return 409 with blockers
GET    /v1/exports                       the compliance-facing export ledger (ADR-047's own Gap 2) — role-gated, not per-investigation
GET    /v1/investigations/{id}/ingest/candidates   extraction candidates for one document (?document_id=)
```

**The block above illustrates an earlier, abandoned ingest design — `09_INGEST_STUDIO.md`'s own
recipe-based routes, below, are what the Ingest Studio actually calls.** Neither block is pruned:
the illustrative one predates the Studio and matches no route this app registers under that shape,
but removing it would trade a wrong row for a blank one rather than a correct one, so it stays as a
disclosed historical illustration alongside the real surface.

```
GET    /v1/ingest/connectors                               the connector catalogue (09_INGEST_STUDIO.md §2)
POST   /v1/investigations/{id}/ingest/recipes                                   Connect: create a draft
GET    /v1/investigations/{id}/ingest/recipes                                   Connect: the author's own unit's drafts
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}                        load one draft
PATCH  /v1/investigations/{id}/ingest/recipes/{recipe_id}                        Connect: edit a draft still in progress
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}/profile                Profile: run and read the automatic source profile
GET    /v1/ingest/transforms                                 Map: the Knowledge Adapter catalogue
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}/map/sample-rows/{row_index}   Map: page through a real row bound to the template
PUT    /v1/investigations/{id}/ingest/recipes/{recipe_id}/row-template            Map: save the row template
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/map/handling-preview    Map: preview an element's handling/provenance override
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/verify                  Verify: the dry run — no write of any kind
GET    /v1/investigations/{id}/ingest/recipe-registry                             Publish: every recipe the principal's own unit owns, any status
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/publish                 Publish: draft → published; the sign-off itself
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/versions                Publish: reopen a published recipe as a new draft version
PATCH  /v1/investigations/{id}/ingest/recipes/{recipe_id}/schedule                Publish: change a published recipe's schedule
(ADR-099 Amendment 3: every route above is the case's, a recipe the dataset's of the case it was made in, found, listed, verified, published and run only in a case reading it; reads at Viewer, changes at Editor, each on top of its Studio role. The connector and transform catalogues stay global: they describe the system, not data.)
```

**Connect (`POST`/`GET`/`PATCH .../recipes`) is `SOURCE_AUTHOR`-gated**, the studio role that also
gates listing source files (`GET /v1/investigations/{id}/ingest/source-files`) and uploading one (`POST` to the same path,
ADR-067; under the case since ADR-099 Amendment 4) — creating or editing a draft and
picking a source to point it at are the same action, one step apart. `GET .../recipes/{id}`
rejects (409, via `RecipeNotADraftError`'s own sibling checks elsewhere in this family) once a
recipe has left `draft` status for the edit route, but stays readable regardless of status.

**Profile and Map read the source under the requesting principal's own clearance**, the same
shape-masking §3.6's `explain`/dossier reads already apply: `GET .../profile` calls the
profiler and `GET .../map/sample-rows/{row_index}` reads the identical bounded sample, both masked
identically so a principal who can't see the source's own marking never sees more of it through
one route than the other. `GET /v1/ingest/transforms` and `GET /v1/ingest/connectors` are
deployment metadata (the Knowledge Adapter registry, the connector catalogue) — authenticated but
not investigation-scoped and not audited, the same category `GET /v1/ontology` already is.

**Map's own two writes are gated on the draft already having a profile.** `PUT .../row-template`
(the template save) and `POST .../map/handling-preview` (what an in-progress element's handling
would resolve to) both reject with `RecipeNotReadyForProfileError` until `GET .../profile` has
actually run — an override needs a baseline handling to tighten against, and an incomplete draft
has none. `PUT .../row-template` also checks every element's own handling override actually
tightens, never loosens, the source-level marking Connect set (`validate_handling_tightens`) — the
same independent-minimums rule Profile's own masking already enforces, checked here before the
template is persisted rather than only at read time. `POST .../map/handling-preview` calls the
identical resolver Verify's own dry run calls, so Map and Verify never disagree about what an
override produces.

**Verify is the dry run: no Parquet staging, no graph write, no transaction.** An `on_match:
reference` element's lookup against the existing graph still goes through the ordinary,
principal-scoped `GraphPort.find_node` — an access-filtered miss reads as "would create" exactly
like a genuine miss would, so a dry run cannot be used to discover that a higher-classification
match exists. The lookup reads with the case's principal, so a value already held only by another
dataset is not found and a new node is made for it in this one: one address loaded into two
datasets by two loads is two nodes, joined only by resolution, unless the loads write the same node
id (ADR-099 Amendment 1 decision 5). A completed run, rejections included, marks the recipe verified; publishing checks
that flag rather than re-running the dry run itself.

**Publish, its schedule, and reopening a version are all `SOURCE_APPROVER`-gated**, a distinct
role from `SOURCE_AUTHOR` — the source-approver's sign-off *is* the publish action, not a separate
step, and reopening a published recipe for a new mapping (`POST .../versions`) needs the identical
sign-off since publishing the new version *is* the approval; there is no separate "approve a
changed mapping" action. `GET /v1/investigations/{id}/ingest/recipe-registry` is Publish's own
listing, every status the principal's own unit owns, not only drafts, of the case's datasets (and
those made before ADR-099 Amendment 3, which name none, Amendment 5) — a distinct path from
`GET /v1/investigations/{id}/ingest/recipes`
rather than a query parameter, since the latter already registers `{recipe_id}` in the same
position and a literal suffix there would collide with it. `POST .../publish` writes the recipe's
own YAML and commits it before flipping the registry row to `published` — a published row never
exists without a matching commit, the safer order given the repository is the record. `PATCH
.../schedule` re-commits the same YAML with a new schedule without bumping the version — the
mapping itself is unchanged, only when it runs.

**Unstructured extraction and its review queue — `09_INGEST_STUDIO.md` §7's own mechanism, nested
under an investigation for audit-context consistency with `run_studio_recipe` above, the identical
reasoning:**

```
POST   /v1/investigations/{id}/ingest/extract                          run extraction over a document's text
POST   /v1/investigations/{id}/ingest/candidates/{candidate_id}/accept accept one candidate into the graph
POST   /v1/investigations/{id}/ingest/candidates/{candidate_id}/reject reject one candidate
```

The path's case scopes what the principal reads to its datasets, and an accepted candidate's minted
node is written into the case's first dataset (ADR-099 decision 6, Amendment 1 decisions 1 and 2),
so `investigation_id` is no longer audit attribution only. `POST .../extract` calls the configured extraction model against
the given text under the requesting principal's own handling marking and returns the raw
candidates for review (`GET .../ingest/candidates`, above, lists them back). Accept and reject are
both single-candidate, no bulk operation of either kind exists — `09_INGEST_STUDIO.md` §7's own
"no bulk accept" is structural here, not a checked rule: the route takes exactly one
`candidate_id`, never a list. Accepting mints the node (optionally with `properties_override`);
rejecting discards the candidate with no node ever created, and neither ever produces a dossier
span (§3.6) until a candidate has actually been accepted.

### 3.5 Resolution

```
GET    /v1/resolution/threshold          current session τ
PUT    /v1/resolution/threshold          set τ; triggers a reproject delta
POST   /v1/resolution/link               analyst-asserted SAME_AS
POST   /v1/resolution/split              analyst-asserted NOT_SAME_AS
GET    /v1/resolution/explain/{cluster}  the comparison vector and score that produced a cluster
```

**Nested under an investigation, not the bare top-level paths above** — the same shape
`resolution.py`'s own docstring already discloses for `/v1/resolution/link`: every route in this
section is actually nested, since a session threshold and a resolution decision are both scoped to
one investigation's own working set, not global to the principal:

```
GET    /v1/investigations/{id}/resolution/threshold          the same ThresholdResponse PUT sets
PUT    /v1/investigations/{id}/resolution/threshold          set τ; triggers a reproject delta
POST   /v1/investigations/{id}/resolution/link               analyst-asserted SAME_AS (optional `reason`, kept as the audit justification — ADR-080)
POST   /v1/investigations/{id}/resolution/split               analyst-asserted NOT_SAME_AS (optional `reason`, as above)
GET    /v1/investigations/{id}/resolution/explain/{cluster}  the read described just above
```

`explain` is required, not a nicety. An analyst who cannot see why two records were treated as
one person will either trust the merge blindly or distrust the whole system. Return the
per-comparison match weights, not just the total.

**A manual link, unlike a split, can grow a saved pattern's or hotlist's own match set** — `POST
.../link` evaluates every watch this principal's hotlists/monitors/saved patterns declare, the
identical evaluation `run_studio_recipe` (§3.4) already performs on an ingest, since a `SAME_AS`
write and an ingested row are both, from a watch's own point of view, new evidence to check. A watch
is evaluated only against data of its own dataset (ADR-099 Amendment 3).
`POST .../split` never evaluates anything — a `NOT_SAME_AS` write can only shrink a match set, and
a watch has nothing to newly fire on.

**The corpus-wide resolution trigger is a separate route, deliberately not investigation-scoped:**

```
POST   /v1/resolution/{entity_type}/run   re-run resolution for one entity type across the whole corpus
```

`ADR-025`'s own mechanism for a resolution comparison config that changed, or a backlog that never
ran — this acts on every entity of the given type regardless of which investigation's working set
it happens to appear in, since the resolution `SAME_AS` edges it writes are corpus-wide facts, not
investigation-scoped ones (§4 already collapses them per-session at read time, at whatever
threshold that session has set). It compares across the corpus, but each `SAME_AS` it writes carries
only the datasets its two records share: a match across two datasets is in none, and no case reads
it (ADR-099 Amendment 2 decision 3). Returns immediately with an accepted job id; the run itself is
the same post-ingest resolution job `run_studio_recipe` (§3.4) also submits per resolvable entity
type.

### 3.6 Dossier

```
GET    /v1/investigations/{id}/dossier/documents/{document_id}   a message, with its entity spans
```

(B6) The Dossier's own read, backing `apps/workspace/src/dossier/` — "the
shared endpoint's messages... rendered with the entity spans highlighted in place." A document's
raw text (persisted once, at extraction time, keyed by `document_id` and scoped to the extracting
principal's own `owning_unit` — the same `WHERE owning_unit = $2` shape `get_authorized` already
uses for a candidate, so an unauthorised principal gets the same 404 whether the document never
existed or simply isn't theirs) plus the subset of its **accepted** extraction candidates whose
minted node the requesting principal can currently see:

```json
{
  "document_id": "doc-412",
  "text": "Dana called +441621926368 about the shipment.",
  "spans": [
    {"start": 0, "end": 4, "node_id": "n1", "entity_type": "Person", "provenance_state": "asserted"}
  ]
}
```

A span naming a node the principal cannot see is **omitted from the array entirely, never
returned redacted** — the same rule §3.5's `explain` response already follows for a pairwise
comparison naming an invisible node (`visiblePairs`). A redacted span would still assert "an
entity was extracted here," which is exactly the existence signal access control exists to deny;
omission is the only response shape that doesn't. A **pending** (not yet accepted) or **rejected**
candidate never produces a span at all — that is the still-separate, still-unbuilt review-queue
screen's own concern (`09_INGEST_STUDIO.md` §7), not post-hoc inspection of an already-resolved
message, and a pending candidate has no minted node and no `Handling` to check visibility against
in the first place.

### 3.7 Geospatial admin actions

```
POST   /v1/admin/geospatial/build-basemap   tier-1 pipeline: download, planetiler, gazetteer load — streamed
POST   /v1/admin/geospatial/verify          attribution and, for a tier-4 provider, a live CRS/zoom probe
```

The two Geospatial-screen actions are structurally unreachable from inside the setup harness image
— disclosed in `harness/geospatial.py`'s own docstring — since `build_local_basemap` needs a live
`GraphPort` transaction, and both it and `verify_map` import `services`/`adapters` modules the
harness image deliberately does not carry. Admin-role-gated (`require_admin_role`,
`osprey-admin`) — the one process that already has every module both actions need. `build-basemap` streams its own real
progress the same way Launch does (`text/event-stream`, one `{"line": ...}` per step, `event:
complete` last); `verify` is fast enough to answer as a plain JSON `{"passed": ..., "issues": [...]}`.
Not yet called from any UI — the post-launch console has no screen built yet.

### 3.8 Hotlists, monitors, alerts

```
POST   /v1/investigations/{id}/hotlists   create, in the case's first dataset; identifier plus a review date; fires only on that dataset's data, Editor (ADR-099 Amendment 3)
GET    /v1/investigations/{id}/hotlists   the calling principal's own hotlists of the case's datasets, Viewer
POST   /v1/investigations/{id}/monitors   create a standing query the evaluator watches, in its saved pattern's dataset and matched only within it, Editor
GET    /v1/investigations/{id}/monitors   the calling principal's own monitors of the case's datasets, Viewer
GET    /v1/investigations/{id}/alerts     the calling principal's own alerts of the case's datasets, Viewer
GET    /v1/investigations/{id}/alerts/{alert_id}   one alert, expanded to its jumpable referents, Viewer
POST   /v1/investigations/{id}/alerts/{alert_id}/jump   a new case seeded from the alert, reading the alert's dataset, Editor
```

**Owner-only, and of a dataset** — a hotlist or a monitor is a standing watch that outlives any one
investigation, and an alert belongs to the principal who owns the watch that fired it, not to
whichever investigation happens to be open when it does. Each belongs to a dataset (a hotlist to
the first of the case it was made in, a monitor to its saved pattern's; ADR-099 Amendments 3 and 4)
and is listed only in cases reading that dataset. A match in another dataset writes nothing, not
even a `notify` stub, and an alert's entities are read as its case reads them. `POST .../jump` branches a fresh
investigation from `Investigation.branched_from`, seeded with the alert's own referent nodes — the
identical branching mechanism §3.1's `POST /v1/investigations/{id}/branch` already uses, not a
second implementation of it. `Alert.investigation_id` (the triggering event's own investigation,
where the underlying ingest or resolution that raised the alert happened) may be absent — a
resolution-triggered alert carries no single investigation — and the jump still succeeds, simply
unlinked (`Investigation.branched_from` is `None` rather than pointed at a wrong investigation). The
case a jump makes reads the alert's dataset, else what the alert's case reads, else a dataset of its
own (Amendment 4 decision 3).

### 3.8a Typology rules, their audit, held rows (ADR-109 phase A)

```
GET    /v1/investigations/{id}/rules   the case's typology rules, retired ones included, Viewer
POST   /v1/investigations/{id}/rules   deploy one: a typology, its parameters, its trigger point and budget, Author
POST   /v1/investigations/{id}/rules/{rule_id}/retire   retire one (never deleted), Author
GET    /v1/investigations/{id}/rules/audit   the rule audit, newest first, paged, Author or the unit's admin
GET    /v1/investigations/{id}/held-rows   rows a failing pre-commit rule held, at or below the reader's marking, Editor
POST   /v1/investigations/{id}/held-rows/reject   reject named held rows, with a reason, Author
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/held-rows/release   load named held rows of one load, Author and Loader
```

**A rule belongs to its case** and evaluates as its deployer's principal, resolved fresh (ADR-036);
its parameters are a closed vocabulary per typology (structuring, rapid movement, circular flow —
rule 8), refused at the schema otherwise. **Where it runs is the rule's** (ADR-109 ruling 1): a
`pre_commit` rule judges a run's incoming money movements inside the load's graph transaction — a
hit is written there as an `Alert` node with `ALERTED_ON` links, and its queue row follows the
commit; a rule that errors or overruns `budget_ms` holds the rows it could not judge (§5.1). A
`post_commit` rule runs once the load's events are in the analytics store, best-effort. Both read
flows from the analytics store's `TRANSACTED` events (one per transaction; the graph merges a pair's
transactions into one link), with the access step in the query; a rule never fires on an event its
deployer cannot read, and one transaction loaded twice is read once. A finding alerts once (its
signature, per rule, in Valkey).

**An alert a rule raised** is a §3.8 alert row carrying `typology`, `words`, `edge_ids`,
`event_ids`, `window`, `trigger` and `alert_node_id`, plus the `Alert` node, marked no lower than
anything it references; where referents with a restricted code belong to different units no single
marking is safe, the node is withheld and the withholding audited. They are also the deployer's
§3.8 alerts, and the case team's queue below.

**The audit read** returns entries of `rule_deployed`, `rule_retired`, `rule_evaluated`,
`rule_fired`, `rule_failed`, `rows_held`, `rows_released`, `rows_rejected` and
`alert_node_withheld`. An entry naming a node the reader cannot see is withheld whole, before
paging, so the total never counts it.

**The case team's queue (phase B, ruling 3).**

```
GET    /v1/investigations/{id}/alert-queue   the case's rule-raised alerts; ?status= active (default), open, claimed, closed or all, Viewer
GET    /v1/investigations/{id}/alert-queue/{alert_id}   what fired it: nodes, cited links and ALERTED_ON, each transaction, Viewer
POST   /v1/investigations/{id}/alert-queue/{alert_id}/claim   open → claimed by the caller, Editor
POST   /v1/investigations/{id}/alert-queue/{alert_id}/release   claimed (by the caller) → open, Editor
POST   /v1/investigations/{id}/alert-queue/{alert_id}/disposition   → closed, true or false positive with a reason, Editor
POST   /v1/investigations/{id}/alert-queue/{alert_id}/canvas   its node, entities and cited links into the working set, Editor
```

Every member of the case reads every rule-raised alert of it, whoever deployed the rule; an alert
any of whose entities, cited links or transactions the reader cannot read is left out of the list
and its count, and opening or acting on it answers 404 (ADR-039's all-or-nothing). The summary names
entities as the reader sees them, never by id. A move between statuses is one conditional update,
so two members acting at once cannot both win: the loser gets 409 `alert_moved_on`. A true positive
confirms the `Alert` node (asserted, `confirmed_by` the member, rule 5); a false positive leaves it
`inferred`. The canvas route seeds all or, past the cap, nothing (`limit_exceeded`, rule 2).

**Held rows** are read in the store's query by marking (the adapters' two axes) and case; a
decision names rows by id and decides all or none (an id not held, or not readable, refuses the
whole decision as not found). A release loads the rows under a new load id with their original row
numbers, judged again by the case's rules, but a failure no longer holds them: the release is the
human judgement. A recipe published again since the rows were held is refused in words.

### 3.8b Ultimate beneficial ownership (ADR-109 phase C)

```
GET    /v1/investigations/{id}/ownership/{node_id}   who ultimately owns or controls it; ?threshold= (default 25), Viewer
POST   /v1/investigations/{id}/ownership/{node_id}/canvas   its ownership structure into the working set, Editor
```

The structure is read upward from the entity over `BENEFICIAL_OWNER_OF` and `CONTROLS`, one layer
at a time, as the reader (`GraphPort.expand`, access in the traversal): a party or link the reader
cannot see is absent, and the trace is what it would be without it. `ComputePort.ownership` does the
maths (`01_DOMAIN_MODEL.md` §10). The answer (`OwnershipView`) is the trace and the parties and links
it was computed over. Too deep (a chain of more than ten links) or too large (more than 500
parties) is 409 `ownership_too_complex` with the reason — never a part-trace (rule 2). An entity the
reader cannot see is 404. A trace is a view: nothing it concludes is written (ruling 9).

**Drawn patterns as rules (phase D, the no-code typology builder).** A `pattern` rule names a
pattern the deploying Author drew and saved in the query builder (§3.3; deploying another's is 422).
At each evaluation the saved pattern is read again as the deployer (an edited one is evaluated as it
now reads; one no longer theirs stops the rule, audited — ADR-036's discipline), counted and matched
through `GraphPort` as the deployer. It runs after commit only — it is matched against the stored
graph — and a pre-commit `pattern` rule is refused at the schema. The alert cites the whole match
(the pattern language returns one union of what matches, ADR-030); one alert per distinct match (its
signature is the matched nodes and links); more than `max_matches` nodes is refused in words.

### 3.8c KYC: the onboarding gate, status and screening lists (ADR-109 phase F)

```
GET    /v1/investigations/{id}/kyc/{node_id}   a customer's KYC status and baseline risk, computed now, Viewer
```

**The gate is rules** (ruling 6): three more typologies in §3.8a's closed vocabulary, judged over
the customers a load *creates*, at the trigger point each rule declares. `kyc_screening`: each new
person or organisation's name, and — for an organisation — each natural person who ultimately owns
at least `owner_threshold`% of it or controls it (§3.8b's ownership maths over the load's own
ownership links and the stored structure above them), screened against the screening lists; a hit
writes the listed party and a scored, `inferred` `SAME_AS` with the alert. `shared_attributes`: a
new customer's phone, email, IP address or handle already used by `min_others` other customers.
`document_verification`: a new customer with no valid verifying document. A pre-commit KYC rule
judges the load's writes as the engine wrote them (the open transaction cannot be read back), each
filtered by its deployer's access; one that fails holds the rows that created the customers it
could not judge. "Halting onboarding" is the alert, raised with the load (OspreyFlow activates no
accounts).

**The daily sweep** (ruling 7). Each load records the expiry of every verifying document it writes
(`kyc_expiries`); once a day one replica (a Valkey claim per day) re-checks the documents that
lapsed since the last sweep, as each case's `document_verification` rule's deployer, and raises a
review alert where no valid document remains — the deployment's first periodic pass.

**Screening lists** are deployment-wide reference data in `screening_entries`, outside the graph —
only a matched entry enters a case. `python -m scripts.load_screening_list <file>` loads one,
replacing a list of the same name whole; a list not marked synthetic needs the owner's local
real-data exceptions entry (rule 9; spec 00 §7 for OpenSanctions' terms). Names are compared with
the resolution engine's own Jaro-Winkler, over sorted tokens; a disagreeing date of birth rules a
match out.

**The status route** reads, as the reader, the customer's verifying documents, its listed `SAME_AS`
neighbours, its beneficial owners' (for an organisation), its shared contact details, its country
and industry, and returns the status and the weighted factors. Not a customer (anything but a
person or an organisation): 422 `kyc_not_applicable`; unseen: 404. Nothing it computes is stored.

### 3.9 Sites

```
POST   /v1/investigations/{id}/sites                          create; multipart, a label plus the image itself
GET    /v1/investigations/{id}/sites/{site_id}                one site's own metadata
GET    /v1/investigations/{id}/sites/{site_id}/image           the site's uploaded image, proxied
PATCH  /v1/investigations/{id}/sites/{site_id}/control-points  set the georeferencing control points
POST   /v1/investigations/{id}/sites/{site_id}/grid            place the grid; its cells become real location entities
```

A **site** is A1's own mechanism (`08_ACCEPTANCE_SCENARIOS.md`): an uploaded floor plan or
diagram, georeferenced by a set of control points, whose grid cells become real location entities
once placed. `POST .../sites` is the first multipart upload in the Conduit — the image's own
dimensions and format are read from the bytes themselves, never trusted from the browser-supplied
content-type header, and an unsupported format is refused (422) before anything is stored. The
image itself is never handed to the browser as a direct object-store URL — `GET .../image` proxies
it, the same reasoning as the tile proxy (§3.7's neighbour in spirit, `00_ARCHITECTURE.md` §1.2):
credentials stay server-side and every read is a request this process can see, not a signed URL
handed to whoever asks. Setting control points is a distinct step from creating the site or placing
its grid — a site can exist, image and all, before it is georeferenced. `POST .../grid` runs the
site-grid connector and the ordinary recipe engine synchronously against the placed grid, loading
one geometry per cell; redrawing the grid is idempotent (`on_match: reference` in the connector's
own recipe) rather than creating duplicate location entities.

### 3.10 Ontology and map

```
GET    /v1/ontology                              entity/edge type names, channels, shapes, identifiers
GET    /v1/admin/link-types                      the proposed relationship types of the administrator's own unit, newest first, `osprey-admin` (ADR-090)
POST   /v1/admin/link-types/{proposal_id}/promote   into the ontology for every case (`{"basis", "reason", "rename_to"?}`): Direct only from now on; merged into a promoted type of its name whose links it fits, or 422 `proposal_refused` (rename it); another unit's is 404 `proposal_not_found`, `osprey-admin` (ADR-090)
POST   /v1/admin/link-types/{proposal_id}/reject    no longer offered; its links stay and keep its name (`{"reason"}`), `osprey-admin` (ADR-090)
POST   /v1/admin/link-types/retire                  a promoted type of the unit no longer offered anywhere (`{"name", "reason"}`); its links stay, `osprey-admin` (ADR-090)
GET    /v1/map/providers                        the deployment's declared map providers, for the layer control
GET    /v1/map/tiles/{provider_id}/{z}/{x}/{y}   the tile proxy for a tier-3/4 provider
GET    /v1/map/local-source/{provider_id}        a tier-1/2 provider's local PMTiles file, over HTTP
```

**`GET /v1/ontology`** is what the Glass's channel/shape mapping (`02_GLASS_FRONTEND.md` §4: "Hue
is entity type; shape is entity type too") reads, rather than a hardcoded copy of `packages/
ontology/default.yaml` in the frontend — the ontology already carries `EntityTypeDef.channel`/
`.shape` per type, and duplicating that mapping client-side would drift the moment a deployment's
ontology changes.

**It is the ontology in force, not `default.yaml` alone** (ADR-090): the types analysts proposed and
an administrator promoted are in it, with the `overlay_revision` that rose at each promotion and
retirement, while `version` is still the authored one. A pending proposal is not: it is offered only
by `.../link-types` in the cases it belongs to. The label each proposal's links are stored under
(`<name>__<proposal id>`) and the aliases that make those labels read as a name are the Vault's
business, and this route strips both, as a source-system identifier is kept from the Glass (rule 7).
Every proposal and decision is audited (`link_type_propose`, `_withdraw`, `_promote`, `_reject`,
`_retire`) with its reason.

**The map routes are a real spec silence, not an oversight in this table alone** — `02_
GLASS_FRONTEND.md` requires the layer control this section documents but never named the endpoint
it reads from; recorded as a proposal there, not settled spec. All four routes above are
deployment-wide configuration/infrastructure metadata: authenticated so an unauthenticated
caller learns nothing about this deployment's providers or credentials, but not investigation-
scoped and not audited. `GET .../tiles/...` resolves a `credential: env:VAR` reference server-side
and caches the fetched tile to object storage per the provider's own TTL, so the browser never
holds a tier-3/4 credential or talks to a hosted provider directly. `GET .../local-source/{id}`
exists because a browser cannot fetch a `file://` URI at all — it rewrites a tier-1/2 provider's
local source to this route instead, answers ranged `Range` requests itself (the `pmtiles` protocol
handler reads its directory and tile blocks via ranged fetches against this one file), and 404s
with a named `detail` when the file has not been built, which `apps/workspace/src/map/
basemapAvailability.ts`'s own preflight check depends on to show "basemap not built" rather than a
blank map.

### 3.11 Node provenance actions

```
POST   /v1/investigations/{id}/nodes/{node_id}/confirm   inferred/unresolved → asserted, human-attested; Editor, within the case's datasets (ADR-099)
POST   /v1/investigations/{id}/nodes/{node_id}/retract   asserted → inferred, the mirror of confirm; Editor (ADR-099)
POST   /v1/investigations/{id}/nodes/{node_id}/suppression-mark   propose a suppression (R7 step one); `DELETE` withdraws it; Editor (ADR-099 moved both under the case)
DELETE /v1/investigations/{id}/nodes/{node_id}/suppression-mark   withdraw that proposal; Editor (ADR-099)
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/run   run a published recipe against a file
```

`confirm`/`retract` supersede the node (`GraphPort.supersede_node` — a fresh id, never the original,
since the superseded revision's own index entry is still present) rather than editing it in place;
each is valid from exactly one starting state (`confirm` from `inferred`/`unresolved`; `retract`
only from `asserted`) and raises rather than silently succeeding against the wrong one — a caller
attempting either most likely holds a stale view of the node. Confirming clears the superseded
`extraction_confidence` rather than leaving a stale model-reported figure sitting on a now
human-attested fact; retracting does not attempt to reconstruct the original figure, it reverts
honestly to `inferred` with no confidence value. Both flag any judgement that cites the superseded
node as supporting evidence, within the same session — `08_ACCEPTANCE_SCENARIOS.md`'s own
"retraction propagates" assertion, generalised to every supersede either route performs.

`POST .../ingest/recipes/{recipe_id}/run` is Loader-gated (`StudioRole.LOADER`) — §8's "Loader: run
a published recipe against a file at or below their own clearance." `source_location`, when given
in the request, is that file; omitted, it repeats against the recipe's own recorded location, and
the recipe's own deduplication key makes a re-run idempotent (§6: "re-runnable"). A load that
actually creates something submits a post-ingest resolution job per resolvable entity type the
recipe declares — the only route through which an ingest can raise a hotlist or saved-pattern
alert against a live deployment, not fixture data assembled by a test harness.

## 4. The Working-Set Service

The most important component in the Conduit.

**Storage.** One Valkey hash per investigation holding the node and edge set in a compact binary
encoding, plus a capped stream of deltas for reconnect. TTL of 24 hours on idle, with explicit
save promoting the set to durable storage in the Vault.

**Caps.** 50,000 nodes, 250,000 edges. On breach the service does not truncate; it returns a
`limit_exceeded` response naming the three options the Glass offers the analyst (branch, filter,
promote to batch). Encode this as a typed error, not a generic 400, so the client can render the
right dialogue.

**Projection.** The stored set is source-fidelity. The projection applied on read is: resolution
collapse at the session's τ, the access check for the principal (handling and the case's datasets),
then delta computation against
what the client last acknowledged. Projection is pure and cheap; it runs per request. Resolution
collapse is implemented with Splink; the handling filter and delta computation are implemented
too.

**Why the stored set can hold more than one principal's own view, and why the filter must
therefore run on every read, not once at write time.** An investigation is not single-principal
for its whole life — §3.1's `owning_unit` authorization is unit-wide, not creator-only, so a
shared team investigation, or one principal's branch of another's, means a later reader's own
`Principal` may be different, and less privileged, than whoever's `expand`/`seed` call originally
populated a given node. `GraphPort`'s own access filtering at the point of fetch is still the only
thing that ever decides what gets *written* to the store — nothing re-derives or second-guesses
that. What the access check re-applies on every read (`ontology.handling.principal_may_read`: handling,
`principal_may_view`, and the case's datasets, `in_case_datasets`, ADR-099 Amendment 1 decision 3 —
the same predicates the adapter's compiled Gremlin is built from) is a *second*, independent check
for whoever is *reading* the store back: a node one principal was entitled to fetch is not
disclosed to a different principal who is not. This applies uniformly to the reconnect snapshot,
replayed missed deltas, a live WebSocket push, and a `branch` copy — you cannot fork what you
cannot see, either. The stream's principal comes from a ticket minted outside any case, so the
stream scopes it to its own case before the first read.

**Why server-side rather than browser-only.** Three reasons that each independently decide it.
An investigation must survive a tab crash. A branch operation must be atomic. And the resolution
threshold must re-project against the full source-fidelity set, which the browser does not hold
— the browser holds the projection.

## 5. Pipelines

### 5.1 Ingest

```
upload/connector → identify → stage(raw) → normalise → deduplicate → stage(normalised)
                                                     → extract? → resolve → load → index
```

- **identify** — MIME sniffing, not extension trust. Container formats unpacked one level.
- **normalise** — the Knowledge Adapters from `01_DOMAIN_MODEL.md` §7. Originals retained.
- **deduplicate** — content hash per record type; the CDR rule is specified in the domain model.
- **stage(raw)** — the source rows land in Parquet *before* any transform touches them, every
  field as it appeared, typed as text. Immutable, never rewritten.
- **stage(normalised)** — the post-transform rows land in a second Parquet dataset, partitioned
  the same way and carrying the raw row's identifier.
- **judge (ADR-109 ruling 1)** — between load and commit, the case's `pre_commit` typology rules
  (§3.8a) judge the run's money movements in the open transaction. A hit loads with its `Alert`
  node; a rule that errors or overruns its budget fails closed: the transaction is rolled back, the
  rows it could not judge go to the `held_rows` quarantine with their original row numbers, and the
  load runs again without them. The run report says how many were held and why (`rows_held`,
  `rule_notes`) — never a silent part-load. After the commit, once the events are in the analytics
  store, the `post_commit` rules run, best-effort.

**Two staging datasets, not one, and the order matters.** Staging exists so that re-extraction,
re-resolution and schema migration are possible without re-uploading — and only the raw dataset
delivers that. If normalisation runs before the only stage step, a normaliser bug found in month
six is correctable only for fields the recipe happened to bind twice, and an ontology version
that wants a property the original recipe never captured has nowhere to read it from. Both cases
end in a re-upload, which is the outcome staging is meant to prevent.

Raw staging is cheap — text columns, compressed — and it is the layer that makes every other
recovery path work. Skipping it is the most expensive shortcut available in this design.
- **extract** — only for unstructured material; see §5.2.
- **resolve** — Splink, writing `SAME_AS` edges; see §5.3.
- **load** — batched writes through `GraphPort` and `AnalyticsPort` in one logical transaction
  per document.

  > **Spec and code disagreed here, and ADR-058 (accepted in its Amendment 1) settles which way.** The engine writes one element per
  > `GraphPort` call today (`services/ingest/engine.py`), not batches. Proposed: a publish aggregates its resolved
  > elements and writes them through the bulk-load capability by default, falling back to `upsert_*` only for elements
  > that collide with what is already stored. One transaction per document stays unachievable at 10^5 elements; a failed
  > bulk load is reverted and re-run (ADR-058 D6).
- **index** — full text and embeddings into OpenSearch.

**Geospatial reference data uses the same pipeline with two differences.** Gazetteers, boundary
files and OSM extracts enter through `services/ingest/connectors/geo/` (GeoPackage, Shapefile,
GeoJSON, CSV-with-coordinates, OSM PBF, and WFS). They skip extraction entirely, since they are
already structured, and they load into a **reference partition** that is versioned as a whole
rather than per-document — a gazetteer refresh replaces a version, it does not merge into the
previous one, and investigations record which gazetteer version was in force.

Geometry is stored once, not twice: the geometry column lives in the analytics store where
spatial predicates are cheap, and the graph holds the `Location` node with a `geometry_ref`
pointing at that row — never `lon`, `lat` or a source easting and northing as node properties.
A `Location` with no single point, such as a jurisdiction or an administrative boundary, can carry
a polygon-shaped `geometry_ref` instead of a point one (`schemas/analytics.py`'s `GeometryRecord.
kind`) — or none at all, so coordinates can never be a required property on the type.
Putting geometry in the graph store would make spatial filtering a traversal, which is the wrong
shape of query and constrains engine choice for no gain.

The **geocoder is a local service** over that reference partition. An address or place name
extracted from a document resolves against the ingested gazetteer inside the deployment. No
hosted geocoder is called, ever: an air-gapped deployment could not, and sending intelligence
material to one would breach the handling model regardless of connectivity. A gazetteer match is
written as `inferred` with its match score, confirmable by an analyst like any other derived
link.

### 5.2 Extraction

Four modalities behind one `ModelPort`, each the deployment's own model chosen from a pinned list
(`osprey.yaml` `models.*`, ADR-095), plus a fast recogniser in front of the text path:

| Input | Model class | Default local | Output |
| --- | --- | --- | --- |
| Text, first pass | Named-entity recogniser (`RecognisePort`) | Stanza 1.10.1, in the `ner` sidecar (ADR-098) | People, organisations, places (GPE, LOC, FAC), and email addresses and phone numbers by pattern as `Endpoint`s; no score; dates and money are not proposed |
| Text, on request | Instruction-tuned LLM | `models.extraction`: `qwen2.5:7b-instruct` (or the 14b) via Ollama, 32,768-token context | Typed nodes and edges, each with a confidence |
| Audio and video | ASR | `models.transcription`: `Systran/faster-whisper-tiny.en` | Transcript with word timings; a video's audio, time as the locator, frames not analysed (ADR-094) |
| Image | Vision-language | `models.vision`: `moondream:1.8b-v2-q4_K_M` | Description and OCR, the image region as the locator (ADR-094) |
| Document | Layout + text | Text path after layout parse | As text, plus table structure |

*Extract entities* and the extraction routes run the recogniser by default and the model pass only
when asked (`using: model`, ADR-098 Amendment 1 decision 4). Text longer than one extraction window
is read in overlapping windows and the findings joined, so nothing past a window is dropped unread
(ADR-095 decision 2). Embeddings use `models.embedding` (`all-minilm:22m-l6-v2-fp16`).

**Structured output is enforced, not requested.** The extraction call passes a JSON Schema
generated from the active ontology and uses constrained decoding — vLLM guided decoding on the
cluster profile, Ollama's format parameter locally. A model that cannot be constrained is not a
supported extraction model. Parsing free text for JSON and hoping is the single largest source
of silent data corruption in pipelines of this kind.

Each extracted element carries the model identifier and version, the character span or timestamp
it came from, and the model's reported confidence (none for a recogniser finding, which reads *found
by Stanza*). All of it is `inferred` until confirmed.

**The golden set is a build artefact.** `tests/golden/` holds documents with hand-labelled
expected extractions. Changing a prompt or a model runs the set and reports precision and recall
per entity type against the previous version. A change that degrades recall on any type fails
the build unless explicitly accepted with a recorded reason. This is the evaluation harness the
Gemini specification asks for, and it needs to exist from the first extraction commit, not
later — retrofitting a golden set means hand-labelling against a corpus you have already come to
believe in.

**Extraction never writes directly to the graph.** It writes candidates to the staging layer.
Resolution and load are separate stages so that a bad extraction run is revertible.

### 5.3 Resolution

Splink, running on DuckDB locally and Spark on the cluster, configured from the ontology's
per-type `resolution` block. Output is `SAME_AS` edges with the match probability, the model
version and the full comparison vector. Nothing is merged in storage — see
`01_DOMAIN_MODEL.md` §4 for why this overrides the Gemini specification.

Deterministic identifiers bypass the probabilistic path. Two endpoints with the same normalised
E.164 are the same endpoint; do not spend a Fellegi–Sunter model on it.

Analyst decisions are permanent and beat the model: a `NOT_SAME_AS` edge is never overridden by
a later resolution run, and a later run that would have merged the pair records the conflict for
review rather than acting on it.

## 6. Access control and audit

**Principal resolution.** OIDC via Keycloak (Apache-2.0). The session token resolves to a
`Principal` carrying identity, unit, roles, clearance, and the handling codes the principal may
receive, and, for a request whose path names a case, that case's datasets (none otherwise, so it
reads nothing). `get_principal` adds them; every principal a route is given comes through it
(ADR-099 decision 5, Amendment 1 decision 1).

**Enforcement at the port.** The `Principal` is a required argument on every read path in
`GraphPort` and `AnalyticsPort`. Adapters inject the filter into the traversal or the `WHERE`
clause. Filtering in the Conduit after retrieval is forbidden — it leaks existence through
counts and timing, and it is the mistake this rule exists to prevent.

**Existence, not just content.** The conformance suite asserts that an unauthorised principal
cannot detect a filtered node's existence: not through a path length, not through a degree
count, not through a histogram bucket. Aggregate endpoints apply the filter before aggregation.

**Audit.** Append-only, to a stream the Conduit cannot rewrite. Every read, expansion, path
query, pattern run, document view and export records principal, timestamp, the resolved query,
result cardinality, and — where the action crosses a handling boundary — the justification the
analyst supplied. Audit write failure fails the request; an unaudited read in this domain is
worse than a refused one.

**Export gate.** `POST /export` evaluates every node and edge in the selection against the
handling scheme. A `consult_originator` item blocks the export and is named specifically.
Override requires a justification and an originator reference, both recorded. Exports carry the
Osprey mark, the investigation reference, the export timestamp, the resolution threshold in
force, and a manifest of withheld items by count. A disclosed limit (ADR-099 Amendment 1 decision 6):
export of a link checks the link's handling as the client submitted it, not its datasets.

## 7. Caching

Three layers, three different invalidation stories. Keep them separate or you will invalidate
the wrong one.

| Layer | Store | Key | Invalidation |
| --- | --- | --- | --- |
| Working set | Valkey hash | `ws:{investigation_id}` | Explicit, on mutation |
| Query result | Valkey string | hash of (query, principal_class, τ) | TTL 300s + on graph write to touched types |
| Analytics result | Valkey string | hash of (query, principal_class) | TTL 900s + on partition load |

`principal_class` rather than `principal_id`: cache by what the principal may read — clearance, unit,
the handling codes it may receive and the case's datasets (ADR-099; `tests/services/api/
test_cache_access_class.py`) — not by the person. Otherwise the cache is useless at scale — and caching by person
while keying on query is how access-control leaks happen.

## 8. Failure behaviour

Stated explicitly because the default behaviours are all wrong for this domain.

- **A source is offline.** Return the partial result with an explicit notice naming how many
  sources contributed and how many did not. Never return a partial result silently.
- **A query times out.** Return the partial traversal with its depth, and a message naming the
  narrowing action. Never return an empty result for a timeout.
- **A model is unavailable.** Extraction jobs queue rather than fail. The document is ingested
  and searchable; extraction is marked pending and visible as such.
- **The graph store rejects a write.** The staged Parquet is intact; the job is retryable with
  no data loss. This is the property the staging layer buys.
- **The audit stream is unavailable.** Reject reads. This is the one case where the platform
  fails closed.
