# Stage 4 and PL4: what the scouts found (20 November 2026)

Read-only scouts for PL4, PL7, PL8, IS2, IS3, IS5 and GG2, on the owner's word of 20 November ("each scout lists what the React screen
does today and flags anything the page would leave out, before a builder starts"). The conductor's digest; the scouts' line numbers are
theirs and are re-read by each builder. **No brief is written for any of them yet**: each waits on the owner's rulings below.
The design rule (RULINGS.md, 20 November): the GOV.UK pages keep the Default theme's behaviour wherever plain TypeScript can rebuild it;
an exception is only for something impossible or meaningless on a server-rendered page, and each is the owner's to agree.

## Facts that hold for every page build

- `apps/pages` holds only the server (PL3, CO3's stream proxy): no `modules/`, no `tree-default/` or `tree-govuk/`, no client-script
  bundle (no esbuild), no `FUNCTIONS.yaml`, no `PARITY_EXCEPTIONS.yaml`, no tree-parity script, no glass-trees tests folder yet.
- **No `/v1` HTTP forwarder** exists in `apps/pages` (ADR-152 decision 5 requires one; CO3's brief lists it "no slice yet"), and **no real
  sign-in** (`pages` answers 503: PL3 and CO2 both excluded it; the realm defines only `osprey-glass`). Pages cannot reach the Conduit's
  REST API or sign anyone in. Neither has an owning slice. They gate I22 and every page build.
- Rule 13: every new keyboard action needs a case in its spec; several React screens have none (Releases, Connect/Profile/Dedup, the
  source page, the Runs grid, external orchestration).
- ADR-152 decision 12 / D10: each rebuilt screen's acceptance scenario is written first, against today's React screen.
- Uploads with scripts off (Connect's file, Sources' Add file, Releases' folder import): the pages service reads the multipart form and
  forwards raw bytes or JSON; the Conduit is unchanged.

## PL4 (cut A to E, agreed) and the pages' dependence on its slices

A wiring and the comparison script; B design tokens to `packages/design` (about 111 importers); C pure leaves and stores (action
registry, working-set store, contrast, conduit request); D Conduit clients and plain logic (ingest, admin and sources clients, the
invite form's plain parts, theme/brand/palette, layout splits); E canvas and graph logic and structural types. Protected files: no
protected line names a moved path; only new wiring lines (Core Makefile `test-js`/`check`, ci.yml lint and test steps) as owner diffs
written from slice A's finished tree. `FUNCTIONS.yaml` has no schema in Amendment 1 (47 rows: 46 from the inventory plus the sign-in
assets row); PARITY_EXCEPTIONS lines are the owner's.

## PL8 (panel frames, ten actions)

Ten actions in `PANEL_FRAME_ACTIONS` (`keyboard/actionRegistry.ts`), one case each in `keyboard/panel-frames.spec.ts`, plus one case
(hidden timeline out of Tab order) with no id. Persistence is `localStorage` only; the three layout stores are plain TypeScript behind
three React hooks. As is with scripts on: all ten. Scripts off: Hide/Show and fold as links or `details`; the drag, sash and Alt-arrow
moves meaningless. Details toggle depends on a canvas; timeline actions on a timeline module. Needs owner: scripts-off exceptions, the
Details toggle without a canvas, Find connections as a fourth panel, whether `frame-scroll.spec.ts` is in scope, both trees carry the
actions, and where the registry/layout logic moves (PL4 as cut moves neither). Does not fit four rounds as one slice: about three
(storage and logic; frames, Hide/Full width/Details/timeline and the spec/08 scenario; order, fold and the three sashes).

## IS2 (Studio Model step)

Today a read-only summary (`ModelTab`, 20 lines) plus the proposals block (accept/decline forms, status tags, withheld row) and
"Define a new link type" in the Inspector. Make-live, drafts, versions and reference lists are Conduit routes with no Glass screen.
Left out as it stands: the Needs-you jump (in-memory state across pages) and typed text kept when the help overlay opens. The port
fits four rounds; the full row as written does not (types per dataset need X7). Open: IS2 as the port only (IS2b types after PL4 C, IS2c
make-live/versions/reference lists), the matching rule's home (the type record or the recipe element), define-a-type's owner, the
Needs-you and help exceptions, the unmounted Admin Proposed types (delete or keep), the copy that replaces "thin until phase 5".

## IS3 (dataset map)

Does not exist in code, spec/08 or any screen; its only definition is ADR-140 Amendment 22, ADR-141 Amendment 2 and the 18 November
Studio revision. A read-only map is buildable on today's routes (the pure `pipelineLayout.ts`); run-order editing and the whole-dataset
load (IS6) need a Conduit change (store the order, start a whole load, read its report, export the job file) and a storage ruling.
Spec gaps: spec/09 has no dataset-map section, spec/08 no scenario. Open: where "runs after" editing lives (IS3 or IS6), table only or
with lines (decision 1 requires a script-off table), the Default reference screen, the milestone's facts, where the order is stored.

## IS5 (Studio built screens)

Nothing is live (no polling, WebSocket or timers beyond one 250 ms debounce), nothing needs drag and drop; every screen but Verify is
forms, tables and lists. Verify draws the ordinary GlassCanvas: it needs the graph module (GG2) or an owner exception (a table of the dry
run). Connect, Profile, Checks, Verify and Publish are mounted from the Pipelines drawer, which IS4 owns. Proposed cut: IS5a frame plus
Releases; IS5b Sources list and source page; IS5c Register wizard and Screening lists; IS5d Runs grid (promotions and drawn merge may
split off); IS5e Publish/schedule and Load rules; IS5f Connect/Profile/Deduplicate; IS5g Verify. Open: Verify's graph, the Airflow DAG
download in Runs against the 18 November "one neutral job file, no generated Airflow job" ruling, who builds the frame and the
Pipelines place (inventory row 484 is neither IS4 nor IS5), uploads with scripts off, the live-text pieces (build them; not exceptions),
the keyboard gaps, Connect's missing rights tip, drawn merge's gate, who owns `AddFiles`, the Needs-you data outside `ingest/`.

## PL7 (pages rendered in every shape; I22)

Nothing renders `pages` today and no `OSPREY_PAGES_*` setting is in any renderer file. About 12 product files, 15 re-pinned tests, 3 to
4 new ones. Cut: PL7a (pages rendered in all four shapes beside the workspace, the default-brand route table, `govuk_tree_state` and the
render-follows-state test, the guide passages) with no visible effect until the forwarder and sign-in exist; PL7b (the complete-state
removal, the cutover release-notes test, glyph and Ingress moves) after the last GOV.UK page and GG2. The guide's section 6a says the
cloud-platform profile installs nothing from the command line, which contradicts Amendment 1; `tests/glass_trees/test_tree_parity.py`
(I6) has no author; no test enforces "no Superset" for GOV.UK. Owner: name the `/v1` forwarding and real sign-in slices; rule on the
canvas, the map and Superset for a GOV.UK deployment without the workspace. The GOV.UK demo is protected: tell the owner before a render
change touches it. The release diff needs PL6's scan script first.

## GG2 (graph canvas module on Sigma 4)

The React canvas is a 4,078-line Sigma-bound file plus about 36 React-free canvas files; the logic ports, the drawing does not (Sigma 4
removes the programs and reducers it uses). About 65 keyboard ids; the Matrix (two ARIA grids) is mandatory as the textual alternative.
Nothing is impossible on a server page; what is left out is left out by scope. **No Sigma 4 measurement exists**, and invariant I12
("the thresholds of spec/02 §5 unchanged") cannot hold literally: the CI gate (`perf.spec.ts`, 30 s first frame, 3,000 ms a frame) is
calibrated for GitHub's software rendering and measures none of hover, 500-node expansion, brush, recompute. Cut: GG2a budget page
(may merge early), GG2b working set and delta client, GG2c canvas actions, GG2d plain case list and Matrix tables (b to d merge only after
WS4). Open: I12's thresholds, whether a CI software gate is acceptable proof, which left-out behaviours are GG2, pointer drag with a
keyboard route, whether "New case" is GG2 or GR1.
