"""v052-results (ADR-145 Amendment 15 Part A, the search results page): the browser (Playwright keyboard) reds, each a plant at the real call site.

Run from the worktree root at the commit under test, with process/lanes/case/shared-files-v052-results.diff applied
(git apply) and nothing else changed:
    python3 OspreyFlow_Build/process/lanes/case/gates/v052_results_browser_reds.py > OspreyFlow_Build/process/lanes/case/gates/v052-results-browser-reds.log

Each plant replaces one exact string in one file (refused if the string is not there exactly once), runs the
named Playwright keyboard file (the lane's slot 2, OSPREY_PORTS_SLOT=2) filtered to the named test, records the result, and restores the file with
`git checkout -- <file>`. A plant whose test stays green is a failure of this record.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip())
WS = ROOT / "OspreyFlow_Core/apps/workspace"

PLANTS = [
    ("Enter not passed on by the search box (main's GlobalSearch)",
     [('src/search/GlobalSearch.tsx', '          onSubmit={onSearch}\n', '')],
     'keyboard/search-results.spec.ts', 'ospreyflow dark: Enter in the search box opens the results'),
    ("the view left in reach beneath the results (the hook's viewInert)",
     [('src/search/useSearchResultsOverlay.ts', '    viewInert: searching !== null && !reading,', '    viewInert: false,')],
     'keyboard/search-results.spec.ts', 'ospreyflow dark: Enter in the search box opens the results'),
    ('the heading not focused on opening',
     [('src/search/SearchResults.tsx', '  useEffect(() => {\n    heading.current?.focus();\n  }, [query]);', '  useEffect(() => undefined, [query]);')],
     'keyboard/search-results.spec.ts', 'govuk light: Enter in the search box opens the results'),
    ('a group not chosen by its button',
     [('src/search/SearchResults.tsx', 'onClick={() => choose({ group: g.key })}', 'onClick={() => undefined}')],
     'keyboard/search-results.spec.ts', 'ospreyflow light: a group, a dataset and the next page'),
    ("Next page asking the same page (GOV.UK's link)",
     [('src/search/SearchResults.tsx', 'onTurn(to);', 'onTurn(page);')],
     'keyboard/search-results.spec.ts', 'govuk light: a group, a dataset and the next page'),
    ("focus lost with the pager's button",
     [('src/search/SearchResults.tsx', '    focusHeadingOnAnswer.current = true;\n    setPage(next);', '    setPage(next);')],
     'keyboard/search-results.spec.ts', 'ospreyflow dark: a group, a dataset and the next page'),
    ('Clear filters doing nothing',
     [('src/search/SearchResults.tsx', '        focusHeadingOnAnswer.current = true;\n        choose({ filters: NO_FILTERS });', '        focusHeadingOnAnswer.current = true;')],
     'keyboard/search-results.spec.ts', 'ospreyflow light: a group, a dataset and the next page'),
    ('the GOV.UK date input never sending a date',
     [('src/search/SearchResults.tsx', '    onDate(date.toISOString().slice(0, 10));\n', '')],
     'keyboard/search-results.spec.ts', 'govuk light: the results are filtered by date'),
    ('the browser date field not sending its date',
     [('src/search/SearchResults.tsx', 'onChange={(e) => choose({ filters: { ...filters, [key]: e.target.value } })}', 'onChange={() => undefined}')],
     'keyboard/search-results.spec.ts', 'ospreyflow dark: the results are filtered by date'),
    ('Open doing nothing',
     [('src/search/SearchResults.tsx', 'onClick={() => onOpenDocument(first.id)}', 'onClick={() => undefined}')],
     'keyboard/search-results.spec.ts', 'ospreyflow dark: a result is shown on the graph'),
    ("the results drawn though marked hidden (the stylesheet's grid over [hidden])",
     [('src/search/searchResults.css', '.search-results[hidden] { display: none; }\n', '')],
     'keyboard/search-results.spec.ts', 'ospreyflow light: a result is shown on the graph'),
    ('focus left on the view when the reader closes',
     [('src/search/useSearchResultsOverlay.ts', '    if (was && !reading && searching !== null) document.querySelector<HTMLElement>(RESULTS_HEADING)?.focus();\n', '')],
     'keyboard/search-results.spec.ts', 'govuk light: a result is shown on the graph'),
    ('Back leaving focus where it was',
     [('src/search/useSearchResultsOverlay.ts', '      focusBox.current = true;\n', '')],
     'keyboard/search-results.spec.ts', 'govuk light: Back returns to the view'),
    ('Enter always submitting, over a suggestion moved to',
     [('src/design/primitives/Combobox.tsx', 'if (onSubmit && e.key === "Enter" && !(open && highlighted >= 0 && filtered[highlighted])) {', 'if (onSubmit && e.key === "Enter") {')],
     'keyboard/search-results.spec.ts', 'a suggestion moved to with the arrow keys'),
]


def main() -> int:
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.strip()
    # The shared diff (the registry and every-harness, the orchestrator's files) is applied for the run, since the spec
    # imports its registry; nothing else may be changed.
    shared = {"keyboard/actionRegistry.ts", "a11y/every-harness.spec.ts"}
    dirty = [l[3:] for l in subprocess.run(["git", "status", "--porcelain", "--", str(WS)], capture_output=True, text=True, cwd=ROOT).stdout.splitlines()]
    if [d for d in dirty if not any(d.endswith(s) for s in shared)]:
        print("refused: the workspace has uncommitted changes; plants restore with git checkout")
        return 2
    print(f"# v052-results browser reds at {head}; each plant restored with `git checkout -- <file>`")
    stayed_green = 0
    # Optional plant numbers as arguments run those alone (a later addition, without rerunning the rest).
    only = {int(a) for a in sys.argv[1:]}
    for n, (what, edits, test_file, name) in enumerate(PLANTS, 1):
        if only and n not in only:
            continue
        bad = [(p, (WS / p).read_text().count(o)) for p, o, _ in edits if (WS / p).read_text().count(o) != 1]
        if bad:
            print(f"## {n}. {what}\nrefused: a planted string is not there exactly once: {bad}")
            stayed_green += 1
            continue
        for p, o, nw in edits:
            (WS / p).write_text((WS / p).read_text().replace(o, nw))
        path = ", ".join(sorted({p for p, _, _ in edits}))
        try:
            # -g is a regular expression: the name is escaped, so parentheses in a name match themselves.
            run = subprocess.run(["npx", "playwright", "test", "--config", "keyboard/playwright.config.ts", test_file, "-g", re.escape(name)],
                                 capture_output=True, text=True, cwd=WS, env={**os.environ, "OSPREY_PORTS_SLOT": "2"})
        finally:
            subprocess.run(["git", "checkout", "--", *sorted({str(WS / p) for p, _, _ in edits})], check=True, cwd=ROOT)
        out = run.stdout + run.stderr
        lines = [l for l in out.splitlines() if any(k in l for k in ("✘", "✓", "Error:", "Expected", "Received", " passed", " failed"))]
        print(f"## {n}. {what}\nplant in {path}; OSPREY_PORTS_SLOT=2 npx playwright test --config keyboard/playwright.config.ts {test_file} -g {name!r}; exit {run.returncode}")
        print("\n".join(lines[:24]))
        if run.returncode == 0:
            stayed_green += 1
            print("STAYED GREEN")
        elif not re.search(r"\d+ failed", out):
            stayed_green += 1
            print("NO TEST FAILED (the run failed otherwise): not a red")
    ran = len(only) if only else len(PLANTS)
    print(f"# {ran - stayed_green} of {ran} red")
    return 1 if stayed_green else 0


if __name__ == "__main__":
    sys.exit(main())
