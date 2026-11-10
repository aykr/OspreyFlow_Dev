"""L3.H2's offline plants (rule 15): each check planted out at its own call site, its tests run, the
file restored. Run from the worktree root: `python3 OspreyFlow_Build/process/lanes/case/gates/
L3.H2-plants.py <out>`."""
import os, pathlib, subprocess, sys

CORE = pathlib.Path("OspreyFlow_Core")
T = "../OspreyFlow_Build/tests/services/api/"
REL, CEIL, HOME = T + "test_drawn_watch_release.py", T + "test_promotion_ceiling.py", T + "test_home_cases.py"
PLANTS = [
  # Part 1: a release of held rows runs the drawn watches, as every load does.
  ("the release runs no drawn watch (its dataset never given)",
   "services/api/app.py",
   "        node_ids=touched_node_ids(report), dataset_id=recipe.dataset_id, principal=principal,",
   "        node_ids=touched_node_ids(report), dataset_id=None, principal=principal,",
   REL, "raises_its_owners_alert"),
  ("the release's count never put on its answer",
   "services/api/app.py",
   "    report.drawn_watch_alerts = await run_drawn_watches_best_effort(",
   "    await run_drawn_watches_best_effort(",
   REL, "raises_its_owners_alert"),
  ("every owner's drawn-watch alerts counted for the releaser",
   "services/api/recipe_run.py",
   "            dataset_id, list(node_ids), load_id=load_id, counted_for=principal.id",
   "            dataset_id, list(node_ids), load_id=load_id, counted_for=None",
   REL, "only_of_their_own"),
  ("a failing drawn watch failing the release",
   "services/api/recipe_run.py",
   "    except Exception as exc:  # noqa: BLE001 - as `_evaluate_watches_best_effort`'s: audited",
   "    except DrawnWatchesFailed as exc:",
   REL, "failing_drawn_watch"),
  # The independent review's item 3 (rule 7): a failing watch's detail never under the releaser.
  ("the failing watch's error written under the releaser",
   "services/api/recipe_run.py",
   '"error": DRAWN_WATCH_FAILED},',
   '"error": str(exc)},',
   REL, "said_under_them"),
  ("the failing watch's detail written under the releaser, not its owner",
   "services/api/recipe_run.py",
   "                principal=failure.owner,",
   "                principal=principal,",
   REL, "said_under_them"),
  ("an unresolved owner's identity provider error written under the releaser",
   "services/api/recipe_run.py",
   "                continue\n            await audit.record(\n                principal=failure.owner,",
   "                failure = type(failure)(failure.watch, principal, failure.error)\n            await audit.record(\n                principal=failure.owner,",
   REL, "cannot_be_resolved"),
  # Part 3: one level check; the remove route's 404 and the administrator's path.
  ("a copy of the level check in the drawn watches",
   "services/api/drawn_watches.py",
   "from .dataset_scope import HoldsALevel, case_reads, holds_a_level_in\n",
   "from .dataset_scope import HoldsALevel, case_reads\nfrom .dataset_scope import holds_a_level_in as _one\n\n\n"
   "def holds_a_level_in(investigations):\n    return _one(investigations)\n\n\n",
   REL, "level_check_is_the_apps_own"),
  ("the safety net open to anyone holding remove_case, not the administrator alone",
   "services/api/app.py",
   "    if admin_safety_net and ADMIN_ROLE in principal.roles:",
   "    if admin_safety_net:",
   HOME, "non_member_holding_remove_case"),
  ("no safety net on the remove route",
   "services/api/app.py",
   "    Investigation, Depends(_authorized_at(AccessLevel.AUTHOR, admin_safety_net=True))",
   "    Investigation, Depends(_authorized_at(AccessLevel.AUTHOR, admin_safety_net=False))",
   HOME, "safety_net_removes"),
  ("a home case removed by the administrator",
   "services/api/app.py",
   "    if await datasets.dataset_of_home_case(investigation.id) is not None:\n        raise HTTPException(",
   "    if False:\n        raise HTTPException(",
   HOME, "safety_net_removes"),
  # Part 2: the ceiling on promotions and drawn merges.
  ("an item above the ceiling unnamed at the sheet and the route",
   "services/api/promotions.py",
   "            elif (over := self.above_the_ceiling(marking, ceiling)) is not None:",
   "            elif False and (over := self.above_the_ceiling(marking, ceiling)) is not None:",
   CEIL, "at_the_sheet_and_at_the_route or approval_after_the_ceiling or layer_merge or drawn_merges_item or retyped"),
  ("a picture above the ceiling unnamed",
   "services/api/promotions.py",
   "                elif (over := self.above_the_ceiling(doc_marking, ceiling)) is not None:",
   "                elif False and (over := self.above_the_ceiling(doc_marking, ceiling)) is not None:",
   CEIL, "picture_above_the_ceiling"),
  ("the record stored whatever it would write",
   "services/api/promotions.py",
   "        self.refuse_above_the_ceiling(markings)\n",
   "",
   CEIL, "own_record_is_refused"),
  ("the load committed after the ceiling was lowered",
   "services/api/promotions.py",
   "            self.refuse_above_the_ceiling([record.marking])\n",
   "            pass\n",
   CEIL, "load_itself_is_refused"),
  ("a waiting drawn merge's match unjudged against a lowered ceiling at its re-check",
   "services/api/drawn_merge.py",
   "            if not ceiling.is_the_scheme_s_highest and ceiling.above(stricter.classification):\n                return \"changed\"\n",
   "",
   CEIL, "waiting_drawn_merge"),
  ("a copy's own marking left out of what the record judges",
   "services/api/drawn_merge.py",
   "        markings += [Handling.model_validate_json(c.handling).classification for c in copies]\n",
   "",
   CEIL, "copy_raised_after"),
  ("a drawn merge's match above the ceiling unjudged",
   "services/api/drawn_merge.py",
   "            if over is not None:\n",
   "            if False:\n",
   CEIL, "drawn_merges_match"),
]
env = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", POSTGRES_PASSWORD="throwaway", VALKEY_PORT="59993", CLICKHOUSE_HTTP_PORT="59994")
env.pop("OSPREY_LANE", None)
env.pop("OSPREY_HIGHEST_MARKING", None)
out = []
for words, f, old, new, test, k in PLANTS:
    p = CORE / f
    src = p.read_text()
    assert src.count(old) == 1, (words, src.count(old))
    p.write_text(src.replace(old, new))
    try:
        r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", test, "-q", "-p", "no:cacheprovider", "-k", k], cwd=CORE, env=env, capture_output=True, text=True)
    finally:
        p.write_text(src)
    lines = r.stdout.splitlines()
    tail = [l for l in lines if l.startswith("FAILED") or " passed" in l or " failed" in l]
    tail += [l for l in lines if l.startswith("E  ")][:3]
    out.append(f"## {words}\nplant in {f}; -k {k}; exit {r.returncode}\n" + "\n".join(tail) + "\n")
    print(words, "->", "RED" if r.returncode == 1 else f"NOT RED (exit {r.returncode})")
tests = sorted({t for *_, t, _ in PLANTS})
r = subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", *tests, "-q", "-p", "no:cacheprovider"], cwd=CORE, env=env, capture_output=True, text=True)
out.append("## restored\n" + r.stdout.strip().splitlines()[-1] + "\n")
pathlib.Path(sys.argv[1]).write_text("\n".join(out))
