"""Run from the repository root on a clean tree: python3 OspreyFlow_Build/process/lanes/docs/gates/v052-sweep-early-plants.py

v052-sweep-early's red-first run: main's guides first, then each plant at its real call site in the code or in the
guide's own sentence, one at a time; the test that holds it must be red. Each run with a fresh PYTHONPYCACHEPREFIX."""
import os, re, subprocess, sys, tempfile
from pathlib import Path

#: The repository root, from this file's own place: process/lanes/docs/gates/ under OspreyFlow_Build.
WT = str(Path(__file__).resolve().parents[5])
PY = f"{WT}/OspreyFlow_Core/.venv/bin/python"
CACHES = tempfile.mkdtemp(prefix="v052-sweep-early-pycache-")
os.makedirs(CACHES, exist_ok=True)
TESTS = ["tests/test_guide_navigation_words.py", "tests/test_guides_ports_and_search.py", "tests/test_guides_drawn_merge.py",
         "tests/test_guides_v051_gaps.py", "tests/test_user_guide_search_results.py", "tests/test_guides_cloud_platform.py"]
env = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994")
for k in ("OSPREY_LANE", "PYTHONDONTWRITEBYTECODE"): env.pop(k, None)
C, W = "OspreyFlow_Core/", "OspreyFlow_Core/apps/workspace/src/"
AG, UG, DG, ARG = (f"{C}docs/{n}-guide.md" for n in ("administration", "user", "developer", "architecture"))
SITES = "OspreyFlow_Build/marketing_site/sites/build.py"
GUIDES = {AG, UG, DG, ARG}
PLANTS = [
    # navigation
    ("the Reports view relabelled", W + "shell/railLayout.ts", '  dashboards: "Reports",', '  dashboards: "Dashboards",', ["views_the_guides_name_are_where"]),
    ("Connection strength moved into the view switch", W + "shell/railLayout.ts", 'export const VIEW_SWITCH = ["graph", "map", "boards", "dashboards"] as const;\nexport const MORE_VIEWS = ["matrix", "reports", "ownership", "strength"] as const;', 'export const VIEW_SWITCH = ["graph", "map", "boards", "dashboards", "strength"] as const;\nexport const MORE_VIEWS = ["matrix", "reports", "ownership"] as const;', ["views_the_guides_name_are_where"]),
    ("Admin's Operations relabelled", W + "admin/sections.json", '"label": "Operations",', '"label": "Runs",', ["each_admin_section_is_named", "the_layout_is_read"]),
    ("guide: a view put on the rail", AG, "the **Reports** view (the top bar's view switch) draws", "the rail's **Reports** draws", ["no_guide_or_site_puts_a_view_on_the_rail", "views_the_guides_name_are_where"]),
    ("guide: Ask the case again", AG, "question in Ask & Chat, among the engines offered", "question in Ask the case, among the engines offered", ["questions_panel_is_called_by_its_label"]),
    ("guide: Schedules and runs again", AG, "Admin → Operations lists every one.", "Admin → Schedules and runs lists every one.", ["each_admin_section_is_named"]),
    ("guide: Admin › People again", AG, "assigned in *Admin › People and roles*, which keeps", "assigned in *Admin › People*, which keeps", ["each_admin_section_is_named"]),
    ("site: Questions again", SITES, "'<strong>Ask &amp; Chat.</strong> Ask a model about the case;", "'<strong>Questions.</strong> Ask a model about the case;", ["questions_panel_is_called_by_its_label"]),
    # ports and search
    ("a fourth narrow port", C + "packages/ports/media.py", "class MediaStore(Protocol):", "class ExtraPort(Protocol):\n    pass\n\n\nclass MediaStore(Protocol):", ["each_narrow_port_is_a_protocol", "both_guides_name_every_narrow_port"]),
    ("guide: the index feed left out", DG, "Three narrower ports sit beside them:", "Two narrower ports sit beside them:", ["both_guides_name_every_narrow_port"]),
    ("the index feed's reason reworded", C + "packages/ports/index_feed.py", "can reach the unfiltered read", "can call it", ["index_feed_is_said_to_be_unreachable"]),
    ("a PostgreSQL full-text query written", C + "services/api/search.py", "async def search(graph: GraphPort", "_FULL_TEXT = \"SELECT id FROM nodes WHERE to_tsvector(name) @@ to_tsquery(%s)\"\n\n\nasync def search(graph: GraphPort", ["guides_and_the_sites_give_search_as_built"]),
    ("the no-index line reworded", C + "services/api/search_service.py", '"no_index": "Search is limited to exact identifiers: this deployment has no search index.",', '"no_index": "Search is limited: there is no search index.",', ["guides_and_the_sites_give_search_as_built"]),
    ("signing's default none", C + "harness/cloud_platform/settings.py", 'opensearch_signing: Literal["sigv4", "none"] = "sigv4"', 'opensearch_signing: Literal["sigv4", "none"] = "none"', ["opensearch_signing_setting", "section_6a11_asks"]),
    ("the access filter no longer given to the results page's search", C + "services/api/app.py", "        result = await search_service.search_page(\n            body,\n            principal,\n            graph,\n            searcher=index.searcher if index is not None else None,\n            access_filter=index_access_filter(index.scheme, principal)\n            if index is not None\n            else None,\n", "        result = await search_service.search_page(\n            body,\n            principal,\n            graph,\n            searcher=index.searcher if index is not None else None,\n            access_filter=None,\n", ["section_6a11_asks"]),
    ("guide: question 13 without what replaces FGAC", AG, "In its place, OspreyFlow applies each reader's access in its own query to the index:", "OspreyFlow does nothing in its place:", ["section_6a11_asks"]),
    ("a match mode relabelled", W + "search/SearchFilters.tsx", '{ value: "contains", label: "Contains" },', '{ value: "contains", label: "Includes" },', ["names_the_box_s_filters"]),
    ("the box's limited line reworded", W + "search/GlobalSearch.tsx", '"Suggestions are limited just now: only the exact start of a name or identifier matches.";', '"Suggestions are limited.";', ["more_line_and_its_limited_line"]),
    ("the box's two characters made three", W + "search/GlobalSearch.tsx", "export const SUGGEST_MIN_CHARS = 2;", "export const SUGGEST_MIN_CHARS = 3;", ["box_s_two_characters"]),
    # drawn merge and writers
    ("the merge's second step renamed", W + "ingest/runs/drawnMerge.tsx", '"label"}>2. Match</h5>', '"label"}>2. Pair</h5>', ["four_steps_as_the_screen_heads"]),
    ("the merge's matches asserted, not inferred", C + "services/api/drawn_merge.py", "            state=ProvenanceState.INFERRED,", "            state=ProvenanceState.ASSERTED,", ["proposed_never_merged_in_storage"]),
    ("a writer no longer reading in full", C + "services/api/grading.py", "        with sources_in_full():", "        with contextlib.nullcontext():", ["names_every_writer_that_reads_in_full", "writers_check_flags_one_left_out"]),
    ("guide: the merge called coming again", ARG, "A drawn dataset is **merged into another** the same way,", "**Coming:** merging a drawn dataset into another. A drawn dataset is **merged into another** the same way,", ["no_guide_calls_the_merge_coming"]),
    # v0.5.1's gaps
    ("the refresh no longer silent", W + "App.tsx", "silent: () => renewSilently({ silentRequestTimeoutInSeconds: SILENT_AT_LOAD_TIMEOUT_SECONDS }),", "silent: async () => null,", ["refresh_keeps_you_signed_in"]),
    ("sign-out keeping the place", W + "auth/userManager.ts", "  forgetPlace(sessionStorage);\n  return getUserManager().signoutRedirect();", "  return getUserManager().signoutRedirect();", ["refresh_keeps_you_signed_in"]),
    ("the GOV.UK top never compact", W + "brand/BrandFrame.tsx", 'className={claims === 0 ? "brand-chrome brand-chrome--compact" : "brand-chrome"}', 'className="brand-chrome"', ["govuk_top_is_slim"]),
    ("another screen claiming the full frame", W + "admin/Schedules.tsx", "// The Admin area's Operations (formerly Schedules and runs; ADR-141 decision 1)", "import { useFullFooter } from \"../brand/BrandFrame\";\nexport function Claims() { useFullFooter(); return null; }\n// The Admin area's Operations (formerly Schedules and runs; ADR-141 decision 1)", ["govuk_top_is_slim"]),
    ("the cloud-platform profile gone", C + "cli/ospreyflow/deployments.py", 'PROFILE_NAMES = ("local-lite", "small", "cluster", "cloud-platform")', 'PROFILE_NAMES = ("local-lite", "small", "cluster")', ["shared_platform_profile_is_named"]),
    ("guide: §14's row struck", AG, "| A namespace on a shared platform (`cloud-platform`), the poc shape |", "| A namespace elsewhere |", ["section_14_says_how"]),
    # §9 both ways
    ("a refusal the code no longer raises", C + "services/api/entra_people.py", 'raise _refused("There is no organisation account to join.")', 'raise _refused("Joining is not offered.")', ["section_9_quotes_no_entra_refusal_the_code_does_not_raise", "section_9_quotes_each_entra_people_refusal"]),
    ("guide: a stale refusal kept", AG, 'and joining ("There is no organisation account to join.")', 'dashboards ("Dashboard identities are not registered on this deployment yet."), and joining ("There is no organisation account to join.")', ["section_9_quotes_no_entra_refusal_the_code_does_not_raise"]),
    # added after the lane review: an assertion each, at the code that decides it
    ("the runbook granting fine-grained access control", C + "harness/cloud_platform/runbooks.py", '"policy admits that role alone, with no fine-grained access control, so there is no user or "', '"policy admits that role alone, with fine-grained access control and a master user "', ["opensearch_signing_setting", "section_6a11_asks"]),
    ("the runbook's one subnet", C + "harness/cloud_platform/runbooks.py", "needs two private subnets, in two availability zones, ", "needs one private subnet, ", ["section_6a11_asks"]),
    ("the filter's text clause gone", C + "services/api/search_access.py", '                _part(\n                    "text_unit",', '                _part(\n                    "text_any",', ["section_6a11_asks"]),
    ("Whole case's search without the filter", C + "services/api/app.py", "        pending = await pending_of()\n        return await search_service.search_page(\n            body,\n            principal,\n            graph,\n            searcher=index.searcher if index is not None else None,\n            access_filter=index_access_filter(index.scheme, principal)\n", "        pending = await pending_of()\n        return await search_service.search_page(\n            body,\n            principal,\n            graph,\n            searcher=index.searcher if index is not None else None,\n            access_filter=None\n", ["section_6a11_asks"]),
    ("the reduced variant renamed", C + "packages/schemas/deployment.py", 'POSTGRES_FULLTEXT = "postgres-fulltext"', 'POSTGRES_FULLTEXT = "graph-only"', ["guides_and_the_sites_give_search_as_built"]),
    ("the overview's chip back to OpenSearch or PostgreSQL", "OspreyFlow_Build/marketing_site/sites/overview.py", "'OpenSearch, PostgreSQL',", "'OpenSearch or PostgreSQL',", ["guides_and_the_sites_give_search_as_built"]),
    ("Dashboard identities relabelled", W + "admin/sections.json", '"label": "Dashboard identities"', '"label": "Dashboards"', ["each_admin_section_is_named"]),
    ("the more line reworded", W + "search/GlobalSearch.tsx", "`Showing the first ${results.length}; more match. Keep typing to narrow.`", "`Showing ${results.length}; more match.`", ["more_line_and_its_limited_line"]),
    ("the limited line never shown", W + "search/GlobalSearch.tsx", "body.limited === true", "false", ["more_line_and_its_limited_line"]),
    ("the Conduit's limited field renamed", C + "services/api/search.py", "    limited: bool = False", "    is_limited: bool = False", ["more_line_and_its_limited_line"]),
    ("the prefix limit at 60", C + "services/search_index/mapping.py", "PREFIX_MAX_CHARS = 50", "PREFIX_MAX_CHARS = 60", ["box_s_limits_as_the_code_holds"]),
    ("a refused suggestion shown as none found", W + "search/GlobalSearch.tsx", '      if (!response.ok) {\n        settle("unavailable", [], false);', '      if (!response.ok) {\n        settle("none", [], false);', ["box_s_limits_as_the_code_holds"]),
    ("the limited line for every mode", C + "services/api/search_service.py", 'update={"source": "graph", "limited": request.mode == "starts_with"}', 'update={"source": "graph", "limited": True}', ["box_s_limits_as_the_code_holds"]),
    ("on screen asked of the Conduit", W + "search/GlobalSearch.tsx", "    if (using.onScreenOnly) {\n", "    if (false) {\n", ["box_s_limits_as_the_code_holds"]),
    ("the GOV.UK banner not folded", W + "shell/ContextBanner.tsx", 'className="govuk-notification-banner context-banner--govuk context-banner--folded"', 'className="govuk-notification-banner context-banner--govuk"', ["govuk_top_is_slim"]),
    ("a refresh forgetting Rules and Monitoring", W + "auth/refreshPlace.ts", 'const PLACES: readonly Place[] = ["home", "case", "admin", "studio", "rules"];', 'const PLACES: readonly Place[] = ["home", "case", "admin", "studio"];', ["refresh_keeps_you_signed_in"]),
    ("a refresh putting back the drawing board", W + "auth/refreshPlace.ts", 'const RESTORED_GLASS_VIEWS: readonly string[] = ["graph", "map", "matrix", "reports"];', 'const RESTORED_GLASS_VIEWS: readonly string[] = ["graph", "map", "matrix", "reports", "boards"];', ["refresh_keeps_you_signed_in"]),
    ("a place the rights do not open kept", W + "auth/refreshPlace.ts", '  if (chosen && (chosen === "admin" || !caseOpen) && !offered.includes(chosen)) return "home";', '  if (false) return "home";', ["refresh_keeps_you_signed_in"]),
    ("the Conduit with Java on the profile", C + "harness/cloud_platform/profile.yaml", "build_args: {CONDUIT_JAVA: omitted}", "build_args: {}", ["shared_platform_profile_is_named"]),
    ("INSTALL.md without helm upgrade --install", C + "harness/cloud_platform/runbooks.py", '## 5. The deployment\n\n```bash\nhelm upgrade --install "$RELEASE"', '## 5. The deployment\n\n```bash\nhelm install "$RELEASE"', ["section_14_says_how"]),
    ("a merge route without the right", C + "services/api/app.py", '@app.post("/v1/datasets/{dataset_id}/merges/dry-run", dependencies=_MERGES)', '@app.post("/v1/datasets/{dataset_id}/merges/dry-run")', ["who_may_merge"]),
    ("a target of another unit accepted", C + "services/api/drawn_merge.py", "            or target.owning_unit != drawing.owning_unit\n", "", ["who_may_merge"]),
    ("the boards kept as boards", C + "services/api/drawn_merge.py", "            await self.views.merge_boards(record.case_id, record.load_id, drawn)\n", "", ["what_follows_the_merge"]),
    ("the f-string refusal reworded", C + "services/api/entra_people.py", 'come from Entra ID, and are changed there.")', 'are Entra\'s.")', ["section_9_quotes_each_entra_people_refusal", "section_9_quotes_no_entra_refusal"]),
    ("splitViews keeping More views in More views", W + "shell/railLayout.ts", "  return main.length > 0 ? { main, more } : { main: more, more: [] };", "  return { main, more };", ["views_the_guides_name_are_where"]),
    ("the figure's caption back to Questions", SITES, "'questions': ('cap-a2-c8-v6.jpg', 'Ask & Chat: an answer", "'questions': ('cap-a2-c8-v6.jpg', 'Questions: an answer", ["questions_panel_is_called_by_its_label"]),
    ("the basemap script no longer reading in full", C + "scripts/build_local_basemap.py", "    with sources_in_full():", "    with contextlib.nullcontext():", ["names_every_writer_that_reads_in_full", "writers_check_flags_one_left_out"]),
    ("guide: §5.5's 50 characters made 40", UG, "A *Starts with* search is at most 50 characters", "A *Starts with* search is at most 40 characters", ["box_s_limits_as_the_code_holds"]),
    ("guide: §2's refresh on every view", UG, "(on the view it had, where that is the graph, the map, the Matrix or Figures; on any other view, the Glass's first)", "on the view it had", ["refresh_keeps_you_signed_in"]),
    ("guide: question 13's fourth part struck", AG, "and a document's text only for the unit that holds it,", "", ["section_6a11_asks"]),
    ("guide: who may merge cut short", DG, "It is merged only into a dataset of the drawing's unit.", "", ["who_may_merge"]),
]
def run():
    e = dict(env, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(dir=CACHES))
    r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rf", *TESTS], cwd=f"{WT}/OspreyFlow_Build", env=e, capture_output=True, text=True)
    failed = re.findall(r"^FAILED \S+?::(.+?)(?: - .*)?$", r.stdout, re.M)
    summary = next((l for l in r.stdout.splitlines()[::-1] if " passed" in l or " failed" in l or "error" in l), r.stdout[-300:])
    return failed, summary
def apply(path, old, new):
    full = f"{WT}/{path}"; s = open(full).read()
    if path in GUIDES:
        pat = r"\s+".join(map(re.escape, old.split())); n = len(re.findall(pat, s)); assert n == 1, (path, old, n)
        s = re.sub(pat, lambda m: new, s, count=1)
    else:
        assert s.count(old) == 1, (path, old, s.count(old)); s = s.replace(old, new)
    open(full, "w").write(s)
if "--check" in sys.argv:
    bad = []
    for l, p, o, n, w in PLANTS:
        s = open(f"{WT}/{p}").read()
        c = len(re.findall(r"\s+".join(map(re.escape, o.split())), s)) if p in GUIDES else s.count(o)
        if c != 1: bad.append((l, c))
    print(bad or "every plant found once"); sys.exit(bool(bad))
assert subprocess.run(["git", "-C", WT, "status", "--porcelain"], capture_output=True, text=True).stdout == "", "commit first"
print("command: cd OspreyFlow_Build && python -m pytest -q -p no:cacheprovider", " ".join(TESTS))
print("each run: closed ports 59991-59994, no OSPREY_LANE, a fresh PYTHONPYCACHEPREFIX\n")
for path in [AG, UG, DG, ARG, SITES]:
    subprocess.run(["git", "-C", WT, "show", f"main:{path}"], stdout=open(f"{WT}/{path}", "w"), check=True)
failed, summary = run()
subprocess.run(["git", "-C", WT, "checkout", "--", AG, UG, DG, ARG, SITES], check=True)
print(f"== main's four guides and the sites' build.py, before this branch: {summary}\n   red: {', '.join(failed)}\n")
ok = len(failed) > 0
for label, path, old, new, want in PLANTS:
    apply(path, old, new)
    failed, summary = run()
    subprocess.run(["git", "-C", WT, "checkout", "--", path], check=True)
    missing = [w for w in want if not any(w in f for f in failed)]
    ok &= not missing
    gone = [l.strip() for l in old.splitlines() if l.strip() and l not in new.splitlines()] or [old.strip()]
    came = [l.strip() for l in new.splitlines() if l.strip() and l not in old.splitlines()] or ["(removed)"]
    print(f"== {label} [{path.rsplit('/', 1)[-1]}]\n   - " + "\n   - ".join(repr(l[:150]) for l in gone) + "\n   + " + "\n   + ".join(repr(l[:150]) for l in came) + "\n   {summary}\n   red: {', '.join(failed) or 'none'}" + (f"\n   <-- NOT red: {missing}" if missing else "") + "\n")
failed, summary = run()
print(f"== restored: {summary}")
print("each plant red in the tests that hold it:", ok and not failed)
sys.exit(0 if ok and not failed else 1)
