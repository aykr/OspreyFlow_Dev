"""v052-search's plants as code (rule 15): each one plants a defect at the shape the code under test
really has, runs the test that must catch it, records the test's own failing line, and restores the
file. Each pytest runs with a fresh `PYTHONPYCACHEPREFIX`, so a plant never runs the previous plant's
bytecode (rules' finding of 13 November 2026: a `.pyc` is matched by its source's mtime, to the
second, and size).

Run from the repository root, offline (the closed ports are pinned here):

    OspreyFlow_Core/.venv/bin/python OspreyFlow_Build/process/lanes/studio/v052-search/plants.py

It exits non-zero if any plant does not apply, any planted test passes, or the restored tree fails.
The live reds (the leak test's) are cases of the leak test itself, run with the leased live run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
CORE = ROOT / "OspreyFlow_Core"
BUILD = ROOT / "OspreyFlow_Build"
CLOSED = {
    "ARCADEDB_HTTP_PORT": "59991",
    "POSTGRES_PORT": "59992",
    "VALKEY_PORT": "59993",
    "CLICKHOUSE_HTTP_PORT": "59994",
    "OPENSEARCH_PORT": "59999",
}

Q = "services/api/search_index_query.py"
A = "services/api/search_access.py"
S = "services/api/search_service.py"
APP = "services/api/app.py"
T_Q = "tests/services/api/test_search_index_query.py"
T_A = "tests/services/api/test_search_access.py"
T_S = "tests/services/api/test_search_service.py"
T_R = "tests/services/api/test_search_route_index.py"


@dataclass(frozen=True)
class Plant:
    name: str
    file: str  # under OspreyFlow_Core
    old: str
    new: str
    test: str  # a pytest node id under OspreyFlow_Build, or "vitest:<file>"


PLANTS = [
    # --- the query builder -------------------------------------------------------------------------
    Plant(
        "the access filter moved to post_filter (limits hits, not counts)",
        Q,
        '"bool": {\n                "filter": filters,',
        '"bool": {\n                "filter": filters[1:],',
        f"{T_Q}::test_the_access_filter_limits_hits_and_counts_alike",
    ),
    Plant(
        "dis_max sums the bands",
        Q,
        '"must": [{"dis_max": {"queries": bands, "tie_breaker": 0}}]',
        '"must": [{"dis_max": {"queries": bands, "tie_breaker": 1}}]',
        f"{T_Q}::test_every_dis_max_takes_the_best_band_alone",
    ),
    Plant(
        "the typo band asked as a fuzzy query",
        Q,
        '{"match": {"names.tri": {"query": text, "minimum_should_match": TYPO_SHARE}}}',
        '{"match": {"names.words": {"query": text, "fuzziness": "AUTO"}}}',
        f"{T_Q}::test_no_clause_expands_against_the_word_list",
    ),
    Plant(
        "a long query cut, not refused",
        Q,
        "    if len(text) > MAX_QUERY_CHARS:",
        "    text = text[:MAX_QUERY_CHARS]\n    if False:",
        f"{T_Q}::test_a_query_over_the_limit_is_refused_not_cut",
    ),
    Plant(
        "a body built with no access filter",
        Q,
        "    if not access_filter:",
        "    if False:",
        f"{T_Q}::test_a_body_cannot_be_built_without_an_access_filter",
    ),
    Plant(
        "the canonical form of a number not asked",
        Q,
        "    if canonical is not None and canonical != text:",
        "    if False:",
        f"{T_Q}::test_the_identifier_band_asks_the_canonical_form_too",
    ),
    Plant(
        "by-type counts over text documents too",
        Q,
        '"filter": {"term": {"kind": "node"}},\n                "aggs": {',
        '"filter": {"match_all": {}},\n                "aggs": {',
        f"{T_Q}::test_the_by_type_counts_ask_every_type_the_ontology_has",
    ),
    Plant(
        "the group in the query, so other groups' counts shrink",
        Q,
        '        body["post_filter"] = {\n            "bool": {"filter": [{"term": {"kind": "node"}}, {"term": {"type": group}}]}\n        }',
        '        body["query"]["bool"]["filter"].append({"term": {"type": group}})',
        f"{T_Q}::test_a_group_narrows_the_list_and_leaves_every_groups_count_whole",
    ),
    Plant(
        "a suggestion longer than the stored prefixes asked",
        Q,
        "    if len(prefix) > PREFIX_MAX_CHARS:",
        "    if False:",
        f"{T_Q}::test_a_suggestion_longer_than_the_stored_prefixes_is_refused_not_cut",
    ),
    Plant(
        "highlight marks as control characters, which OpenSearch's trim cuts",
        Q,
        'HIGHLIGHT_OPEN = "\\ue000"',
        'HIGHLIGHT_OPEN = "\\x02"',
        f"{T_Q}::test_the_marks_survive_opensearch_trimming_a_fragments_edges",
    ),
    Plant(
        "the dataset counts asked of every dataset",
        Q,
        '                    "include": sorted(case_datasets),\n',
        "",
        f"{T_Q}::test_the_dataset_and_date_filters_are_offered_from_the_same_query",
    ),
    Plant(
        "the pending nodes not left out",
        Q,
        '    return {"must_not": [{"terms": {"node_id": sorted(set(pending))}}]} if pending else {}',
        "    return {}",
        f"{T_Q}::test_pending_nodes_are_left_out_of_a_search_and_a_suggestion",
    ),
    Plant(
        "a suggestion's types not filtered",
        Q,
        '                    *([{"terms": {"type": list(types)}}] if types else []),\n',
        "",
        f"{T_Q}::test_a_suggestion_can_be_limited_to_types",
    ),
    Plant(
        "a score outside the bands made the caller's mistake (422)",
        Q,
        "class ScoreOutsideBands(RuntimeError):",
        "class ScoreOutsideBands(ValueError):",
        f"{T_Q}::test_a_score_between_bands_is_a_defect_not_a_guess",
    ),
    # --- the access filter ---------------------------------------------------------------------------
    Plant(
        "every classification allowed",
        A,
        "        allowed = scheme.classification[: rank + 1]",
        "        allowed = list(scheme.classification)",
        f"{T_A}::test_the_filter_agrees_with_the_conduits_rule_everywhere",
    ),
    Plant(
        "a restricted code's unit scope dropped",
        A,
        '                                                {"term": {"owning_unit": unit}},\n',
        '                                                {"exists": {"field": "owning_unit"}},\n',
        f"{T_A}::test_the_filter_agrees_with_the_conduits_rule_everywhere",
    ),
    Plant(
        "the background principal searched",
        A,
        "    if principal.datasets is None:",
        "    if False:",
        f"{T_A}::test_a_principal_with_no_case_limit_is_refused",
    ),
    # --- the service -------------------------------------------------------------------------------
    Plant(
        "the index asked with no access filter",
        S,
        "    elif searcher is not None and access_filter is not None:",
        "    elif searcher is not None:",
        f"{T_S}::test_with_no_access_filter_the_index_is_never_asked",
    ),
    Plant(
        "every failure hidden behind the fallback",
        S,
        '        except IndexUnavailable:\n            why = "unreachable"',
        '        except Exception:\n            why = "unreachable"',
        f"{T_S}::test_an_index_that_answers_badly_is_raised",
    ),
    Plant(
        "counts shown as exact though the graph withheld a hit",
        S,
        "        counts_exact=found.counts_exact and shown == len(found.hits) and not pending,",
        "        counts_exact=found.counts_exact and not pending,",
        f"{T_S}::test_a_hit_the_graph_does_not_return_is_dropped_and_counts_are_not_exact",
    ),
    Plant(
        "a dataset outside the case offered",
        S,
        "                for d, name in case_datasets.items()\n                if found.dataset_counts.get(d)",
        "                for d, name in {**case_datasets, **{k: k for k in found.dataset_counts}}.items()\n                if found.dataset_counts.get(d)",
        f"{T_S}::test_a_dataset_outside_the_case_is_never_offered",
    ),
    Plant(
        "a filter on a dataset outside the case passed on",
        S,
        "    if outside:",
        "    if False:",
        f"{T_S}::test_a_filter_on_a_dataset_outside_the_case_is_refused",
    ),
    Plant(
        "the fallback not saying it is limited",
        S,
        "        limited=True,\n        limited_reason=reason,",
        "        limited=False,\n        limited_reason=None,",
        f"{T_S}::test_with_no_index_the_fallback_says_there_is_none",
    ),
    Plant(
        "the fallback's depth not reported as more",
        S,
        "        more=len(found) > start + size or reached,",
        "        more=len(found) > start + size,",
        f"{T_S}::test_the_fallback_says_more_at_its_depth",
    ),
    Plant(
        "the fallback's group applied after paging",
        S,
        "    if request.group is not None:\n        found = [n for n in found if n.type == request.group]\n    page = found[start : start + size]",
        "    page = found[start : start + size]\n    if request.group is not None:\n        page = [n for n in page if n.type == request.group]",
        f"{T_S}::test_the_fallback_narrows_by_group_and_dataset_before_it_pages",
    ),
    Plant(
        "a value list compared as a whole (the TypeError the review found)",
        S,
        "        if any(meets(v) for v in _strings(value)):",
        "        if meets(value):",
        f"{T_S}::test_a_list_valued_property_never_breaks_a_search",
    ),
    Plant(
        "no merge at all",
        S,
        "    cluster = {n.id: n.resolution.cluster_id or n.id for n in shown}",
        "    cluster = {n.id: n.id for n in shown}",
        f"{T_S}::test_visible_hits_the_case_reads_as_one_are_one_result",
    ),
    Plant(
        "a TLS failure hidden behind the fallback",
        S,
        '        except opensearchpy.SSLError:\n            log.exception("the search index\'s TLS failed")\n            raise\n',
        "",
        f"{T_S}::test_any_other_failure_is_raised_not_hidden",
    ),
    Plant(
        "a pending set not known to be whole relied on",
        S,
        "    if searcher is not None and access_filter is not None and not pending_complete:",
        "    if False:",
        f"{T_S}::test_a_pending_set_not_known_to_be_whole_and_the_graph_answers",
    ),
    Plant(
        "counts shown as exact while nodes are pending",
        S,
        "        counts_exact=found.counts_exact and shown == len(found.hits) and not pending,",
        "        counts_exact=found.counts_exact and shown == len(found.hits),",
        f"{T_S}::test_nodes_the_index_has_not_caught_up_with_are_left_out_and_counts_not_exact",
    ),
    Plant(
        "a case-sensitive suggestion narrowed on every property",
        S,
        "        if allowed is None or key in allowed",
        "        if True",
        f"{T_S}::test_a_case_sensitive_suggestion_looks_only_at_identifiers_and_names",
    ),
    Plant(
        "a graph-answered suggestion not saying it is limited",
        S,
        'update={"source": "graph", "limited": request.mode == "starts_with"}',
        'update={"source": "graph", "limited": False}',
        f"{T_S}::test_a_suggestion_the_graph_answers_says_it_is_limited",
    ),
    Plant(
        "a group labelled with its type's name",
        S,
        '    if type_name == "Person":\n        return "People"',
        '    if type_name == "Person":\n        return "Person"',
        f"{T_S}::test_group_labels_and_the_matched_fields_display_name",
    ),
    # --- the routes --------------------------------------------------------------------------------
    Plant(
        "a refused suggestion left as a 500",
        APP,
        '    except ValueError as exc:\n        raise HTTPException(status_code=422, detail=str(exc)) from exc\n    await audit.record(\n        principal=principal,\n        action="suggest",',
        '    except KeyError as exc:\n        raise HTTPException(status_code=422, detail=str(exc)) from exc\n    await audit.record(\n        principal=principal,\n        action="suggest",',
        f"{T_R}::test_a_suggestion_the_index_cannot_ask_is_refused_with_422",
    ),
    Plant(
        "the pending nodes not passed to the search",
        APP,
        '            pending=sorted(pending.ids),\n            pending_complete=pending.complete,\n            schema=index.schema if index is not None else None,\n        )\n    except ValueError as exc:\n        raise HTTPException(status_code=422, detail=str(exc)) from exc\n    await audit.record(\n        principal=principal,\n        action="search",',
        '            schema=index.schema if index is not None else None,\n        )\n    except ValueError as exc:\n        raise HTTPException(status_code=422, detail=str(exc)) from exc\n    await audit.record(\n        principal=principal,\n        action="search",',
        f"{T_R}::test_the_pending_ids_reach_only_the_querys_must_not",
    ),
    Plant(
        "the case's threshold not read",
        APP,
        "            tau=await _search_tau(working_set, investigation.id),",
        "            tau=None,",
        f"{T_R}::test_the_cases_threshold_merges_through_the_working_set",
    ),
    Plant(
        "the audit counting merged results, not the records sent",
        APP,
        '        result_cardinality=len(result.nodes),\n    )\n    return result\n\n\n@app.post(\n    "/v1/investigations/{investigation_id}/suggest",',
        '        result_cardinality=len(result.results),\n    )\n    return result\n\n\n@app.post(\n    "/v1/investigations/{investigation_id}/suggest",',
        f"{T_R}::test_the_cases_threshold_merges_through_the_working_set",
    ),
    # --- the Glass ---------------------------------------------------------------------------------
    Plant(
        "the bar ignores the reply's `limited`",
        "apps/workspace/src/search/GlobalSearch.tsx",
        "body.limited === true",
        "false",
        "vitest:apps/workspace/src/search/GlobalSearch.test.tsx",
    ),
]


def run(test: str) -> tuple[bool, str]:
    env = {**os.environ, **CLOSED, "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(prefix="plant-pyc-")}
    if test.startswith("vitest:"):
        cmd = ["npx", "vitest", "run", test.removeprefix("vitest:")]
        cwd = CORE
    else:
        cmd = [str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", test]
        cwd = BUILD
    done = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    lines = (done.stdout + done.stderr).splitlines()
    asserting = [
        ln.strip()
        for ln in lines
        if ln.startswith(">") or ln.lstrip().startswith(("E ", "AssertionError", "×", "FAIL"))
    ]
    summary = [ln for ln in lines if " passed" in ln or " failed" in ln or "Tests " in ln]
    return done.returncode == 0, "\n".join(asserting[:4] + summary[-1:])


def main() -> int:
    bad = 0
    for i, plant in enumerate(PLANTS, 1):
        path = CORE / plant.file
        original = path.read_text()
        if original.count(plant.old) != 1:
            print(f"P{i} NOT APPLIED ({original.count(plant.old)} matches): {plant.name}")
            bad += 1
            continue
        path.write_text(original.replace(plant.old, plant.new))
        try:
            passed, why = run(plant.test)
        finally:
            path.write_text(original)
        print(
            f"P{i} {'GREEN (BAD)' if passed else 'red'}: {plant.name}\n  {plant.test}\n  "
            + why.replace("\n", "\n  ")
        )
        bad += passed
    files = sorted({p.test.split("::")[0] for p in PLANTS if not p.test.startswith("vitest:")})
    env = {**os.environ, **CLOSED, "PYTHONPYCACHEPREFIX": tempfile.mkdtemp(prefix="plant-pyc-")}
    done = subprocess.run(
        [str(CORE / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider", *files],
        cwd=BUILD,
        env=env,
        capture_output=True,
        text=True,
    )
    print(
        "restored:",
        [ln for ln in done.stdout.splitlines() if " passed" in ln or " failed" in ln][-1:],
    )
    return 1 if bad or done.returncode else 0


if __name__ == "__main__":
    sys.exit(main())
