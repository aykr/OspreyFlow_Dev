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

### 3.0a The OpenAPI document (the owner's answer of 1 November 2026)

```
GET    /v1/openapi.json                        the API's OpenAPI document, its info.version the release (signed in)
```

**Published at the deployment's address, behind sign-in, versioned with the release.** The document
is served under `/v1/`, so the workspace's proxy carries it to the deployment's address with every
other route (`05_DEPLOYMENT.md` §2.6.1), and it takes a signed-in principal as every other `/v1`
route does; any signed-in person may read it. FastAPI's own unauthenticated copies (`/openapi.json`,
`/docs`, `/redoc`) are switched off: no page of this API answers without sign-in except `/healthz`.

**Its `info.version` is the release, from one source.** The deployment's version is the release tag
its checkout sits on, else `dev-<short commit>` (ADR-114 Amendment 8), rendered into
`deployment.env` as `OSPREY_RELEASE_VERSION` by `harness.render.release_version`. The Conduit reads
it in one place (`services/api/release_version.py`), and both Admin → System and the OpenAPI document
say that value; neither keeps a version of its own, and neither says FastAPI's default `0.1.0`. A
process started with no rendered version says `dev-unknown`. The packages' own `version` fields in
`pyproject.toml` and `package.json` are not the release and are not read.

**Tests:** `tests/services/api/test_openapi_published.py` — refused without sign-in; FastAPI's
unauthenticated copies gone; the version rendered from a checkout tagged `v0.4.1` read back through
the route; the workspace proxy's `/v1/` location carries it. It closes the GDS baseline audit's
open-standards item O1.

### 3.1 Investigations

```
POST   /v1/investigations                      create; optional `domains`, the case's domain packs (ADR-126); NULL until chosen
GET    /v1/investigations/{id}                 metadata, not the working set
PUT    /v1/investigations/{id}/tab             open or close this case's tab, for the caller only
GET    /v1/investigations/{id}/history         addressable step history
POST   /v1/investigations/{id}/history/{step}  restore to a step; a step marked `restorable: false` (a case-brief edit) is refused 409 `step_not_restorable` (ADR-128 Amendment 1)
GET    /v1/investigations                      the cases the caller holds a level on
PATCH  /v1/investigations/{id}                 rename and/or set the case's domain packs, atomically and audited (Author; ADR-126)
DELETE /v1/investigations/{id}                 remove, softly (Author, or the unit's osprey-admin)
GET    /v1/investigations/{id}/access          the caller's level; an Author sees every grant
PUT    /v1/investigations/{id}/access          the unit-wide level (Author)
PUT    /v1/investigations/{id}/access/grants/{account}     grant a level to one account, or to a team as `team:<role id>` (Author); 409 service_account for an account the directory holds that is no enabled person, or a dashboard identity above Viewer (ADR-145 Amendment 5 point 7); 409 no_such_team
DELETE /v1/investigations/{id}/access/grants/{account}     withdraw it (Author)
GET    /v1/investigations/{id}/access/history  who was granted what, and when (Author)
```

**Case views (ADR-144; `01_DOMAIN_MODEL.md` §2.2c).** A view holds no data, and every route below
stands behind the case's own level check first: a reader with no level on the case is refused each
one exactly as for a case that does not exist. Saving, sharing and deleting need `investigate`;
listing and opening need only a level. Each answer is a `CaseView`, which counts a view's chosen
nodes and never names them or their positions (rules 3 and 7).

```
GET    /v1/investigations/{id}/views                  the case's views the caller may see: their own, and those shared
POST   /v1/investigations/{id}/views                  save a view, private to the caller (`CaseViewInput`: a name, exactly one of `node_ids` or `filter`, a layout, a window, a threshold)
GET    /v1/investigations/{id}/views/{view}           open it now (`CaseViewOpened`): what the caller may see, the saved positions of those alone, and `missing`, a count naming none
POST   /v1/investigations/{id}/views/{view}/share     share it with the case's members, at their own levels (its creator only; 403 `not_the_views_creator` for a member who can see it)
DELETE /v1/investigations/{id}/views/{view}           delete it, and nothing else (its creator only, as above)
```

Someone else's private view, another case's view and no view at all answer alike: 404
`view_not_found`. A view's `window` and `threshold` are returned on the view. The window is the
timeline's range, which the Glass applies to the timeline as it does for the case. The threshold is
the Conduit's (ADR-144 Amendment 2 decision 3): opening a view returns each node it shows with the
cluster it falls in at the view's `threshold`, or the case's when the view has none, worked out from
the `SAME_AS` and `NOT_SAME_AS` links among the shown nodes alone, read with the caller's principal.
A link the caller may not see joins nothing, and a manual split holds however loose the view
(`test_a_view_opens_collapsed_at_its_threshold`,
`test_a_match_the_reader_may_not_see_does_not_collapse_what_they_see`).

**Drawing boards (ADR-143 decisions 4 to 7; Amendments 2 and 3; `01_DOMAIN_MODEL.md` §2.2d; L3.3).**
A board is a view with `drawing` on, kept by the views store and never listed among the case's
views. What is drawn on it is written into the graph: into the case's analyst layer, or, in the home
case of a drawn dataset, into that dataset (Amendment 3 decision 1); never into a source. Each drawn
node and link carries `provenance.drawn` (`DrawnAssertion`: its board's item id, who asserted it, the
board and the case, the analyst's label, a grading in the deployment's scheme, a source note, a
document of the case, or both). The board's registry (`board_items`) holds ids and a link's ends
only; every element is read through the caller's principal, scoped to the case's read set and
filtered in the adapter (rule 3). Every route stands behind the case's level check first. Reading
needs `investigate`; drawing needs Editor, `draw_on_boards` and `investigate` too (a role with
`draw_on_boards` alone would make a board it could not open), and only a board's creator draws on
it, moves its items or adds to it (403 `not_the_boards_creator` for a member who can see it). A
board's id is told to its creator alone, so another member's private board is in nothing anyone
else reads (rule 3): a drawn element's source locator names no board, and every read path (the
adapter's serialisation and the working set's projection, through `withhold_sources`) gives its
`provenance.drawn.board_id` empty to anyone but its author, who made the board. A shared board is
found by the board routes, not by its items
(`test_a_private_boards_id_is_on_no_other_members_canvas`, through the canvas's own `sync`). A *Same* or *Not
the same* is registered on its board (`board_items` kind `match`), so it goes with its drawn node.

```
GET    /v1/investigations/{id}/boards                         the case's boards the caller may see (`Board`: name, creator, shared, how many drawn nodes the caller may see; `start` is `selection` when the caller may see one of the nodes it started from, `blank` otherwise, a view's start reading as `selection` since the store keeps only the nodes)
POST   /v1/investigations/{id}/boards                         a board (`BoardInput`: blank, from a view, or from a selection; only the loaded nodes the caller may see are kept, as live references)
GET    /v1/investigations/{id}/boards/{board}                 open it now (`BoardOpened`): its drawn items and references the caller may see, `drawn` naming which are drawn, `missing` the count of the board's own references whose drawn item has been withdrawn since, given to the board's creator alone and never counting what the caller was never allowed to see (rule 3; `test_missing_counts_what_was_lost_and_never_what_was_never_allowed`), the case's node and link types, the markings up to the case's ceiling and the caller's clearance, the grading scheme, `may_draw`
POST   /v1/investigations/{id}/boards/{board}/share           share it with the case (its creator only)
DELETE /v1/investigations/{id}/boards/{board}                 delete it; what was drawn on it stays in the layer, with its watches
POST   /v1/investigations/{id}/boards/{board}/items           declare a node (`DrawnItemInput`), with its watch; audited as draw_item
POST   /v1/investigations/{id}/boards/{board}/links           draw a link between two items on the board, drawn or loaded (`DrawnLinkInput`); a loaded end is untouched; audited as draw_link
PUT    /v1/investigations/{id}/boards/{board}/layout          move items (`BoardMove`): the board's own layout, not data
PATCH  /v1/investigations/{id}/board-items/{item}             the author edits their own item (`DrawnItemEdit`), in place; a marking is never lowered (409 `marking_never_lowered`)
POST   /v1/investigations/{id}/board-items/{item}/withdraw    the author withdraws their own item (`Withdrawn`): out of every read, never deleted; each drawn link and picture resting on it goes with it, those the caller may see named (`links`, `pictures`), one they may not see named only in the audit and counted nowhere, not even in `watches_ended`; audited before it is written
GET    /v1/investigations/{id}/boards/{board}/matches         *Looks like a loaded item* (`MatchSuggestions`): `inferred`, acting on nothing
POST   /v1/investigations/{id}/boards/{board}/matches         *Same* (one `SAME_AS`, score 1.0) or *Not the same* (one `NOT_SAME_AS`) in the layer (`MatchDecision`); no node is written
PUT    /v1/investigations/{id}/boards/{board}/nodes/{node}/picture   upload a picture of a drawn node (`?name`, `?marking`, `?source_note`, all required): an image Document and its DEPICTS in the layer; a later picture supersedes it; audited before the file or the graph is written
POST   /v1/investigations/{id}/boards/{board}/nodes/{node}/picture   link a picture the case holds (`PictureChoice`: an image Document the caller may see) by a DEPICTS in the layer, marked at least as the image is; the image stays in its dataset; audited, with that marking, before the link is written
GET    /v1/investigations/{id}/boards/{board}/pictures        each drawn node's picture the caller may see
GET    /v1/investigations/{id}/boards/{board}/nodes/{node}/picture   that picture's file
GET    /v1/investigations/{id}/drawn-watches                  the watches drawing set in the case (`DrawnWatch`), each withheld whole from a caller who may not see its item
POST   /v1/drawings                                           *New drawing board* with no case (`DrawingInput`; create_case and draw_on_boards): a drawn dataset, its home case and its board (`NewDrawing`)
```

Someone else's private board, another case's board and no board at all answer alike: 404
`board_not_found`; an item of another case, one the caller may not see and none answer 404
`item_not_found`. Each refusal of a drawing is said in words before anything is written:
`above_the_ceiling` (409, naming the case's highest allowed marking: the strictest its datasets
set, a composite's members' among them, the deployment's highest where none is set; Amendment 2
decision 3; `test_the_ceiling_of_a_case_reading_a_composite_is_its_members`), `above_your_clearance`
(409), `not_in_the_model` (422: a node type of the case's model only, C14, never `Alert` or
`Document`; a link type of the model only, never a resolution, picture or alert link),
`not_a_property` (422: a type's required property missing, or one it does not declare),
`ends_not_on_the_board` (422), `wrong_ends` (422), `already_drawn` (409: the same link already
drawn between the two), `not_your_item` (403), `promoted` (409: changed only by reverting its
promotion, L3.4; a withdrawal is refused the same way while a promoted link rests on the item),
`not_a_marking` (422), `no_source` (422: an edit, or a picture, with no source left). A promoted
link the withdrawer may not see is left in place and tells them nothing: their answer is the one
they get with no such link (the orchestrator's ruling, 8 November 2026). The registry's
`promoted_at`, which L3.4 sets, says it was promoted, so the element is never read for it
(`test_an_unseen_promoted_link_stays_and_tells_the_withdrawer_nothing`). Further refusals:
`marking_never_lowered` (409), `link_marking_kept` (409: a drawn link's marking is not changed by
an edit, since the store would leave a second link for the other audience), `no_such_document`
(422), `not_a_picture` (422), `no_picture_for_this_type` (422, before the file is kept). Edits,
pictures and match decisions are judged against the ceiling as the merged handling of what they
touch, and every refusal is judged before the layer is made. A withdrawal is `withdraw_drawn` under
`board-withdrawal:<item>`: the element and what rests on it are reverted for every reader and kept
in the store. A drawn item is changed only on its board: the canvas routes that would change one
(ADR-105's entity picture, a link's change, a retract) answer 409 `drawn_on_its_board` in words
(`test_a_drawn_nodes_picture_is_refused_on_the_canvas_route`, `test_a_drawn_link_is_not_changed_from_the_canvas`).

A deleted view's conversation stays in the store, read by no route: the questions are listed only
through a view the reader may open, so they go with the view. Its pending proposals stay pending
and read by no route either, since each candidate store read leaves out one kept with a view the
request was not let into (`test_a_deleted_views_conversation_and_proposals_are_read_by_no_one`). A view of chosen nodes reads them by id from the graph under the caller's scoped
principal, with the links among those it may show. A filtered view narrows the caller's own
projection of the case's working set. Either way, a result past the working set's cap is the typed
`limit_exceeded` (§4).

**Authorization.** Every route above an investigation id checks the calling
`Principal.org_unit` against that investigation's own `owning_unit` — set once at creation from
the acting principal's own unit, the same shape as `Handling.owning_unit`
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
| Viewer | `GET` the case; `access` (GET: the caller's own level); `tab` (PUT: the caller's own flag, ADR-084); `views` (GET, POST), `views/{view}` (GET, DELETE), `views/{view}/share` (POST; ADR-144: saving, sharing and deleting also need `investigate`, and only a view's creator shares or deletes it); `boards` (GET), `boards/{board}` (GET), its `matches` and `pictures` (GET), a node's `picture` (GET), `drawn-watches` (GET) (ADR-143: also `investigate`); `datasets` (GET, ADR-099); `search`, `suggest`, `paths` (POST, ADR-099); `explore/counts`, `explore/most-connected`, `explore/busiest-links`, `explore/busiest-days`, `explore/groups`, `explore/whats-new`, `explore/starter-questions`, `nodes/{node}/shared-contacts` (GET, ADR-100); `expand/preview`; `patterns/preview`, `patterns/run`, `patterns/ask` (POST), `patterns`, `patterns/{pattern}` (GET); `compute/{metric}`; `connection-strength`, `rarity` (POST) and `strength-influencers` (GET; ADR-139); `resolution/threshold` (GET); `resolution/explain/{cluster}`; `hotlists`, `monitors`, `alerts`, `alerts/{alert}` (GET, ADR-099 Amendment 3); `rules`, `alert-queue`, `alert-queue/counts`, `alert-queue/{alert}`, `ownership/{node}`, `kyc/{node}`, `risk/{node}` (GET, ADR-109); `questions` (GET, ADR-098); `ingest/candidates` (GET); `dossier/documents/{doc}`; `documents/{doc}/reader`, `documents/{doc}/file` (GET); `history` (GET); `brief` (GET, ADR-128); `judgements`, `gaps`, `assumptions` (GET); `links/{edge}/notes`, `links/{edge}/history`, `links/{edge}/events` (GET); `link-types` (GET, ADR-090) and `link-types/promotable` (POST, ADR-143 decision 9); `sites/{site}` and its `image` (GET); the Ingest Studio's reads (`ingest/source-files`, `ingest/recipes`, `ingest/recipes/{recipe}`, its `profile`, `map/sample-rows/{row}` and `map/handling-preview`, `staging-preview` (POST, ADR-140 Amendment 12), `ingest/recipe-registry`; ADR-099 Amendment 4); `events/holders` (GET, ADR-099 Amendment 9); `trends`, `trends/options`, `trends/{trend}/figures` (GET) and `trends/preview` (POST); `packs`, `packs/{pack}`, its `history` and `published`, and the case's `published` (GET; ADR-113); the delta stream |
| Editor | `boards` (POST), `boards/{board}` (DELETE), its `share`, `items`, `links`, `matches` (POST), `layout` (PUT), a node's `picture` (PUT, POST), `board-items/{item}` (PATCH) and its `withdraw` (ADR-143: also `draw_on_boards`, and the board's creator alone); `seed`; `expand`; `working-set/add-by-identifiers` (ADR-128); `nodes` (DELETE); `nodes/{node}/confirm`, `retract`, `suppression-mark` (POST, DELETE; ADR-099 Amendment 1); `links-among` (ADR-098); `explore/starter-questions/{question}/run`, `nodes/{node}/shared-contacts/{other}/canvas` (ADR-100); `resolution/threshold` (PUT), `link`, `split`; `patterns/save`; `hotlists`, `monitors` (POST); `hotlists/{hotlist}/audience` (PUT, ADR-133); `held-rows` (GET, ADR-109); `alert-queue/{alert}/claim`, `release`, `disposition`, `canvas`, `assign`, `alert-assignees` (GET, ADR-133), `ownership/{node}/canvas` (ADR-109); `questions` (POST) and `questions/candidates/{candidate}/accept`, `reject` (ADR-098); `documents` (POST), `documents/{doc}/extract`, `designations`, and its candidate `accept`, `reject`; `ingest/extract`, its candidate `accept` and `reject`; `links/{edge}/events/documents`, `links/{edge}/events/{event}/extract` and its candidate `accept`, `reject`; `history/{step}` (restore); `judgements`, `gaps`, `assumptions` (POST); `links/{edge}/notes` (POST), `links/{edge}/notes/{note}` (PUT, DELETE), `links/{edge}/change` (POST); `link-types` (POST), `link-types/{proposal}/withdraw` (the proposer or an Author, ADR-090); `export`; `sites` (POST), `control-points`, `grid`; the Ingest Studio's writes (`ingest/source-files` (POST), `ingest/recipes` (POST), `ingest/recipes/{recipe}` (PATCH), its `versions`, `row-template`, `verify`, `publish`, `schedule` and `run`); `trends` (POST), `trends/{trend}` (DELETE); `packs` (POST), `packs/{pack}/items` (POST) and `items/{item}` (DELETE), its `order`, an item's `refresh`, `publish`, `versions/{v}/withdraw` and `export` (ADR-113) |
| Author | `PATCH` the case (rename); `DELETE` the case (a soft remove: it then reads as not found to everyone, nothing is deleted, ADR-052 Amendment 7; the unit's `osprey-admin` may too, through the same safety net); `datasets` (PUT: what the case reads, ADR-099 decision 3); `access` (PUT: the unit-wide level, which is none, Viewer or Editor, never Author); `access/grants/{account}` (PUT, DELETE); `access/history`; the case brief's writes (`brief/priority`, `brief/requirements` and each requirement's text, `status`, removal and `attachments`, ADR-128); `rules` (POST), `rules/{rule}/retire`, `rules/audit` (GET; the admin's safety net reaches this one too), `held-rows/reject`, `ingest/recipes/{recipe}/held-rows/release` (ADR-109); `strength-influencers` (PUT: the case's own influencers, ADR-139). An `osprey-admin` in the case's own unit may also use these without holding a level (the safety net, audited as `access_admin_override`); that gives no other access. |

`GET /v1/investigations` lists the cases the caller holds a level on (id, name, their level, created,
created by, whether the caller has closed the case's tab, and the names of the
dataset it chose, never its analyst layer). `POST /v1/investigations` takes either `dataset_ids`, exactly
one source or composite dataset of the caller's unit, or `new_dataset_name`, an empty dataset of the
caller's unit made first; neither, both, or two ids is 422 `dataset_refused` and no case is made (ADR-099
Amendment 12 item 6: the Conduit no longer makes a case a dataset of its own). The case's analyst layer
is made with it (ADR-143 decision 1; `01_DOMAIN_MODEL.md` §2.2a). No case is made from another
since L3.2; one made so since L3.1, until the upgrade turns it into a view, reads its original's chosen
dataset and layer, read-only, holding none of its own: a mark or link made in it is 409
`original_layer_read_only` (ADR-144 Amendment 1 decision 2; its code before L3.2 named the retired
kind of case, renamed by Amendment 2). A case opened from an alert reads the
dataset and gets an empty layer of its own (ADR-143 Amendment 1 item 3). Under a case, what is written joins its source; an entity marked
by hand and a manual link or split join its layer (ADR-143 Amendment 1). A case reading a composite
writes nothing but into its layer: every other write is 409 `composite_read_only` ("do this in a
case that reads that dataset"), and so is any write into a composite's id (ADR-099 Amendments 14
and 15; the Studio's routes of a composite too). Its monitors keep working, their alerts raised into
its layer, and its scheduled loads are refused, each slot in words. No case is made from another
(ADR-144 Amendment 1): a smaller part of a case is a case view (above). `GET .../access` shows anyone their own level, and shows an Author the
unit-wide level, every grant and the grantees' display names (`names`, ADR-106: only ids already in
the grants served). A grantee is named by account id — the token's `sub`, which the Admin area shows
for a person or a dashboard identity; any other string grants nothing to anyone (ADR-052 P3, as
corrected by Amendment 12).

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
POST   /v1/investigations/{id}/working-set/add-by-identifiers  count, then add, a list of identifiers (ADR-128 decision 1)
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
{"seq": 414, "op": "remove",  "node_ids": ["..."], "edge_ids": ["..."]}
{"seq": 415, "op": "reproject", "reason": "resolution_threshold"}
{"seq": 417, "op": "snapshot", "nodes": [...], "edges": [...], "withheld": true}
{"seq": 418, "op": "replace_edge", "old_edge_id": "...", "edge": {...}}
{"seq": 419, "op": "view_over_cap", "would_be": {...}}
```

Every delta is projected for its reader before it is sent (ADR-124 decision 4). A delta names only
what that reader may see: a removal names only ids they may read, a reproject carries no figures,
and a replacement that would name a hidden link is sent as a removal, an addition, or nothing,
by ADR-124's four-row table. The stored form of a removal or a replacement carries a record of what
it removed; the record is never sent. There is no `update` operation and no `notice` operation
(ADR-124 Amendments 4 and 6).

`replace_edge` (ADR-080) is sent when an analyst changes a link the reader may see on both sides:
the client takes the old link out and puts the new one in at the same step, so no screen shows both
or neither.

Sequence numbers are monotonic per investigation. A client that misses a sequence reconnects and
requests a full snapshot rather than attempting to patch — silent divergence between the
server's picture and the analyst's is the failure this protocol exists to prevent. `snapshot` is
that full-state response. Only the full snapshot `sync` returns carries `withheld`: true when the
case holds any node or link whose own handling the reader may not view, judged without datasets;
every other snapshot and delta carries none (ADR-124 decision 5). The Glass shows it as the one
standing sentence, "This case holds material you are not cleared to see.", with no number.

`view_over_cap` is sent instead of a snapshot or a delta when the reader's own projected view has
passed the working-set cap, with the reader's own figure only; the stream then sends nothing more on
that connection until the reader tries again (ADR-124 decision 2, Amendment 9).

Withheld means withheld from this reader by handling, and nothing else. No delta, snapshot or
response carries a count of what is withheld from the reader (ADR-124 decision 1). What may still
vary with it is limited to the existence signals ADR-124 decision 12 accepts (the standing sentence
among them) and the residuals its amendments record. A link whose end has left the working set (removing a node leaves its links
in the store) is left out of every read.

### 3.3 Query and analytics

```
POST   /v1/investigations/{id}/search      federated search across graph, documents, index, within the case's datasets (ADR-099)
GET    /v1/datasets                     the source and composite datasets of the caller's unit, for a new case to name (ADR-099); never an analyst layer, for any role (ADR-143 decision 1); none to a caller holding no right (Amendment 11)
POST   /v1/datasets                     a new, empty source dataset of the caller's unit (`{"name": ...}`), audited (ADR-099)
POST   /v1/datasets/composites          a composite of two or more of the caller's unit's source datasets (`{"name", "member_ids"}`), audited; a member of another unit, a missing one, a composite or an analyst layer is 422 `dataset_refused`, one answer for all (ADR-099 Amendment 12 item 2)
POST   /v1/datasets/drawn              *New drawing board* with no case (`{"name", "pack", "highest_marking"}`, create_case): a drawn dataset, its domain model live at version 1 and its home case, the maker its Author, audited; a highest marking above the maker's clearance is 409 `above_your_clearance`, one not of the scheme 422 (ADR-143 Amendment 2 decisions 3 and 5)
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
POST   /v1/investigations/{id}/connections the fewest degrees connecting two nodes and the routes there, or the routes at a degree asked for (ADR-116)
POST   /v1/investigations/{id}/patterns/preview   cardinality estimate for a visual query, within the case's datasets (ADR-099)
POST   /v1/investigations/{id}/patterns/ask   a question to the model, given only the case's vocabulary and the question; the proposed pattern is validated against the ontology and ADR-121 and returned with a one-line explanation and the preview's count, nothing run; `$selected_n` resolves only to selected nodes the reader may see; 422 `could_not_express`, Viewer with the `ask_model` right (ADR-129)
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
PUT    /v1/investigations/{investigation_id}/nodes/{node_id}/picture        one entity's own picture, an image Document that DEPICTS it, replacing the one seen before (kept); marking and legal basis required; 409 `composite_read_only` in a case reading a composite ("do this in a case that reads that dataset"), nothing written (ADR-099 Amendment 15), before any file is stored, Editor (ADR-105)
DELETE /v1/investigations/{investigation_id}/nodes/{node_id}/picture        back to its type's picture; its own is kept, no longer shown; 409 `composite_read_only` in a case reading a composite ("do this in a case that reads that dataset"), nothing written (ADR-099 Amendment 15), Editor (ADR-105)
GET    /v1/investigations/{investigation_id}/nodes/{node_id}/picture        the entity's picture's file, to someone who may see it; one they may not answers as none, Viewer (ADR-105)
POST   /v1/investigations/{investigation_id}/pictures                       which of these entities have a picture of their own the caller may see, Viewer (ADR-105)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/extract   entities from a held Document by kind: text, an image described and read, a video transcribed; `using`: `recogniser` (the default, ADR-098) or `model`, Editor (ADR-094)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/candidates/{candidate_id}/accept   accept one finding from a held Document as an inferred node, Editor (ADR-094)
POST   /v1/investigations/{investigation_id}/documents/{document_id}/designations   words in a Document marked as an entity by the analyst: an asserted node linked to it, both written in the case's analyst layer (ADR-143 Amendment 1; 409 `no_analyst_layer` when the case reads nothing, and nothing is written), Editor (ADR-098)
POST   /v1/investigations/{investigation_id}/links-among   the links among nodes already in the view (all, or the named ones), all or `limit_exceeded`, Editor (ADR-098); with `degree` 2–6 and 2–8 named nodes, also the routes between them within it (Amendment 4)
GET    /v1/investigations/{investigation_id}/datasets   the dataset the case chose (a source or a composite; never its analyst layer), Viewer (ADR-099, ADR-143)
PUT    /v1/investigations/{investigation_id}/datasets   what the case reads (`{"dataset_ids": [one]}`, a source or composite of the Author's unit; else 422 `dataset_refused`, one answer for two ids, another unit's, a missing one and an analyst layer), audited before and after, Author (ADR-099 Amendment 12)
POST   /v1/investigations/{investigation_id}/questions   a question to the model about every Document in the case's view the analyst can see, whole, and the graph facts around the selection (one hop) or the whole view, within the timeline window when one is set; the answer cites Documents and `[G-n]` facts and its proposals are pending findings; documents and facts together past the budget refused 409 `limit_exceeded` with its three options, never trimmed (ADR-129 decision 1, Amendment 1), none `no_documents` (422), Editor (ADR-098 decision 4)
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
POST   /v1/investigations/{id}/connection-strength   each working-set link's connection strength as the reader may see it, with what changed it, and the legend (ADR-139), investigate, Viewer
POST   /v1/investigations/{id}/rarity   shared-attribute rarity over the working set: each entity's highest, and the pairs asked for with their shared attributes ranked; past its cap `limit_exceeded` (ADR-139), investigate, Viewer
GET    /v1/investigations/{id}/strength-influencers   the case's legend (the influencers in force, a case override marked) and its override, investigate, Viewer
PUT    /v1/investigations/{id}/strength-influencers   the case's own influencers and those switched off in it, by its Author; no second person; every version kept and audited, investigate, Author
GET    /v1/strength-influencers   every installation-wide influencer version, newest first, and the weights file's defaults, manage_strength_influencers
POST   /v1/strength-influencers   propose a new installation-wide version, pending until a second person approves it, manage_strength_influencers
POST   /v1/strength-influencers/{version}/approve   a second holder puts the waiting version in force, never its proposer (`403 own_change`), manage_strength_influencers
POST   /v1/strength-influencers/{version}/send-back   send the waiting version back with words (or withdraw one's own), manage_strength_influencers
GET    /v1/jobs/{id}/events             SSE progress stream
```

**Connection strength and rarity (ADR-139).** Both reads start from the working set's membership
narrowed to what the reader may see (as `compute/{metric}` does) and ask the graph adapter as the
reader: strength is each link's stored weight with the influencers in force in the case (case
override, then the installation's approved set, then the weights file's), an influencer applying only
where a record the reader may see evidences the link (or, ADR-139 Amendment 2, the link belongs to a
dataset the influencer names and the reader may read); rarity is the client's share measure (or
`Σ ln(N_visible / df_visible)`, the IDF measure, by the installation's choice) over shared attribute
nodes, per dataset by default (`01_DOMAIN_MODEL.md` §6.1a). Both read the case's composition and
measure, resolved case override, installation version, weights file: under client parity a link's
strength is its rarity term plus the adds (`raw_sum` beside the drawn 0–1 strength), and each pair
asked for carries its parity sum. An installation version (`POST /v1/strength-influencers`) may name
`composition` and `rarity_measure`, in force only once approved; the case's `PUT` may name
`composition`. A dataset-triggered influencer is named to a reader only by the datasets they may read,
in the legend and in the case's override. Neither is stored. The
response carries scores, the influencers' definitions and the reader's own visible attributes, never
`N`, `df`, a corpus count or the weight components (rule 7). An influencer naming a type, property,
value or link type the ontology does not declare is refused `422 influencer_refused`, in words. A
pending version changes nothing; one waits at a time (`409 influencer_change_refused`).

**The analytics reads are case reads (ADR-084 Amendment 2).** `histogram`, `cross-filter`,
`first-seen`, `geobins` and `sightings` carry their case in the body (`EventFilter.investigation_scope`)
and take the same gate as every case route, at Viewer: a case the account holds no level on answers
404 and reads nothing, and the refusal is audited. A case reads its own events alone (ADR-144
Amendment 1 ended ADR-084 Amendment 2's widening to the case another was made from), and so do the
events behind one link and an email extracted from one. `EventFilter.inherited` is always set by the
Conduit, to nothing; a value sent by a caller is discarded.
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
POST   /v1/ingest/schedule-preview      a schedule in words and its next five runs, or refused in words (ADR-110)
POST   /v1/investigations/{id}/ingest/recipes/{rid}/schedule/pause    pause the schedule — schedule_pipelines
POST   /v1/investigations/{id}/ingest/recipes/{rid}/schedule/resume   resume it — schedule_pipelines
GET    /v1/investigations/{id}/ingest/recipes/{rid}/runs   the recipe's run ledger; counts withheld above the reader
GET    /v1/investigations/{id}/data-feeds   the pipelines feeding the case (Viewer, read_data_feeds)
GET    /v1/admin/schedules              every schedule (operate_schedules)
GET    /v1/admin/schedules/{rid}/runs   one schedule's run ledger (operate_schedules)
PUT    /v1/admin/schedules/{rid}        change one schedule; 409 `composite_read_only` for a schedule whose case reads a composite or whose recipe's dataset is one (ADR-099 Amendment 15); operate_schedules
POST   /v1/admin/schedules/{rid}/run    run it now; 409 `composite_read_only` for a schedule whose case reads a composite or whose recipe's dataset is one (ADR-099 Amendment 15); operate_schedules
POST   /v1/admin/schedules/{rid}/pause  pause it (operate_schedules)
POST   /v1/admin/schedules/{rid}/resume resume it; 409 `composite_read_only` for a schedule whose case reads a composite or whose recipe's dataset is one (ADR-099 Amendment 15); operate_schedules
POST   /v1/ingest/connector/{name}/run  trigger a configured connector
GET    /v1/handling-scheme              the active deployment's classification/handling-code vocabulary
GET    /v1/yardstick                    the active deployment's probability yardstick (01_DOMAIN_MODEL.md §5)
GET    /v1/grading-scheme               the deployment's grading scheme (`grading.scheme`, ADR-143 decision 11) and each part's grades, for Admin's read-only display; any signed-in person, as the yardstick
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
GET    /v1/investigations/{id}/brief   the case brief (ADR-128 decision 3): the priority information requirement and the information requirements, each open or answered, with only the attachments this reader may read (one they may not is absent, with no title and no count)
PUT    /v1/investigations/{id}/brief/priority   set or clear the priority requirement
POST   /v1/investigations/{id}/brief/requirements   add a requirement; a 21st is 409 `too_many_requirements`
PUT    /v1/investigations/{id}/brief/requirements/{requirement}   change its text
DELETE /v1/investigations/{id}/brief/requirements/{requirement}   remove it with its attachments
PUT    /v1/investigations/{id}/brief/requirements/{requirement}/status   open or answered: the one route that sets a status, a person's (rule 5)
POST   /v1/investigations/{id}/brief/requirements/{requirement}/attachments   attach a trend, pattern, assessment or view the Author may read; absent and unreadable are the same 404 `attachment_not_found`
DELETE /v1/investigations/{id}/brief/requirements/{requirement}/attachments/{kind}/{attachment}   detach
POST   /v1/investigations/{id}/links/{edge}/change   change a link's type and/or details (`{"reason": "...", "type"?, "properties"?, "interval"?, "occurrences"?}`) by superseding it; 200 with the new link, the `replace_edge` step and the change record; 404 `link_not_found` as for notes; 422 `invalid_link_change` (no reason, over 1,000 characters, or the ontology refuses), `nothing_changed`, `resolution_link` for a same-as or not-the-same link, either way round (ADR-080); `handling`? and `confirm_lower`? (ADR-102): a raise is an Editor's, a lower handling in any part is an Author's with `confirm_lower`, else 403 `lowering_needs_author` or 409 `confirm_lower_handling`; a handling that moves the units, is above the analyst's own, or names a code the scheme lacks is 422 `invalid_link_change`; 409 `composite_read_only` in a case reading a composite ("do this in a case that reads that dataset"), nothing written (ADR-099 Amendment 15)
GET    /v1/investigations/{investigation_id}/link-types   the relationship types a link in the case may take: the ontology's (the OspreyFlow default dataset's), those accepted into the model of a dataset the case reads once that version is live, and those proposed in this case alone (`proposal_id` set; ADR-143 decision 9; a proposal made before ADR-099 Amendment 3 keeps ADR-090's case and in-view rule), Viewer (ADR-090)
POST   /v1/investigations/{investigation_id}/link-types   propose a type when none fits (`{"name", "from_types", "to_types", "directed"?, "label"?, "colour"?, "thickness"?, "reason"}`): usable at once in this case alone, probabilistic, belonging to the case's source dataset (never its layer); 422 `proposal_refused` for a name the ontology or the dataset's live model has (never the draft's, which would tell of another case's accepted proposal), or the case already offers, or one that is not a type name, and in a case reading no dataset; 409 in a case reading a composite; `propose_types`, Editor (ADR-090, ADR-143 decision 9 and Amendment 4)
POST   /v1/investigations/{investigation_id}/link-types/{proposal_id}/withdraw   withdraw a pending proposal made in this case (`{"reason"}`), its proposer or an Author; another case's, even of the same dataset, 404 `proposal_not_found`; `propose_types`, Editor (ADR-090)
POST   /v1/investigations/{investigation_id}/link-types/promotable   whether links of each type named (`{"types"}`) can be promoted from this case into its source dataset (`{"types": [{"name", "promotable", "reason"}]}`): a proposed, declined or withdrawn type's cannot, nor one accepted whose model version is not yet live, each said why; another case's proposal answers as a name that is no type; `investigate`, Viewer (ADR-143 decision 9; L3.4's sheet asks the same)
GET    /v1/investigations/{id}/links/{edge}/history  every earlier version of one link and the changes between them, newest first, at most 100 steps (`truncated` says so) — 404 `link_not_found` unless the caller may see the link (ADR-080)
POST   /v1/investigations/{id}/export    runs the handling gate; may return 409 with blockers
GET    /v1/exports                       the compliance-facing export ledger (ADR-047's own Gap 2) — role-gated, not per-investigation
GET    /v1/investigations/{id}/ingest/candidates   extraction candidates for one document (?document_id=); the unit's, less those kept in another case's analyst layer (a mark made by hand there, ADR-143 Amendment 1 item 5)
```

**The block above illustrates an earlier, abandoned ingest design — `09_INGEST_STUDIO.md`'s own
recipe-based routes, below, are what the Ingest Studio actually calls.** Neither block is pruned:
the illustrative one predates the Studio and matches no route this app registers under that shape,
but removing it would trade a wrong row for a blank one rather than a correct one, so it stays as a
disclosed historical illustration alongside the real surface.

```
GET    /v1/ingest/connectors                               the connector catalogue (09_INGEST_STUDIO.md §2)
GET    /v1/ingest/packs                                    the domain packs a pipeline's root may name (09 §1.1)
GET    /v1/ingest/connections                              the connections a source is registered on (ADR-140 Amendment 4; SOURCE_AUTHOR)
GET    /v1/admin/connections                               the deployment's connections (administer_system)
POST   /v1/admin/connections                               an administrator names a connection, audited: files, or sql, api and json with their settings and a secret's name, never its value (ADR-140 Amendment 13)
POST   /v1/admin/connections/{connection_id}/test          Test connection: a SQL login over TLS found read-only, an API's host allowed and its secret set; nothing read (administer_system)
GET    /v1/datasets/{dataset_id}/source-files              the register wizard's files: the dataset's own, as Connect lists them
GET    /v1/datasets/{dataset_id}/sources                   the dataset's registered sources
POST   /v1/datasets/{dataset_id}/sources                   register a source once: a file the dataset's listing offers, else 422; 409 if registered. On a sql, api or json connection, read once into its own file in the dataset's folder and registered on it only if that read succeeds
POST   /v1/datasets/{dataset_id}/sources/{source_id}/read  Refresh now for a sql, api or json source: read again into its file (an incremental SQL source past its cursor); audited (add_ingest_files)
GET    /v1/datasets/{dataset_id}/screening-subscriptions   the deployment's screening lists, and which this dataset subscribes to, by id (add_ingest_files)
PUT    /v1/datasets/{dataset_id}/screening-subscriptions/{list_id}     subscribe by the list's id (404 for an id no list has); audited
DELETE /v1/datasets/{dataset_id}/screening-subscriptions/{list_id}     unsubscribe; audited
GET    /v1/datasets/{dataset_id}/reference-lists/offered   the lists its rules and Lookups are offered: its own and its subscriptions, exactly as the save gate reads them (edit_pipelines)
POST   /v1/datasets/{dataset_id}/reference-lists/{list_id}/import      its own list's rows from one of its files, a new version only when they change (add_ingest_files)
GET    /v1/studio/screening-lists                          the deployment-wide screening lists (load_screening_lists)
POST   /v1/studio/screening-lists                          a list named with its template and its file in the ingest folder; audited
POST   /v1/studio/screening-lists/{list_id}/refresh        Refresh now: a new version only when the rows change; every attempt recorded in words
GET    /v1/studio/screening-lists/{list_id}/imports        its latest imports, newest first
PUT    /v1/studio/screening-lists/{list_id}/schedule       every day or week at an hour, as the person setting it; or by hand only
GET    /v1/datasets/{dataset_id}/sources/{source_id}        one source (404 through another dataset's route)
GET    /v1/datasets/{dataset_id}/sources/{source_id}/profile   its profile, computed for the reader, never stored
GET    /v1/datasets/{dataset_id}/sources/{source_id}/lineage   the dataset's pipelines that read it
PATCH  /v1/datasets/{dataset_id}/sources/{source_id}/governance   a new version of its governance, audited; deployed pipelines reading it need attention
POST   /v1/datasets/{dataset_id}/sources/{source_id}/refresh/pause   pauses its refresh, with why; not an edit; audited (schedule_pipelines; ADR-110 Amendment 13)
POST   /v1/datasets/{dataset_id}/sources/{source_id}/refresh/resume  resumes it; audited (schedule_pipelines)
GET    /v1/datasets/{dataset_id}/model                     its domain model: the live version and the open draft (edit_target_model, ADR-112 Amendment 6)
POST   /v1/datasets/{dataset_id}/model/draft               opens the draft, N+1, as a copy of live (v1 bare POLE if none); 409 model_refused for a second
PUT    /v1/datasets/{dataset_id}/model/draft               saves it; an extension removed not retired, or a POLE core type, 409 model_refused
DELETE /v1/datasets/{dataset_id}/model/draft               discards it; audited
GET    /v1/datasets/{dataset_id}/model/impact              what making it live would change: types, the pipelines writing them, the cases the reader may open and only the composites the reader's cases read
POST   /v1/datasets/{dataset_id}/model/make-live           the named draft live; at the dataset's first, its owners (people the directory holds, enabled, never a service account) named and its home case made first, their Authors, 409 owner_needed in words otherwise, and for a second first Make live at once; the pipelines writing a changed type flagged and paused with the reason; audited
POST   /v1/datasets/{dataset_id}/model/revert              a new draft N+2 copying an earlier version, never a rewrite; 409 no_model_yet for a dataset with none
GET    /v1/datasets/{dataset_id}/model/proposals           the link types analysts proposed for this dataset, newest first, each without its case (rule 3) or storage label (rule 7), with `in_model` (live, draft, or none); to a reader not cleared for the dataset's highest allowed marking (the scheme's highest where none is set), each with `withheld: true` and its words, ends, date and status left empty, and accept and decline refused 422 (ADR-143 Amendment 4's Open, the strict reading); accept_types (ADR-143 decision 9, ADR-090 Amendment 4)
POST   /v1/datasets/{dataset_id}/model/proposals/{proposal_id}/accept    *Add it to the draft model* (`{"basis": "direct"|"probabilistic", "reason"}`, no default for the basis; Direct only from now on): the proposal claimed only from the status read, then a link_type extension appended to the draft (opened if none) under the dataset's model lock (`TargetModelStore.add_extension`), the claim given back if that is refused (409 model_refused); same-name pending proposals of the dataset that fit merged into it; an accepted one lost from the draft and the live model may be added again; its proposer, a name already in the model, or one decided meanwhile 422 proposal_refused; another dataset's 404 proposal_not_found; a composite's 409; audited; accept_types
POST   /v1/datasets/{dataset_id}/model/proposals/{proposal_id}/decline   declined (`{"reason"}`, required): offered no more, its links stay in their case's layer for good; audited; accept_types
POST   /v1/investigations/{id}/ingest/recipes                                   Connect: create a draft
GET    /v1/investigations/{id}/ingest/recipes                                   Connect: the author's own unit's drafts
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}                        load one draft
PATCH  /v1/investigations/{id}/ingest/recipes/{recipe_id}                        Connect: edit a draft still in progress
PUT    /v1/investigations/{id}/ingest/recipes/{recipe_id}/pipeline               the canvas: save the pipeline graph (SOURCE_AUTHOR, Editor); 422 pipeline_invalid, every violation in words
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}/profile                Profile: run and read the automatic source profile
GET    /v1/ingest/transforms                                 Map: the Knowledge Adapter catalogue
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}/map/sample-rows/{row_index}   Map: page through a real row bound to the template
PUT    /v1/investigations/{id}/ingest/recipes/{recipe_id}/row-template            Map: save the row template
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/map/handling-preview    Map: preview an element's handling/provenance override
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/verify                  Verify: the dry run — no write of any kind
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/preview-graph           Preview of a Map or Load step (verify_pipelines, Editor; ADR-140 Amendment 8): Verify's dry run, writing nothing but its own audit row (`preview_studio_recipe_graph`), never marking the draft verified
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/staging-preview         A staging step's live sample (edit_pipelines, Viewer; ADR-140 Amendment 12): the steps up to one over the first ten rows of each source of the saved pipeline, writing nothing; withheld whole from a reader not cleared for every sampled row, or, with a Lookup, from a case not reading the recipe's dataset
GET    /v1/investigations/{id}/ingest/recipe-registry                             the pipelines home and Publish: every recipe the principal's own unit owns, any status (the home hides superseded)
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
mapping itself is unchanged, only when it runs. `POST .../publish` refuses (422,
`refresh_needs_a_key`) a pipeline with no deduplication key whose file is a registered source with a
refresh policy other than by hand. A refresh would load its rows again (ADR-110 Amendment 6 point
2); the dataset source routes refuse the policy itself in the same words.

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
single-candidate on these routes. The one bulk operation is the document reader's *Accept all
pending* (ADR-108 ruling Q1): `POST /v1/investigations/{id}/documents/{document_id}/candidates/accept`
takes an enumerated list of `candidate_ids` — the findings the analyst has on screen — never a
filter or a threshold, so it remains one human decision over named items (rule 5). There is still no
bulk reject. Accepting mints the node (optionally with `properties_override`);
rejecting discards the candidate with no node ever created, and neither ever produces a dossier
span (§3.6) until a candidate has actually been accepted.

### 3.5 Resolution

```
GET    /v1/resolution/threshold          current session τ
PUT    /v1/resolution/threshold          set τ; triggers a reproject delta
POST   /v1/resolution/link               analyst-asserted SAME_AS, written in the case's analyst layer (ADR-143 Amendment 1; 409 `no_analyst_layer` when the case reads nothing)
POST   /v1/resolution/split              analyst-asserted NOT_SAME_AS, written in the case's analyst layer (ADR-143 Amendment 1; 409 `no_analyst_layer` when the case reads nothing)
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
POST   /v1/investigations/{id}/hotlists   create, in the case's first dataset; identifier plus a review date, and optionally its audience (only_me or team; else the deployment's monitoring.hotlist_audience; another choice refused, 403 hotlist_audience_fixed, when hotlist_audience_editable is false); fires only on that dataset's data, Editor (ADR-099 Amendment 3, ADR-133 ruling 3)
GET    /v1/investigations/{id}/hotlists   the calling principal's own hotlists of the case's datasets, with the deployment's audience default and whether owners may choose, Viewer
PUT    /v1/investigations/{id}/hotlists/{hotlist_id}/audience   the owner's change of whom its alerts reach (only_me or team); another's hotlist is not found; 403 hotlist_audience_fixed, in words, when the deployment does not let owners choose, Editor (ADR-133 ruling 3)
POST   /v1/investigations/{id}/monitors   create a standing query the evaluator watches, in its saved pattern's dataset and matched only within it, Editor
GET    /v1/investigations/{id}/monitors   the calling principal's own monitors of the case's datasets, Viewer
GET    /v1/investigations/{id}/alerts     the calling principal's own alerts of the case's datasets, Viewer
GET    /v1/investigations/{id}/alerts/{alert_id}   one alert, expanded to its referents, Viewer
GET    /v1/alerts/{alert_id}   an alert at its own address: the case it is worked in and its explanation there (AlertAtAddress); 404 alert_not_found alike for a missing alert and one the reader may not see, read_alert_queue (ADR-146 decision 6, Amendment 2)
```

**Rules and Monitoring's gate (ADR-146 decision 2, Amendment 2).** Every route of this section and of
§3.8a's queue, rules, rule audit, held rows and screening lists asks, after its own right, for
`triage_alerts` or `author_rules`, with the `read_alert_queue` the place's entry needs
(`services/api/rules_place.py`; 403 `place_required`), but the routes used outside the place: `GET
…/alert-queue` (Home, a report pack's alert items), whose rows go only to a reader the place is offered
to and to the Reports Viewer (403 `queue_rows_not_offered` to anyone else); `GET …/alert-queue/counts`,
the queue as counts alone (`AlertQueueCounts`) for any other reader of it, Viewer and `read_alert_queue`;
and the held rows' `GET …/held-rows`, `POST …/held-rows/reject` and `POST
…/ingest/recipes/{id}/held-rows/release` (the Studio's Runs). `GET /v1/alerts/{alert_id}` answers every
refusal at the end of the quantum it falls in (ADR-146 Amendment 2 point 6).

**Owner-only, and of a dataset** — a hotlist or a monitor is a standing watch that outlives any one
investigation, and an alert belongs to the principal who owns the watch that fired it, not to
whichever investigation happens to be open when it does. Each belongs to a dataset (a hotlist to
the first of the case it was made in, a monitor to its saved pattern's; ADR-099 Amendments 3 and 4)
and is listed only in cases reading that dataset. A match in another dataset writes nothing, not
even a `notify` stub, and an alert's entities are read as its case reads them. The jump's case of its
own went in L2.9 (ADR-146 Amendment 2): an alert is opened at its address, in the case it is worked in.
`GET /v1/alerts/{alert_id}` reads the alert's case (`AlertStore.case_of`), makes the reader's level
check on it (on no case, for a missing id), scopes the reader to that case's datasets
(`scope_to_case`: the path names no case, so `get_principal` reads none), and reads the alert through
the queue's own scope and whole-evidence check (`alert_queue.explain`): an alert of a case the reader may
not open, not in their queue there, or any of whose cited nodes, links or transactions they cannot
read now, is refused exactly as a missing alert (ADR-124 Amendment 17's refusal, now at the address;
rule 3). An alert raised in no case has no address until L2.10's dataset alerts.
`Alert.investigation_id` (the triggering event's own investigation,
where the underlying ingest or resolution that raised the alert happened) may be absent — a
resolution-triggered alert carries no single investigation — and the jump still succeeds. The
case a jump makes reads the alert's dataset, else what the alert's case reads, else a dataset of its
own (Amendment 4 decision 3).

### 3.8a Typology rules, their audit, held rows (ADR-109 phase A)

```
GET    /v1/investigations/{id}/rules   the case's typology rules, retired ones included, Viewer
POST   /v1/investigations/{id}/rules   deploy one: a typology, its parameters, its trigger point and budget, Author
POST   /v1/investigations/{id}/rules/{rule_id}/retire   retire one (never deleted), Author
GET    /v1/investigations/{id}/rules/audit   the rule audit, newest first, paged, Author or the unit's admin
GET    /v1/investigations/{id}/held-rows   rows a failing pre-commit rule held, at or below the reader's marking, Editor
POST   /v1/investigations/{id}/held-rows/reject   reject named held rows, with a reason; 409 `composite_read_only` in a case reading a composite (ADR-099 Amendment 15), Author
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/held-rows/release   load named held rows of one load, Author and Loader
POST   /v1/investigations/{id}/rules/sentence/compile   a rule sentence checked against the ontology and compiled to its drawn pattern, Viewer
POST   /v1/investigations/{id}/rules/sentence/read   a drawn pattern read back as the sentence, its other blanks kept, Viewer
POST   /v1/investigations/{id}/rules/preview   "Preview on the last 90 days": run as the caller, raises and writes nothing, Viewer
POST   /v1/investigations/{id}/rules/sentence   deploy a sentence: Editor for "just me", Author for this case, Author and administrator for the deployment
GET    /v1/screening-lists   each screening list's version, entries, last update and failure, read_alert_queue (no refresh counts: its model, ScreeningListsOverview, has no field for them)
GET    /v1/admin/screening-lists   the same, with the latest refreshes and what each changed, re-screened and raised (entries added, changed and delisted — never `removed`, the removal record's name, ADR-124 decision 4), load_screening_lists
POST   /v1/admin/screening-lists   subscribe a list through its connector to a file in the ingest folder, load_screening_lists
POST   /v1/admin/screening-lists/{list_name}/refresh   "Refresh now": apply the list's new version, re-screen against its changed entries, load_screening_lists
PUT    /v1/admin/screening-lists/{list_name}/schedule   set (or stop) the list's refresh schedule, run as the person setting it, load_screening_lists
POST   /v1/investigations/{id}/rules/{rule_id}/approve   a second person approves the change waiting on a whole-deployment rule (never its proposer), Author and administrator
POST   /v1/investigations/{id}/rules/{rule_id}/reject   reject (or, by its proposer, withdraw) a waiting change, with a reason, Author and administrator
POST   /v1/investigations/{id}/rules/{rule_id}/change   a new version of a sentence rule: applied at once, or waiting for approval for a whole-deployment rule, deploy_rules and keep_watches
GET    /v1/investigations/{id}/rules/{rule_id}/versions   every version of a rule, with who proposed and who decided each, Viewer
GET    /v1/investigations/{id}/rules/{rule_id}/runs   a scheduled rule's schedule in words, its next run or why it will not run, its latest runs, Viewer
POST   /v1/investigations/{id}/alert-queue/{alert_id}/approve-close   a second member approves a proposed close of a high-severity alert (never its proposer), Editor; the same 409 `composite_read_only` as the disposition
POST   /v1/investigations/{id}/alert-queue/{alert_id}/send-back   send a proposed close back to its proposer, with a reason, Editor
GET    /v1/investigations/{id}/ingest/recipes/{recipe_id}/checks   the pipeline's "Checks on load" step: the rules it may attach and what was chosen, edit_pipelines, Editor
PUT    /v1/investigations/{id}/ingest/recipes/{recipe_id}/checks   choose the pipeline's checks and what a hit does there; names rules, never writes one, edit_pipelines, Editor
```

**Stage (d): the scheduled trigger, checks on load, and maker–checker (ADR-133 decisions 1, 6 and 7).**
- **A scheduled rule** is a sentence that runs "on a schedule" (`runs: schedule`, with `schedule`: every
  day, or every week on one day, at a whole hour, read in Europe/London) instead of as data loads; a
  whole-deployment rule cannot be scheduled (it is judged within each loading case). Each slot is claimed
  once (Valkey `SET NX`) and judged as the rule's author resolved afresh — never as the system — over the
  last day or week of stored data, through the same gate and alert path a load uses
  (`services/api/rule_schedule.py`, `sentence_rules.run_scheduled_rule`). The author must still sign in,
  hold `deploy_rules` and be an Author of the case (an Editor for "just me"), or the slot is refused in
  words; three refusals in a row stop the schedule, said on the rule, until it is changed. Every slot is
  recorded (`rule_runs`), with its outcome and the alerts it raised.
- **A screening list's refresh schedule** (Amendment 3 item 4) runs the one refresh as the person who set
  it, resolved afresh; without `load_screening_lists` the slot is refused, recorded with the list's
  refreshes in words, and nothing is read (`services/api/list_schedule.py`).
- **Checks on load** (`services/api/load_checks.py`): a pipeline's chosen rules are kept by the recipe
  (`recipe_load_checks`). Once chosen, its loads are judged by the attached case rules, each doing what was
  chosen for a hit (a hold only before commit), and by every whole-deployment rule and every rule just for
  its author, which no pipeline leaves out. Until chosen, every case rule judges the load, as before. The
  choice names rules (`LoadCheck`, extra fields forbidden); writing a rule needs `keep_watches` as well as
  `deploy_rules`, which a data engineer does not hold. **Verify** judges the sample with the pipeline's
  checks, each as its author, over the rows the person verifying may read in full, through a gate whose
  alert store, quarantine and signature set refuse every call: it writes nothing. It reports the would-be
  alerts beside the rejections, and each check a dry run cannot judge (one reading money movements, events
  or stored links) with why.
- **Maker–checker** (`TypologyRuleStore`): a whole-deployment rule is deployed `pending`, and a change to or
  retirement of one waits beside it as a pending version, the rule running as it stood; a second person
  with `deploy_rules`, the administrator's right and the case's Author level approves or rejects it, never
  the person who proposed it (`403 own_change`). Every change to every rule is kept as a `RuleVersion` with
  who proposed and who decided it; a case rule's change applies at once and is kept the same way, and a
  changed rule runs as the person who wrote the new version. Closing a high-severity alert that a second
  person may read is proposed (`closing`) and approved by another member with `triage_alerts`
  (`alert_queue.approve_close`); an alert its owner alone may read closes as before.

**Screening lists as managed sources (ADR-133 stage (c)).** A list is subscribed through a connector,
a Knowledge Adapter with golden files (`packages/knowledge_adapters/screening_lists.py`: OFAC SDN, OFSI
consolidated (a closed list since 28 January 2026, said so on the Lists tab), UN consolidated, EU
consolidated, OpenSanctions, and the FCDO's UK Sanctions List, OFSI's successor (ADR-133 Amendment 6);
rule 8), to one file inside the ingest
folder (a location outside it, resolved first, is refused). A refresh (`services/api/screening_refresh.py`)
admits the list under rule 9 before reading it into the store — synthetic only when every file is one of
the repository's own, known by its SHA-256 (`packages/demo_fixtures/screening_lists/synthetic.sha256`);
anything else is real and needs this device's `real_data_exceptions.yaml` — then applies it as a version
whose diff names the entries added, changed and removed. Every active `kyc_screening` rule then re-screens,
as its own deployer and within its case's datasets, every person and organisation it may read
(`GraphPort.list_nodes`, paged to the end) against the added and changed entries only; a match is the
onboarding finding — a scored `SAME_AS` written `inferred`, and a `kyc_screening` alert, high severity, in
the case's one queue. Each refresh is recorded in words (updated, unchanged, refused, failed); a refused or
failed one leaves the list as it was. A reader of the alert queue sees each list but not the refreshes:
their counts of customers re-screened and alerts raised are taken across every case (rule 7). A list's
own schedule is stage (d)'s (below); the pipeline scheduler runs Studio recipes only.

**Rules written as sentences (ADR-133 stage (b)).** A sentence (`packages/schemas/sentences.py`) is a
set of closed choices from the ontology — never an expression (rule 8) — refused at validation by its
blank, in words (`422 sentence_refused`), when it names a type, property or link type the ontology does
not declare. It compiles to a drawn pattern, saved as its author's, plus the sentence as the rule's
parameters (`SentenceRuleParams`); the generic `POST …/rules` refuses a sentence. It is judged as its
author (`services/api/rule_sentences.py`): subjects and links through `GraphPort`, frequency and amount
conditions through `AnalyticsPort.event_frequency`, both with the access step in the store's query
(rule 3). The preview counts only what the caller may see, refuses with `409 limit_exceeded` past the
working-set limit (rule 2), and writes no alert, rule or pattern. A deployment-wide sentence watches every
case's loads, judged within the loading case's datasets.

**The AML templates (ADR-133 decision 2, stage (c))** are four more typologies with typed parameters
(`packages/schemas/domain.py`; rule 8), judged over a load's `TRANSACTED` movements the deployer may
read (`services/api/aml_rules.py`): `large_cash` (a CASH_IN or CASH_OUT at or over a threshold),
`high_risk_jurisdiction` (a movement to or from an account whose IBAN country code is on the rule's own
list of two-letter codes — the list is data in the rule, the account read as the deployer),
`dormant_reactivated` (an account moving again after N days without a movement) and `velocity_rise`
(an account's last N days at a factor or more of its own daily rate over the days before, counted or
by amount). The last two read the account's past through `AnalyticsPort.account_activity`, the access
step in the store's query, and run after commit only, since the stored past holds the load's own
movements only once committed. Each raises a medium-severity alert in the case's one queue.

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
anything it references: its entities, the transactions and the links it cites, and what it writes
alongside (ADR-146 decision 10: a link marked above its ends counts). In a load's transaction,
what the load itself wrote stands in at its marking as written, anything else the load cannot read
back at the highest marking the recipe could give it; a marking is never guessed. No node is
written, the row still raised and the withholding audited with its reason in words, where
referents with a restricted code belong to different units (no single marking is safe), where a
referent's marking cannot be read in the load, or where a cited link cannot be read when the alert
is raised after the commit (taken back or replaced since it was found; one such link never stops a
sweep). They are also the deployer's §3.8 alerts, and the case team's queue below. Every write that supersedes
a link alerts may cite (a true positive's confirmed `SAME_AS`, a link change, a picture's
replacement or removal) keeps one record in Postgres from before the graph's commit until every
citing alert cites the newest revision, its node is re-marked and renamed, and its working-set
copies are purged, whatever the triage write then does; a record is applied, before every read of
alerts, once the graph's own stored states show its write committed (each link read for its own
type; an id two types hold moves no alert), its re-marks re-run where one never landed, and a
record held open by a writer committing in many transactions is applied only once that writer has
left. A record is dropped only when stale and its write never committed, or closed by its writer
when it records nothing or rolls back before sending its commit. Transactions are read in the
reader's own case.
The queue then checks the new revision for every reader, as it checks any link (ADR-109 Amendments 9
and 10). The rule audit withholds an entry naming a node, link or transaction the reader cannot see
(a firing written before its links were recorded keeps its entry, its words withheld), a pack's
alert item is checked by what its alert cites now, and a row a rule holds gives the rule's name and
typology, never the finding's words.

**The audit read** returns entries of `rule_deployed`, `rule_retired`, `rule_evaluated`,
`rule_fired`, `rule_failed`, `rows_held`, `rows_released`, `rows_rejected` and
`alert_node_withheld`. An entry naming a node, link or transaction the reader cannot see is withheld
whole, before paging, so the total never counts it (one batched read per kind, the queue's check).

**The case team's queue (phase B, ruling 3), since ADR-133 stage (a) the one queue for every kind.**
It holds the case's typology alerts (the case's members') and the hotlist and monitor alerts the
reader owns or that are shared with their team — the owner's organisational unit: a monitor's
always, a hotlist's while its audience is `team`, never a `notify` stub — decided in the query
(`services/api/alerts.py::queue_scope`). Each row carries `kind` (typology, hotlist, monitor),
`severity` (low, medium, high; the stored value, else its kind's default) and `audience` (case,
team or owner). The Reports view's typology figures count the typology alerts alone; ADR-134's
monitoring figures (below) count every kind.

```
GET    /v1/investigations/{id}/alert-queue   the one queue; ?status= active (default: open, claimed and closing), open, claimed, closing, closed or all; ?kind= and ?severity=, each repeatable, Viewer; its rows only to a reader Rules and Monitoring is offered to and to the Reports Viewer, 403 queue_rows_not_offered to any other (ADR-146 Amendment 2 point 3)
GET    /v1/investigations/{id}/alert-queue/counts   the queue as counts alone (AlertQueueCounts: open, claimed, closing), counted as the queue is; for a reader of the queue the place is not offered to, Viewer and read_alert_queue (ADR-146 Amendment 2 point 3)
GET    /v1/investigations/{id}/alert-assignees   the case's Editors and Authors by grant, with names: whom an alert may be given to, Editor (ADR-133 stage (a))
POST   /v1/investigations/{id}/alert-queue/{alert_id}/assign   open or claimed → claimed by the member named; a typology alert only (one shared with a team is claimed), 422 assignment_refused in words otherwise, Editor (ADR-133 stage (a))
GET    /v1/investigations/{id}/alert-queue/{alert_id}   what fired it: nodes, cited links and ALERTED_ON, each transaction, Viewer
POST   /v1/investigations/{id}/alert-queue/{alert_id}/claim   open → claimed by the caller, Editor
POST   /v1/investigations/{id}/alert-queue/{alert_id}/release   claimed (by the caller) → open, Editor
POST   /v1/investigations/{id}/alert-queue/{alert_id}/disposition   → closed, true or false positive with a reason, Editor. In a case reading a composite, a true positive that would confirm anything not wholly the case's analyst layer's is 409 `composite_read_only` ("do this in a case that reads that dataset"), nothing written and the alert left as it was; one raised there, its node and `SAME_AS` in the layer, is closed (ADR-099 Amendment 15)
POST   /v1/investigations/{id}/alert-queue/{alert_id}/canvas   its node, entities and cited links into the working set, Editor
```

Every member of the case reads every rule-raised alert of it, whoever deployed the rule; an alert
any of whose entities, cited links or transactions the reader cannot read is left out of the list
and its count, and opening or acting on it answers 404 (ADR-039's all-or-nothing). Every node, link
and transaction the listed alerts cite is read once per kind, in one batch, as the reader, through each
adapter's own access step (`alerts.read_evidence`; transactions in requests cut from the ids cited), so
the reads are the same whatever is hidden, and an alert is dropped before anything is counted, ordered
or returned (ADR-146 decision 10, gap map G2: until 7 November 2026 the list read nodes alone). Claim,
release, disposition, approve-close, send-back, assign and the canvas make the same check, so each
refuses exactly what the list withholds, writing and auditing nothing. The reader's own alerts
(`GET .../alerts`, the inbox until ADR-146 removes it) make it too: an alert whose evidence is not all
readable comes with no words and no referents (G3). The summary names entities as the reader sees them,
never by id. A move between statuses is one conditional update,
so two members acting at once cannot both win: the loser gets 409 `alert_moved_on`. A true positive
confirms the `Alert` node (asserted, `confirmed_by` the member, rule 5); a false positive leaves it
`inferred`. The canvas route seeds all or, past the cap, nothing (`limit_exceeded`, rule 2).

**Rule 3 in the pack and queue readers (ADR-134 decision 4, 1 November 2026).** Which pack items a
reader gets is decided in the pack store's query (`PackStore.readable_items`, `readable_earlier`,
`readable_version`; the handling check compiled into Postgres by `services/api/handling_sql.py`),
with a second query answering only yes or no that some were left out; a reorder works out the
withheld items' places inside the store. The Conduit then checks each item again — `item_visible`,
which `test_pack_store_query.py` holds to the same answers as the SQL, and against the graph now for
what an entity, assessment or alert item cites. The case queue (`alert_queue.queue`, what the
Reports figures and neighbourhood risk count) reads through the one queue's batched read instead of
each alert's nodes in turn, which had let the work done grow with the alerts the reader may not see
(`test_case_queue_reads.py`).

**Alert facts (ADR-134 decision 3).** Every alert the alert store writes — raised, triaged, closed
by a revert — is kept in the analytics store as it now is (`AnalyticsPort.load_alert_facts`), with
every handling it rests on as read by whoever raised it (`alerts.handlings`); a hotlist's alerts
are kept again when its audience changes, and every alert at each Conduit start. An alert raised
before this was kept carries no handlings and is counted in an alert trend by no one; a failure to
keep one is logged, never fails the alert itself.

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

### 3.8d Neighbourhood risk (ADR-109 phase E)

```
GET    /v1/investigations/{id}/risk/{node_id}   the case's alerts near an entity, decayed by distance, Viewer
```

Computed at each read, never stored (a stored propagated score would be model-derived data, rule 5,
and a leak, rule 3): the entity's neighbourhood out to two hops through `GraphPort.expand` as the
reader (an `Alert` node and its links excluded — risk travels along what entities are to one
another); the case's alerts the reader may see whole (the §3.8a queue's all-or-nothing), less those
older than ninety days and those closed as false positives, each adding 1 to every entity it names;
and `ComputePort.propagate` (½ per hop of the shortest distance, each alerted entity counted once).
A reader who cannot see an alerted neighbour, or a node on the way to one, gets exactly the score
of the graph without it (`tests/ingest/test_risk.py`, written before the read). More than 5,000
entities within two hops: 409 `neighbourhood_too_large`, never a part-score.

### 3.9 Sites

```
POST   /v1/investigations/{id}/sites                          create; multipart, a label plus the image itself
GET    /v1/investigations/{id}/sites/{site_id}                one site's own metadata
GET    /v1/investigations/{id}/sites/{site_id}/image           the site's uploaded image, proxied
PATCH  /v1/investigations/{id}/sites/{site_id}/control-points  set the georeferencing control points
POST   /v1/investigations/{id}/sites/{site_id}/grid            place the grid; its cells become real location entities; 409 `composite_read_only` in a case reading a composite, before the grid is stored (ADR-099 Amendment 15)
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
GET    /v1/admin/link-types                      the proposed relationship types of the administrator's own unit, newest first, `osprey-admin` (ADR-090); promote and reject below refuse one that names a dataset (422 `proposal_refused`: decided on its dataset's Model tab, ADR-090 Amendment 4)
POST   /v1/admin/link-types/{proposal_id}/promote   into the ontology for every case (`{"basis", "reason", "rename_to"?}`): Direct only from now on; merged into a promoted type of its name whose links it fits, or 422 `proposal_refused` (rename it); another unit's is 404 `proposal_not_found`, `osprey-admin` (ADR-090)
POST   /v1/admin/link-types/{proposal_id}/reject    no longer offered; its links stay and keep its name (`{"reason"}`), `osprey-admin` (ADR-090)
POST   /v1/admin/link-types/retire                  a promoted type of the unit no longer offered anywhere (`{"name", "reason"}`); its links stay, `osprey-admin` (ADR-090)
GET    /v1/map/providers                        the deployment's declared map providers, for the layer control
GET    /v1/map/tiles/{provider_id}/{z}/{x}/{y}   the tile proxy for a tier-3/4 provider
GET    /v1/map/local-source/{provider_id}        a tier-1/2 provider's local PMTiles file, over HTTP
POST   /v1/investigations/{id}/map/places       place search over the gazetteer datasets the case reads (`{"query", "limit"?}`), each place with its point and never its gazetteer's identifier; Viewer, `investigate` (ADR-147 Amendment 1)
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
`_retire`, and on the Model tab `_accept`, naming the basis and the draft version written, and
`_decline`) with its reason.

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
GET    /v1/me/rights                                       the signed-in person's rights (ADR-112), so the Glass leaves out what it would be refused; any signed-in person
GET    /v1/models/engines                                  the model engines an analyst may choose for Ask the case and Ask to search (ADR-135): the local engine and each enabled provider with a key, its label, roles and the roles it is the default for; nothing about a key; any signed-in person
GET    /v1/investigations/{id}/models/engines              the same within a case (ADR-136 decision 3): each engine's privacy-contract mark, and an engine the case's datasets may not reach (a dataset at egress none, or contracted and the provider has no contract) listed available: false with the reason in words; Viewer
GET    /v1/admin/people                                    every person in the realm with roles, clearance and unit, no service account (ADR-112); manage_people
PUT    /v1/admin/people/{user_id}/roles                    a person's roles set whole — the built-in roles, custom roles (role:<id>, 422 for one that does not exist), right:<name>, the old role names; anything else 422; 409 in words (ADR-145 Amendment 5): an administration right newly given by someone who does not hold it (beyond_your_rights), a team's role given to a service account (service_account), or a change leaving no enabled person holding manage_people (locks_out_administrators); manage_people
GET    /v1/admin/people/rows                               Admin › People's row (R3, R1): each person's level in each open case of the administrator's own unit, their own or through a team (`through`), and the unit's cases no enabled person is Author of; never another unit's case; manage_people
PUT    /v1/admin/cases/{case_id}/authors/{account_id}   *Name an Author* (R1): a case of the administrator's own unit that no enabled person is Author of, in their own name or through a team, is given one; another unit's case or none 404 alike; 409 has_an_author otherwise; the account held as the case grant route holds it (409 service_account, no_such_team); reads nothing of the case; audited as name_an_author; manage_people
GET    /v1/admin/people/{user_id}/disable-plan             *Disable…* (ADR-145 decision 6, Amendment 5 point 8): everything the person owns today, each with what it is in words (only cases, rules and lists of the administrator's unit are named; never a hotlist's identifier), and `not_yet_listed`, the kinds L2.5b adds once L3.8's ownership route is on main; manage_people
GET    /v1/admin/people/{user_id}/ownership                *Disable…*'s second list (ADR-145 decision 6 and A4; L3.8): the views and boards the person made, their link-type proposals waiting for a decision and their drawn-item watches not ended, read in the SQL in the administrator's own unit (through the item's case; a removed case's left out) and, for a proposal or a watch, at its dataset's highest marking (none set, or no dataset, reads as the scheme's highest); each by kind, the Conduit's id and the case's name, never a view's, board's or type's own name (rule 7); `counts` by kind; `withheld` when they own items of these kinds the administrator may not see, never how many or where, and `person_ownership.refuse_if_withheld` refuses *Transfer and disable* meanwhile (409 withheld_items, provisional); `not_yet_listed` names L3.4's promotions; audited as read_person_ownership; manage_people
GET    /v1/admin/roles                                     the built-in roles and the Super user preset (`gives`: the three roles it gives together), never editable, and every custom role at its current version with how many hold it and its team; manage_people
POST   /v1/admin/roles                                     a custom role, v1 (`{"name", "rights"}`); 409 in words for a name already used (built-in names included), no rights, an unknown right, both rights of a forbidden pair, or a right the giver may not give (ADR-145 decision 7, Amendment 5); audited as create_custom_role; manage_people
PUT    /v1/admin/roles/{role_id}                           its next version, the same refusals and the lock-out (locks_out_administrators); audited as change_custom_role, before and after; manage_people
GET    /v1/admin/roles/{role_id}/versions                  every version, with who changed it and when; manage_people
PUT    /v1/admin/roles/{role_id}/team                      *Make this role a team* (`{"display_name", "mailbox"}`, ADR-112 Amendment 5 decision 3), or its name and mailbox changed; 409 service_account while a service account holds the role; audited as make_team; manage_people
PUT    /v1/admin/teams/{role_id}/lead                      name the lead, or hand it over (`{"lead"}`): an enabled member, never a service account (409 not_a_member, service_account); a cover who becomes lead stops covering; audited before and after as set_team_lead; manage_people
PUT    /v1/admin/teams/{role_id}/cover                     a cover until a last day (`{"cover", "until"}`, inclusive; `cover: null` ends it): an enabled member other than the lead, a day today or later (409 cover_is_lead, cover_date, not_a_member, service_account); audited before and after as set_team_cover; manage_people
POST   /v1/admin/people                                    invite a person (ADR-114 Amendment 5): sign-in by the identity provider's emailed link when the deployment has a mail server and the person an address, else a one-time code in the answer only; clearance and handling codes no higher than the administrator's (403), a name or address already held 409; audited without the code; manage_people
PUT    /v1/admin/people/{user_id}/access                   clearance, unit and receivable handling codes, the person's other attributes kept; same ceiling; manage_people
POST   /v1/admin/people/{user_id}/disable                  *Transfer and disable* (`{"transfers": [{"kind", "id", "to"}]}`, ADR-145 decision 6): every item of the disable plan given to its recipient, in one transaction with an audit entry each (transfer_owned_item), then the account disabled and its sessions ended; 409 in words, nothing changed, while any item has no recipient (untransferred, naming them) or one who cannot take it (recipient_refused: the person, a disabled or unknown account, a service account, a lead who is not a member, someone without the right the item's runs need); never one's own account (409); manage_people
POST   /v1/admin/people/{user_id}/enable                   enabled again; manage_people
POST   /v1/admin/people/{user_id}/reset-sign-in            sessions ended and a new password required at next sign-in — emailed link or one-time code, as for an invitation; manage_people
DELETE /v1/admin/people/{user_id}                          the account deleted from the identity provider (ADR-112 Amendment 3 (a)); audited with who the id was; never one's own, an account OspreyFlow itself uses, nor the last enabled person who can manage people (409, in words); manage_people
GET    /v1/admin/organisation-arrivals                     who the organisation's sign-in refused for a held email in the last seven days and is not yet joined, from Keycloak's record of the refusal (ADR-112 Amendment 3 (b)); empty without an organisation; manage_people
POST   /v1/admin/people/{user_id}/organisation-link        a refused arrival (by the organisation's id for them, which must be on that list) joined to this account with Keycloak's federated identity link; audited; an account already joined, or one OspreyFlow itself uses, refused (409, in words); manage_people
GET    /v1/admin/demo-packs                                each shipped demo pack (ADR-114 Amendment 5, "Show and explain"): what it shows, licence and credit, the command that adds it on the host (PaySim's with `--file`), and the case it is loaded in only when the administrator can open that case; the Conduit runs nothing; audited; administer_system
GET    /v1/admin/dashboards                                the registered dashboard identities (ADR-111 decision 7), each with how fresh its figures are in the reporting mart — last pulled, standing failure and when, cases pulled; aggregates only, never a case id; manage_dashboards
POST   /v1/admin/dashboards                                register one: its secret in this answer only; clearance capped at the registrar's (403); manage_dashboards
DELETE /v1/admin/dashboards/{client_id}                    remove one — only an osprey-dashboard-* client; manage_dashboards
GET    /v1/admin/system                                    each component asked now: graph, Postgres, Valkey, models, identity provider, and whether the Conduit can act for people (its own credential, kept 30 s; ADR-114 Amendment 36); each model engine, its role defaults and whether its key is present (ADR-135), and its privacy-contract mark and reference (ADR-136); administer_system
GET    /v1/admin/datasets                                  every dataset of the deployment, whichever unit holds it, with its unit and its egress — none, contracted or any (ADR-136 decision 2), its kind (source, composite, drawn; never a layer) and promotion policy (ADR-145 decision 8 and Amendment 4 decision 6); names and settings only, no content and no count; administer_system
PUT    /v1/admin/datasets/{dataset_id}/egress              set one dataset's egress (`{"egress": "none"|"contracted"|"any"}`); audited as set_dataset_egress with who, from what and to what; 404 for a dataset that does not exist; administer_system
PUT    /v1/admin/datasets/{dataset_id}/promotion-policy    set its promotion policy (`{"promotion_policy": "author_promotes"|"second_person_reviews"}`, the first the default); audited as set_dataset_promotion_policy, before and after; 404 for a layer or no dataset, 409 `composite_read_only` for a composite; administer_system. L3.4's promotion enforces it
GET    /v1/admin/datasets/{dataset_id}/authors             its Authors, the home case's (ADR-145 Amendment 4 decision 3): account, name and whether each holds review_promotions (ADR-112 Amendment 4), so may approve; has_home_case false until its first Make live; administer_system
PUT    /v1/admin/datasets/{dataset_id}/owners              *Change owner…* (`{"people": [...], "team"?}`, Amendment 4 decision 6): the same refusals as Make live's owner step (409 `owner_needed`: the System setting, a team that does not exist (by its role's id or name), a service account or an account the directory does not hold as a person), 409 for a dataset not yet live; the named people, and the team as `team:<role id>`, become the home case's Authors and every other Author's grant ends, in one transaction with its audit entry (change_dataset_owners, before and after); administer_system
GET    /v1/admin/datasets/{dataset_id}/cases               every linked case, member or not (ADR-143 Amendment 2 decision 2): name, open or removed, whether it is the home case, the composite it reads through, and its layer's items, links and size, counted by the graph store under the administrator's own handling (`GraphPort.dataset_footprints`, numbers only); never a layer's item, label or property; the same fields for an open and a removed case; audited as list_dataset_cases; administer_system
POST   /v1/admin/datasets/{dataset_id}/cases/{investigation_id}/{merge|delete}/dry-run   a removed case's *Merge into the dataset* or *Delete*, run dry (decision 1): its counts and what it would do, in words, and nothing written but the audit entry (dry_run_layer_merge, dry_run_layer_delete); 404 `case_not_linked` for a case not reading it directly, 409 `case_open`, 409 `composite_read_only` to merge into a composite, 403 `not_an_author` to merge for anyone not one of its Authors (naming them); administer_system. The actions themselves are L3.4's
GET    /v1/admin/models                                    Admin › Models (ADR-135 Amendment 2): each engine with its key's state (set, none, lost) and record, never the key; each job's default; the local models, local_only and the sendable codes (read-only); manage_models
GET    /v1/admin/models/history                            the engines' history: who, when, what, which engine, each edited field's old and new value, the outcome; never a key; manage_models
POST   /v1/admin/models/engines                            add an engine (`{"provider": ModelProviderConfig}`), made in the gateway first, then saved; refused in words beside local_only: true; manage_models
PUT    /v1/admin/models/engines/{name}                     edit an engine (its name fixed); its gateway entries made again; manage_models
DELETE /v1/admin/models/engines/{name}                     remove an engine and its key; refused naming the role where it is a default; manage_models
PUT    /v1/admin/models/defaults                           each job's default engine (`{"defaults": {role: engine}}`); manage_models
PUT    /v1/admin/models/engines/{name}/key                 set, rotate or enter again a key (`{"key": "…"}`), write-only: never returned, logged or audited; the body read by the route, so no refusal echoes it; manage_models
DELETE /v1/admin/models/engines/{name}/key                 remove an engine's key; the engine is then offered to no analyst; manage_models
POST   /v1/admin/models/engines/{name}/test                one completion of at most one token; the outcome in fixed words, never the gateway's or provider's; audited; manage_models
PUT    /v1/admin/models/engines/{name}/limits              an engine's limits (`{"limits": EngineLimits}`: requests and tokens a minute, a token budget per day or month, both or neither), applied by the gateway to the engine's own key from the next call; audited, each changed value; manage_models (ADR-135 Amendment 3)
GET    /v1/admin/models/usage                              calls and tokens per engine and job from the gateway's own records over whole UTC days (`start`, `end`; the last 30 by default; at most 366, refused in words beyond); counts only, no figure per person; 502 in fixed words where the gateway cannot give it; manage_models
GET    /v1/admin/maps                                      Admin › Maps (ADR-147): each map provider with its tier, attribution, licence, state and its key's state (set, env, none) and record, never the key; the local basemap, glyphs and builder; the prefetch areas, schedule and next run; manage_geospatial
GET    /v1/admin/maps/history                              the maps' history: who, when, what, which provider, each changed field's old and new value, the outcome; never a key; manage_geospatial
POST   /v1/admin/maps/providers                            add a provider (`{"provider": MapProvider}`): no `env:` reference, an address outside the deployment, a key only on one the Conduit fetches; the maps file replaces osprey.yaml's map: from then on; manage_geospatial
PUT    /v1/admin/maps/providers/{provider_id}              edit a provider (its id fixed, an installer's reference kept); a changed address removes its key; manage_geospatial
DELETE /v1/admin/maps/providers/{provider_id}              remove a provider and its key; refused for the default or one a prefetch area uses; manage_geospatial
PUT    /v1/admin/maps/providers/{provider_id}/key          set or rotate a provider's key (`{"key": "…"}`), write-only, kept in the Conduit's map key file; manage_geospatial
DELETE /v1/admin/maps/providers/{provider_id}/key          remove the key set in Admin; manage_geospatial
PUT    /v1/admin/maps/default                              the provider the map opens on (`{"default": id}`); manage_geospatial
PUT    /v1/admin/maps/areas                                the prefetch areas (`{"areas": [PrefetchArea]}`), named boxes of at most 5,000 tiles, refused in words with the count; manage_geospatial
PUT    /v1/admin/maps/schedule                             how often every area is fetched (`{"schedule": {"every_hours": n | null}}`); manage_geospatial
POST   /v1/admin/maps/prefetch                             fetch every area now: counts per area, a failure in fixed words; manage_geospatial
GET    /v1/admin/settings/dataset-owners                Admin › System's *Dataset owners may be*: people_and_teams (the default), people_only or teams_only (ADR-145 Amendment 4 decision 7); administer_system
PUT    /v1/admin/settings/dataset-owners                sets it; audited as set_dataset_owner_setting, before and after; it governs *Make live*'s owner step
GET    /v1/admin/audit                                  Admin › Audit's stream (ADR-145 decision 10, Amendment 6): by unit in its WHERE clause; a case's entries for the unit's osprey-admin only; words withheld but People and roles to manage_people and Datasets to administer_system; filters kind, who, case, dataset, since, until narrow only; paged with its total; read_audit; audited as read_audit_section
GET    /v1/admin/audit/rules                            (`?case=`) a case's rule audit for the Administrator: read_audit, read_rule_audit and osprey-admin, declared; through readable_rule_audit behind the case rule-audit route's gate, whole before who, since and until narrow it (the exception to ADR-146 Amendment 2 point 3, Amendment 6)
GET    /v1/admin/audit/models                           the engines' history, paged with its true total: read_audit and manage_models, declared (it names people of every unit)
GET    /v1/admin/operations/ageing                      Operations' What ages (ADR-145 decision 9): the ageing rules, N days, and the promotions waiting for review with their age, read as the reader through L3.4's seam; operate_schedules
PUT    /v1/admin/settings/promotion-alert-days          *Alert the reviewers and administrators after N days* (1 to 90, default 3); operate_schedules; audited as set_promotion_alert_days, before and after
GET    /v1/investigations/{id}/reports                     the Reports view's figures (ADR-111): every figure counted as the reader; KYC figures only for a case with the fibo pack, a POLE summary otherwise, both for a mixed case (ADR-126); held rows for Editors and above; 409 limit_exceeded past the bound; Viewer
GET    /v1/investigations/{id}/reports/feed                the same figures for a dashboard, ?format=json|csv; figures only; every read in the export ledger (artefact_kind report_feed); since ADR-134 decision 2 also the monitoring sections `raised_by_rule` (label typology, hotlists or monitors; a typology rule by its typology, never the rule's own analyst-written name), `closed` (by outcome, per week), `time_to_close` (the open-by-age bands) and `hotlist_matches` (per week), every kind of alert the one queue holds for the reader, so a hotlist kept "only me" is in its owner's figures alone; since L2.12 (ADR-146 decision 9, ADR-145 Amendment 4 decision 9) also `open_by_source` (label `‹group›:‹age band›`, the band closed) and the team view `team_unassigned`, `team_older_than_week`, `team_closed` and `team_not_of_interest` (False positive or No further action), each by rule group — not *mine*, the reader's own claims, which the Glass shows and a board pulling the feed as its identity has none of; the week column holds a date or nothing; Viewer
GET    /v1/investigations/{id}/events/holders          whether the case holds events the reader may count and, when none, which cases the reader can open read one of its datasets and do — never a case without a level, never on a hidden event, never a count (ADR-099 Am. 9); investigate, Viewer
GET    /v1/investigations/{id}/trends/options          the event types and properties a trend may use: the core's temporal link types and those of the case's domain packs (ADR-126; by `type_packs`); numeric and categorical properties, never a high-sensitivity one) — ADR-113; and `alert_fields`, what an alert trend may split and filter by (rule — the case's typology rules by name, hotlists and monitors as one each — typology, severity, outcome; ADR-134 decision 3); run_analysis, Viewer
POST   /v1/investigations/{id}/trends/preview          a trend definition counted for the reader now, through AnalyticsPort.trend — or, for `source: alerts` (ADR-134 decision 3: a count, no event type, split and filtered by the alert fields alone), AnalyticsPort.alert_trend, its series named after (a rule by its name, a severity or outcome by its label); marked at the highest classification counted; 422 trend_refused for anything the ontology does not declare, or a type outside the case's domain packs (ADR-126); 409 limit_exceeded with its options past 104 periods or 12 series; run_analysis, Viewer
POST   /v1/investigations/{id}/trends                  save a checked definition to the case, refused for a type outside the case's domain packs (ADR-126); run_analysis, Editor
GET    /v1/investigations/{id}/trends                  the case's saved definitions, each marked `outside_case_domains` when it uses a type outside the case's packs (it still runs); run_analysis, Viewer
GET    /v1/investigations/{id}/trends/{trend}/figures  a saved trend counted for the reader now; another case's trend is 404; run_analysis, Viewer
DELETE /v1/investigations/{id}/trends/{trend}          remove a saved definition; run_analysis, Editor
POST   /v1/investigations/{id}/packs                   create a report pack (ADR-113 decision 3); record_assessment, Editor
GET    /v1/investigations/{id}/packs                   the case's packs with their versions, each publisher and withdrawer named at read (ADR-106, ADR-113 Am. 3); record_assessment, Viewer
GET    /v1/investigations/{id}/packs/{pack}            the draft as the reader may see it: items in order, no positions, a yes or no that some are withheld (never how many or which — ADR-113 Am. 1 and Am. 5); record_assessment, Viewer
POST   /v1/investigations/{id}/packs/{pack}/items      add an item — a saved trend (snapshotted now, as the adder), an assessment, an entity with a caption, a note with its marking, or an alert of the adder's queue in this case (`alert_id`; ADR-134 decision 1: its explanation, the entities it matched, its cited links and transactions, open or closed with its outcome and reason, `match` inferred or confirmed, resting on the handling of every node, link and transaction it cites; 404 for one outside the adder's queue); content read and frozen by the Conduit; record_assessment, Editor
DELETE /v1/investigations/{id}/packs/{pack}/items/{item}         remove one of the reader's own items; record_assessment, Editor
PUT    /v1/investigations/{id}/packs/{pack}/order      the reader's own items in a new order; withheld items keep their places; record_assessment, Editor
POST   /v1/investigations/{id}/packs/{pack}/items/{item}/refresh a trend snapshot counted again now, or an alert read again now (so one added while open can say how it was closed); the earlier one kept in the history; record_assessment, Editor
GET    /v1/investigations/{id}/packs/{pack}/history    earlier snapshots the reader may see, a yes or no that some are withheld, the versions with any withdrawal; record_assessment, Viewer
POST   /v1/investigations/{id}/packs/{pack}/publish    a new immutable version; 409 pack_has_withheld_items (`withheld: true`, no number) while the publisher cannot see an item; record_assessment, Editor
POST   /v1/investigations/{id}/packs/{pack}/versions/{v}/withdraw  withdraw a publication, with a reason, recorded once; record_assessment, Editor
GET    /v1/investigations/{id}/published               each pack's newest publication not withdrawn (Reports → Published), its publisher named (ADR-106); audited; read_reports, Viewer
GET    /v1/investigations/{id}/packs/{pack}/published  that publication as the reader may see it, with a yes or no that some items are withheld; every read audited; read_reports, Viewer
POST   /v1/investigations/{id}/packs/{pack}/export     the newest live publication through the export gate (ADR-113 decision 6, Am. 2): the exporter's access re-checked item by item; a yes or no of withheld items under the manifest policy (true or false under `disclose`, absent under `omit`), never a count and never named; 403 export_refused when nothing is within their handling (nothing recorded); 422 override_required for an item whose originator must be consulted; the approved manifest with its mark, exporter and publisher named (ADR-106), and an export-ledger entry (report_pack); export, Editor
GET    /v1/reports/dashboards                              the Superset boards this person may open: each counted for a dashboard identity whose every figure they could count (unit, clearance, handling codes, a level on each of its cases — ADR-111 Am. 3); read_reports
POST   /v1/reports/dashboards/{slug}/guest-token           a five-minute, read-only Superset guest token for one such board, its rows limited to that identity (row-level rule); otherwise 404; Superset refusing is a 502 in words; read_reports
POST   /v1/investigations/{id}/documents/{document_id}/candidates/accept   the reader's Accept all pending: an enumerated list of candidate ids, never a filter (ADR-108 Q1); Editor
POST   /v1/investigations/{id}/nodes/{node_id}/confirm   inferred/unresolved → asserted, human-attested; Editor, within the case's datasets (ADR-099); 409 `composite_read_only` in a case reading a composite ("do this in a case that reads that dataset"), nothing written (ADR-099 Amendment 15); a node the caller cannot see is 404 as before.
POST   /v1/investigations/{id}/nodes/{node_id}/retract   asserted → inferred, the mirror of confirm; Editor (ADR-099); 409 `composite_read_only` in a case reading a composite ("do this in a case that reads that dataset"), nothing written (ADR-099 Amendment 15); a node the caller cannot see is 404 as before.
POST   /v1/investigations/{id}/nodes/{node_id}/suppression-mark   propose a suppression (R7 step one); `DELETE` withdraws it; Editor (ADR-099 moved both under the case)
DELETE /v1/investigations/{id}/nodes/{node_id}/suppression-mark   withdraw that proposal; Editor (ADR-099)
POST   /v1/investigations/{id}/ingest/recipes/{recipe_id}/run   run a published recipe against a file; a recipe with a pipeline runs through the pipeline runner (services/api/pipeline_run.py over services/ingest/pipeline.py) and answers a PipelineRunReport, every branch, extract and enrich stage its own account; the case's rule gate judges each branch (§3.8a)
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
the recipe's own deduplication key makes a re-run idempotent (§6: "re-runnable"): rows whose key the
case kept are skipped whole, so a re-run writes no node, link occurrence or analytics event again
(ADR-127 decision 5, ADR-109 Amendment 8). A recipe with no deduplication key loads every row, and
its events, every time. A load that
actually creates something submits a post-ingest resolution job per resolvable entity type the
recipe declares — the only route through which an ingest can raise a hotlist or saved-pattern
alert against a live deployment, not fixture data assembled by a test harness.

## 4. The Working-Set Service

The most important component in the Conduit.

**Storage.** One Valkey hash per investigation holding the node and edge set in a compact binary
encoding, plus a capped stream of deltas for reconnect. TTL of 24 hours on idle, with explicit
save promoting the set to durable storage in the Vault.

**Caps.** 50,000 nodes, 250,000 edges. On breach the service does not truncate; it returns a
`limit_exceeded` response naming the three options the Glass offers the analyst (`save_as_view`,
`filter`, `promote_to_batch`; ADR-144 Amendment 2). Encode this as a typed error, not a generic 400, so the client can render the
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
shared team investigation, or one principal's view shared with another, means a later reader's own
`Principal` may be different, and less privileged, than whoever's `expand`/`seed` call originally
populated a given node. `GraphPort`'s own access filtering at the point of fetch is still the only
thing that ever decides what gets *written* to the store — nothing re-derives or second-guesses
that. What the access check re-applies on every read (`ontology.handling.principal_may_read`: handling,
`principal_may_view`, and the case's datasets, `in_case_datasets`, ADR-099 Amendment 1 decision 3 —
the same predicates the adapter's compiled Gremlin is built from) is a *second*, independent check
for whoever is *reading* the store back: a node one principal was entitled to fetch is not
disclosed to a different principal who is not. This applies uniformly to the reconnect snapshot,
replayed missed deltas, a live WebSocket push, and a case view opened — a view cannot show what
its reader cannot see, either. The stream's principal comes from a ticket minted outside any case, so the
stream scopes it to its own case before the first read.

**Why server-side rather than browser-only.** Three reasons that each independently decide it.
An investigation must survive a tab crash. A write to the working set must be atomic. And the resolution
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

  > **A run writes each link once, in one transaction (ADR-058 Amendment 11; ADR-127 Amendment 19).** The engine
  > combines a run's writes per link and writes them through `upsert_edges` inside the run's one graph transaction,
  > so ADR-109's pre-commit rules can judge the load whole and roll it back. ADR-058 D2's bulk-load capability, which
  > commits per chunk and is reverted and re-run on failure (D6), stays the seeds' path (ADR-058 Amendment 10).
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

Analyst decisions are permanent and beat the model, in the case that made them: a `NOT_SAME_AS`
edge is never overridden by a later resolution run for that case, and a later run that would have
merged the pair records the conflict for review. A split written before ADR-143 Amendment 1, in the
source, stops the run's merge for every case, as before. One held only in a case's analyst layer
does not: the source `SAME_AS` goes ahead for every other case, the conflict is recorded on the
split (so in that layer, for that case's review alone), and that case's projection still keeps the
pair apart (ADR-025 Amendment 1).

## 6. Access control and audit

**Principal resolution.** OIDC via Keycloak (Apache-2.0). The session token resolves to a
`Principal` carrying identity, unit, roles, clearance, and the handling codes the principal may
receive, and, for a request whose path names a case, that case's datasets (none otherwise, so it
reads nothing). `get_principal` adds them; every principal a route is given comes through it
(ADR-099 decision 5, Amendment 1 decision 1).

**Rights (ADR-112).** What a principal may *do* is a set of named rights, from the roles in its
token (`schemas/rights.py`: Analyst, Data Engineer, Admin — `osprey-admin` — and Reports Viewer; a
right granted singly as `right:<name>`; the old Studio roles and `compliance` kept to their own rights
for the transition). Every route declares the right it needs in its decorator
(`require_right(Right.X)`), checked before anything else; eighteen routes need none — reference
catalogues, the case list, health, the stream ticket — and `test_route_rights.py`'s table names each
route's right, every right refused both ways (the right without the case level, the level without
the right). A right never confers visibility: what the principal then sees is still the access step
below. `GET /v1/me/rights` tells the Glass which rights a person holds, so it leaves out what it would
only be refused. **Admin routes:** `GET /v1/admin/people`, `PUT /v1/admin/people/{id}/roles`
(manage_people), `GET|POST /v1/admin/dashboards`, `DELETE /v1/admin/dashboards/{client_id}`
(manage_dashboards; a dashboard's clearance capped at its registrar's), `GET /v1/admin/system`
(administer_system) — through the Conduit's own identity-provider account (ADR-112 Amendment 1).

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
force, and a manifest that says only whether material is withheld (ADR-124 decision 9). A disclosed limit (ADR-099 Amendment 1 decision 6):
export of a link checks the link's handling as the client submitted it, not its datasets.

## 7. Caching

Four layers, four different invalidation stories. Keep them separate or you will invalidate
the wrong one.

| Layer | Store | Key | Invalidation |
| --- | --- | --- | --- |
| Working set | Valkey hash | `ws:{investigation_id}` | Explicit, on mutation |
| Working-set access index (ADR-124 Amendment 4) | Valkey hashes and a sorted set beside the working set, maintained by Lua scripts | `ws:{investigation_id}:access_*` | Moved atomically by every write; checked on read and rebuilt from the bodies if damaged; expires with the working set; Valkey must be `noeviction` |
| Readable signatures (ADR-124 Amendment 4) | In process | (case, epoch, signature version, principal_class) | None needed: a write or rebuild changes the version or the epoch, so a stale entry is never asked for |
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
