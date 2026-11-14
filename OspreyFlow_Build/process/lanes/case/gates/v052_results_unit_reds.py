"""v052-results (ADR-145 Amendment 15 Part A, the search results page): the jsdom tests' reds, each a plant at the real call site.

Run from the worktree root on a clean tree at the commit under test:
    python3 OspreyFlow_Build/process/lanes/case/gates/v052_results_unit_reds.py > OspreyFlow_Build/process/lanes/case/gates/v052-results-unit-reds.log

Each plant replaces one exact string in one file (refused if the string is not there exactly once), runs the
named vitest file filtered to the named test, records the result, and restores the file with
`git checkout -- <file>`. A plant whose test stays green is a failure of this record.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
WS = ROOT / "OspreyFlow_Core/apps/workspace"

PLANTS = [
    ("the request without page_size (today's limit alone)",
     'src/search/SearchResults.tsx', 'body: JSON.stringify({ query, group, filters: requestFilters(filters), page, page_size: RESULTS_PAGE_SIZE }),', 'body: JSON.stringify({ query, group, filters: requestFilters(filters), page }),',
     'src/search/SearchResults.test.tsx', "asks the case's search in the frozen shape"),
    ('the heading not focused on opening',
     'src/search/SearchResults.tsx', '  useEffect(() => {\n    heading.current?.focus();\n  }, [query]);', '  useEffect(() => undefined, [query]);',
     'src/search/SearchResults.test.tsx', 'the heading takes focus'),
    ('uncertain counts not said',
     'src/search/SearchResults.tsx', '${counts.counts_exact ? "" : " (counts may be incomplete)"}', '',
     'src/search/SearchResults.test.tsx', 'counts that may be incomplete say so'),
    ("All counted from the page, not the Conduit's total (rule 7)",
     'src/search/SearchResults.tsx', '[{ key: null, label: "All", count: counts.total }, ...counts.groups]', '[{ key: null, label: "All", count: shown?.results.length ?? 0 }, ...counts.groups]',
     'src/search/SearchResults.test.tsx', "the groups are All then the Conduit's"),
    ("a chosen group's total the whole search's (the first review's)",
     'src/search/SearchResults.tsx', 'records(groupCount ?? counts.total)', 'records(counts.total)',
     'src/search/SearchResults.test.tsx', 'with a group chosen, the total and its announcement'),
    ("the counts kept from the first answer while a group is chosen (the first review's)",
     'src/search/SearchResults.tsx', '      setLast(body);\n', '      setLast((was) => (group === null || was === null ? body : { ...body, groups: was.groups, filters: was.filters, total: was.total }));\n',
     'src/search/SearchResults.test.tsx', 'a filter set while a group is chosen'),
    ('a result named by its id, not nodeLabel',
     'src/search/SearchResults.tsx', 'const name = first ? nodeLabel(first) : result.type;', 'const name = first ? String(first.id) : result.type;',
     'src/search/SearchResults.test.tsx', 'each result is named as the canvas names it'),
    ("the passage's match not marked",
     'src/search/SearchResults.tsx', 'part.match ? <mark key={i}>{part.text}</mark> : <span key={i}>{part.text}</span>', '<span key={i}>{part.text}</span>',
     'src/search/SearchResults.test.tsx', 'a document shows its passage with the match marked'),
    ('Open offered for every result',
     'src/search/SearchResults.tsx', '{result.is_document && first && (', '{first && (',
     'src/search/SearchResults.test.tsx', 'a document shows its passage with the match marked'),
    ('Show on graph with the first record alone',
     'src/search/SearchResults.tsx', 'onClick={() => onShow(nodes)}', 'onClick={() => onShow(nodes.slice(0, 1))}',
     'src/search/SearchResults.test.tsx', 'Show on graph hands over every record'),
    ('a record the answer does not hold dropped in silence',
     'src/search/SearchResults.tsx', '      {unread > 0 && (', '      {false && (',
     'src/search/SearchResults.test.tsx', 'a record a result names but the answer does not hold'),
    ('the Ask line without the words',
     'src/search/SearchResults.tsx', 'onClick={() => onAsk(query)}', 'onClick={() => onAsk("")}',
     'src/search/SearchResults.test.tsx', 'the Ask line hands the words to Ask & Chat'),
    ('the Ask line drawn with nothing to hand to',
     'src/search/SearchResults.tsx', '  const askLine = onAsk && (', '  const askLine = (onAsk ?? (() => undefined)) && (',
     'src/search/SearchResults.test.tsx', 'with no Ask & Chat to hand the words to'),
    ('Back doing nothing',
     'src/search/SearchResults.tsx', 'onClick={onBack}>', 'onClick={() => undefined}>',
     'src/search/SearchResults.test.tsx', 'Back to the view the person left'),
    ('the date filter not sent',
     'src/search/SearchResults.tsx', '    ...(filters.dateFrom ? { date_from: filters.dateFrom } : {}),\n', '',
     'src/search/SearchResults.test.tsx', 'a dataset and a date range filter the search'),
    ('Next page asking the same page',
     'src/search/SearchResults.tsx', 'onClick={() => onTurn(page + 1)}', 'onClick={() => onTurn(page)}',
     'src/search/SearchResults.test.tsx', 'more results are a page away'),
    ("focus left on the pager's button (the first review's)",
     'src/search/SearchResults.tsx', '    focusHeadingOnAnswer.current = true;\n    setPage(next);', '    setPage(next);',
     'src/search/SearchResults.test.tsx', 'after Next page or Clear filters, focus goes to the heading'),
    ('no results saying nothing',
     'src/search/SearchResults.tsx', 'shown && shown.results.length === 0 && shown.page === 1 && (', 'false && (',
     'src/search/SearchResults.test.tsx', 'no results says so'),
    ("the fallback's line not shown",
     'src/search/SearchResults.tsx', '      {shown?.limited && (', '      {false && (',
     'src/search/SearchResults.test.tsx', 'on the fallback one line says the results are limited'),
    ("no line on the fallback without a reason (the first review's)",
     'src/search/SearchResults.tsx', '{shown.limited_reason ?? "Results are limited: the search index is not in use."}', '{shown.limited_reason}',
     'src/search/SearchResults.test.tsx', 'on the fallback with no reason given'),
    ('a dataset the fallback cannot count shown as 0',
     'src/search/SearchResults.tsx', '{d.count === null ? d.name : `${d.name} (${d.count.toLocaleString("en-GB")})`}', '{`${d.name} (${d.count ?? 0})`}',
     'src/search/SearchResults.test.tsx', 'a dataset the fallback cannot count'),
    ("a refusal in the Glass's words, not the Conduit's",
     'src/search/SearchResults.tsx', 'setAnswer({ kind: "refused", words: detail ?? `The search could not be done (${response.status}).` });', 'setAnswer({ kind: "refused", words: `The search could not be done (${response.status}).` });',
     'src/search/SearchResults.test.tsx', "a refusal is said in the Conduit's words"),
    ('buttons for pages under GOV.UK, not its pagination',
     'src/search/SearchResults.tsx', '  if (govuk) {\n    const link =', '  if (false) {\n    const link =',
     'src/search/SearchResults.test.tsx', 'the pages are GOV.UK pagination'),
    ('a browser date field under GOV.UK, not its date input',
     'src/search/SearchResults.tsx', '                  govuk ? (\n                    <GovukDateField', '                  false ? (\n                    <GovukDateField',
     'src/search/SearchResults.test.tsx', 'the dates are GOV.UK date inputs'),
    ("Combobox choosing the first option with onSubmit (main's highlighted 0)",
     'src/design/primitives/Combobox.tsx', 'const none = onSubmit ? -1 : 0;', 'const none = 0;',
     'src/design/primitives/Combobox.test.tsx', 'with onSubmit, Enter on the typed words submits them'),
    ('Combobox ignoring an option moved to',
     'src/design/primitives/Combobox.tsx', 'if (onSubmit && e.key === "Enter" && !(open && highlighted >= 0 && filtered[highlighted])) {', 'if (onSubmit && e.key === "Enter") {',
     'src/design/primitives/Combobox.test.tsx', 'with onSubmit, an option moved to'),
    ('ArrowUp stopping at the first option',
     'src/design/primitives/Combobox.tsx', 'setHighlighted((i) => Math.max(i - 1, none));', 'setHighlighted((i) => Math.max(i - 1, 0));',
     'src/design/primitives/Combobox.test.tsx', 'with onSubmit, ArrowUp from the first option'),
    ("GlobalSearch not passing Enter on (main's box)",
     'src/search/GlobalSearch.tsx', '          onSubmit={onSearch}\n', '',
     'src/App.search.test.tsx', 'Enter in the search box opens the results'),
    ('a view still current while the results show',
     'src/App.tsx', 'pressed: view === id && searching === null,', 'pressed: view === id,',
     'src/App.search.test.tsx', 'Enter in the search box opens the results'),
    ('the view left in reach beneath the results',
     'src/App.tsx', 'inert={app === "glass" && results.viewInert ? true : undefined}', 'inert={undefined}',
     'src/App.search.test.tsx', 'Enter in the search box opens the results'),
    ('the view drawn again on Back, not kept as it was',
     'src/App.tsx', '<div style={{ display: "contents" }} inert=', '<div key={searching ? "over" : "view"} style={{ display: "contents" }} inert=',
     'src/App.search.test.tsx', 'Back to Graph returns to the graph as it was'),
    ('Back leaving focus where it was',
     'src/search/useSearchResultsOverlay.ts', '      focusBox.current = true;\n', '',
     'src/App.search.test.tsx', 'Back to Graph returns to the graph as it was'),
    ('the back link always naming the Graph',
     'src/App.tsx', 'results.open(query, view === "dossier" ? "Messages" : (VIEW_LABELS as Record<string, string>)[view] ?? "Graph")', 'results.open(query, "Graph")',
     'src/App.search.test.tsx', 'the back link names the view the person left'),
    ('choosing a view leaving the results showing',
     'src/App.tsx', '            : () => {\n                results.leave();\n                setView(id);', '            : () => {\n                setView(id);',
     'src/App.search.test.tsx', 'choosing a view leaves the results'),
    ("a saved view opened under the results (the first review's)",
     'src/App.tsx', '    results.leave();\n    setView("graph");\n  }', '    setView("graph");\n  }',
     'src/App.search.test.tsx', 'a saved view opened from the Cases panel leaves the results'),
    ("another place keeping the results for the return (the first review's)",
     'src/App.tsx', '              results.leave();\n              if (place === "admin")', '              if (place === "admin")',
     'src/App.search.test.tsx', 'another place leaves the results'),
    ('the Ask line not carrying the words',
     'src/App.tsx', '            setQuestionDraft({ text: words, at: Date.now() });\n', '',
     'src/App.search.test.tsx', 'the Ask line opens Ask & Chat with the words'),
    ('Ask & Chat ignoring the words carried',
     'src/questions/QuestionsPanel.tsx', '    setQuestion(draft.text);\n', '',
     'src/App.search.test.tsx', 'the Ask line opens Ask & Chat with the words'),
    ("the carried words kept for every later opening (the first review's)",
     'src/App.tsx', '    if (!questionsOpen) setQuestionDraft(null);\n', '',
     'src/App.search.test.tsx', 'the words carried to Ask & Chat are carried once'),
    ('the Ask line offered without ask_model',
     'src/App.tsx', 'onAsk={railEntries(rights).includes("questions") ? (words) => {', 'onAsk={true ? (words) => {',
     'src/App.search.test.tsx', 'someone not offered Ask & Chat'),
    ('Show on graph not seeding',
     'src/App.tsx', '            void seedToCanvas(nodes, []);\n', '',
     'src/App.search.test.tsx', 'Show on graph seeds every record'),
    ('Show on graph seeding the first record alone',
     'src/App.tsx', '            void seedToCanvas(nodes, []);\n', '            void seedToCanvas(nodes.slice(0, 1), []);\n',
     'src/App.search.test.tsx', 'Show on graph seeds every record'),
    ("focus lost after Show on graph (the first review's)",
     'src/App.tsx', '            setTimeout(() => document.querySelector<HTMLElement>(\'[role="application"][aria-label="Network canvas"]\')?.focus(), 0);\n', '',
     'src/App.search.test.tsx', 'Show on graph seeds every record'),
    ('the results drawn over the reader (not hidden while a document is read)',
     'src/App.tsx', '          hidden={results.resultsHidden}\n', '',
     'src/App.search.test.tsx', 'Open reads a document over the view'),
    ("focus left on the inert view when the reader closes (the first review's)",
     'src/search/useSearchResultsOverlay.ts', '    if (was && !reading && searching !== null) document.querySelector<HTMLElement>(RESULTS_HEADING)?.focus();\n', '',
     'src/App.search.test.tsx', 'closing a document read from the results'),
    ("the same words searched again asking nothing (the first review's)",
     'src/search/useSearchResultsOverlay.ts', '      setSearching({ query, left, at: searches.current });', '      setSearching((was) => (was?.query === query ? was : { query, left, at: searches.current }));',
     'src/App.search.test.tsx', 'the same words searched again'),
    ("Help's keys panel under the results (the first review's)",
     'src/App.tsx', '          beside={welcomeOpen && welcome === "asked" ? welcomePanel : null}\n', '',
     'src/App.search.test.tsx', "Help's keys panel opens over the results"),
    ("the keys panel shown by itself drawn over the results (the live check's)",
     'src/App.tsx', 'beside={welcomeOpen && welcome === "asked" ? welcomePanel : null}', 'beside={welcomeOpen ? welcomePanel : null}',
     'src/App.search.test.tsx', 'the keys panel shown by itself on a first visit stays with the graph'),
    ("an over-long query's refusal without its limit (the live check's finding)",
     'src/search/SearchResults.tsx', ': tooLong(body?.detail, query);', ': null;',
     'src/search/SearchResults.test.tsx', 'a query longer than the search takes'),
    ("a list refusal shown in the framework's own words",
     'src/search/SearchResults.tsx', ': tooLong(body?.detail, query);', ': Array.isArray(body?.detail) ? String((body.detail[0] as { msg?: unknown })?.msg) : null;',
     'src/search/SearchResults.test.tsx', 'any other refusal given as a list'),
    ("the query's length counted in UTF-16 units, not characters as the route counts",
     'src/search/SearchResults.tsx', '${[...query].length}', '${query.length}',
     'src/search/SearchResults.test.tsx', 'a query longer than the search takes'),
]

def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    if subprocess.run(["git", "status", "--porcelain", "--", str(WS)], capture_output=True, text=True, cwd=ROOT).stdout.strip():
        print("refused: the workspace has uncommitted changes; plants restore with git checkout")
        return 2
    print(f"# v052-results jsdom reds at {head}; each plant restored with `git checkout -- <file>`")
    stayed_green = 0
    for n, (what, path, old, new, test_file, name) in enumerate(PLANTS, 1):
        target = WS / path
        text = target.read_text()
        if text.count(old) != 1:
            print(f"## {n}. {what}\nrefused: the planted string is in {path} {text.count(old)} times, not once")
            stayed_green += 1
            continue
        target.write_text(text.replace(old, new))
        try:
            # vitest's -t is a regular expression: the name is escaped, so "(Alert monitoring)" matches itself.
            run = subprocess.run(["npx", "vitest", "run", test_file, "-t", re.escape(name)], capture_output=True, text=True, cwd=WS)
        finally:
            subprocess.run(["git", "checkout", "--", str(target)], check=True, cwd=ROOT)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("×", "AssertionError", "Tests "))]
        print(f"## {n}. {what}\nplant in {path}; npx vitest run {test_file} -t {name!r}; exit {run.returncode}")
        print("\n".join(lines[:6]))
        if run.returncode == 0:
            stayed_green += 1
            print("STAYED GREEN")
        elif not re.search(r"Tests\s+\d+ failed", out):
            stayed_green += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    print(f"# {len(PLANTS) - stayed_green} of {len(PLANTS)} red")
    return 1 if stayed_green else 0


if __name__ == "__main__":
    sys.exit(main())
