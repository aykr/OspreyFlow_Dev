"""rules-b v052D(iii)'s server plants (rule 15): each protection in `questions.py` removed at its
real call site, and the test that names it run with a fresh bytecode cache; then the file restored
and the whole file run as a control. Run from OspreyFlow_Core with the closed offline ports."""

import os
import subprocess
import tempfile

P = "services/api/questions.py"
T = "../OspreyFlow_Build/tests/services/api/test_questions_whole_case.py"
PLANTS = [
    ("the question cut to fit, not refused",
     "        if len(words) > MAX_QUERY_CHARS:\n            raise QuestionTooLongToSearchError(len(words))\n",
     "        words = words[:MAX_QUERY_CHARS]\n",
     "test_a_question_longer_than_the_search_takes_is_refused_never_cut"),
    ("one default page, not 50",
     "SearchPageRequest(query=words, page=1, page_size=WHOLE_CASE_PAGE)",
     "SearchPageRequest(query=words, page=1)",
     "test_the_questions_own_words_are_the_query"),
    ("no question searched with an empty query",
     "        if not words:\n            raise NothingToReadError(_NO_QUESTION_YET)\n",
     "        words = words or 'a'\n",
     "test_will_read_with_no_question_yet_says_to_type_it"),
    ("nothing found answered anyway",
     "        if not read:\n            raise NothingToReadError(_NO_MATCHES)\n",
     "",
     "test_nothing_found_is_refused_in_words"),
    ("the view not applied",
     "            results = [r for r in results if r.node_ids and set(r.node_ids) <= in_view]\n",
     "            pass\n",
     "test_in_a_view_only_what_the_view_holds_is_read"),
    ("a Document on the canvas read by its passage",
     "                if view is not None:\n                    read += 1",
     "                view = None\n                if view is not None:\n                    read += 1",
     "test_a_document_on_the_canvas_is_read_whole"),
    ("the passage not read",
     "        return f'{said}\\n  Passage: \"{self.passage}\"' if self.passage else said",
     "        return said",
     "test_a_document_off_the_canvas_is_read_as_its_passage_never_whole"),
    ("an invented [S-n] kept",
     "            lambda m: m.group(0) if int(m.group(2)) in sources else \"\", answer",
     "            lambda m: m.group(0), answer",
     "test_a_cited_source_stands_for_its_records_and_an_invented_one_is_dropped"),
    ("an invented [S-n] not counted",
     "+ len(asked_s) - len(search_citations)",
     "",
     "test_a_cited_source_stands_for_its_records_and_an_invented_one_is_dropped"),
    ("the search's fallback words dropped",
     "                limited_reason=found.limited_reason,",
     "                limited_reason=None,",
     "test_the_searchs_fallback_and_limits_reach_the_read_summary"),
    ("will read not given the question",
     "            read_from=read_from,\n            question=question,\n            case_search=case_search,\n        )\n        routed",
     "            read_from=read_from,\n            question=None,\n            case_search=case_search,\n        )\n        routed",
     "test_will_read_counts_what_asking_reads_and_sends_nothing"),
    ("the sources not kept for a later reader",
     "            search_node_ids=list(dict.fromkeys(i for s in material.sources for i in s.node_ids)),",
     "            search_node_ids=[],",
     "test_an_answer_is_shown_only_to_a_reader_who_may_see_every_source"),
    ("a later reader not checked against the sources",
     "            if entry.search_node_ids and len(",
     "            if False and len(",
     "test_an_answer_is_shown_only_to_a_reader_who_may_see_every_source"),
]
ENV = dict(os.environ, ARCADEDB_HTTP_PORT="59991", POSTGRES_PORT="59992", VALKEY_PORT="59993",
           CLICKHOUSE_HTTP_PORT="59994")
ENV.pop("OSPREY_LANE", None)


def run(target: str) -> subprocess.CompletedProcess[str]:
    env = dict(ENV, PYTHONPYCACHEPREFIX=tempfile.mkdtemp(prefix="plant-pyc-"))
    return subprocess.run([".venv/bin/pytest", "-c", "../OspreyFlow_Build/pytest.ini", "-q", "-p",
                           "no:cacheprovider", target], capture_output=True, text=True, env=env)


original = open(P).read()
try:
    for name, before, after, test in PLANTS:
        assert original.count(before) == 1, (name, original.count(before))
        open(P, "w").write(original.replace(before, after))
        r = run(f"{T}::{test}")
        print(f"{'RED  ' if r.returncode else 'GREEN?!'} | {name} | {test}")
        for line in [l for l in r.stdout.splitlines() if l.startswith("E ")][:2]:
            print("    " + line[:200])
    open(P, "w").write(original)
    print("CONTROL (unplanted, fresh cache):", run(T).stdout.strip().splitlines()[-1])
finally:
    open(P, "w").write(original)
