#!/usr/bin/env bash
# Rule 15 for ADR-151's Glass half: each plant breaks one branch of BatchExpansion or its client in
# the shape the code meets at its own call site (the Conduit's status and body), and the named case
# must go red for it, with its failure's words kept; then everything is put back and is green.
# Run from the repository root, at a clean commit (each plant is restored from HEAD).
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
WS=OspreyFlow_Core/apps/workspace
API=$WS/src/workingset/batchExpansionApi.ts
UI=$WS/src/workingset/BatchExpansion.tsx
TEST=src/workingset/BatchExpansion.test.tsx
git diff --quiet -- "$API" "$UI" || { echo "commit first: the plants restore from HEAD"; exit 2; }
fails=0

run() { (cd "$WS" && npx vitest run "$TEST" 2>&1); }

plant() { # name, file, perl substitution, the case that must go red
  local name="$1" file="$2" sub="$3" case="$4" out
  perl -0pi -e "$sub" "$file"
  if git diff --quiet -- "$file"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$(run)"
  git checkout -q HEAD -- "$file"
  if grep -qF "FAIL  $TEST > BatchExpansion > $case" <<<"$out"; then
    echo "AS IT MUST BE (red): $name"
    # The words of the named case's own failure, not the first in the file.
    awk -v h="FAIL  $TEST > BatchExpansion > $case" 'index($0,h){f=1;next} f&&/AssertionError|Error:/{print "    " $0; exit}' <<<"$out"
  else
    echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "✓|×|FAIL|Tests " <<<"$out" | head -20; fails=1
  fi
}

plant "a new request or a renewed token starting another job" "$UI" \
  's/  \}, \[attempt\]\);/  }, [attempt, request, bearerToken]);/' \
  "starts one job, whatever the panel is given later: a new request object, a renewed token"
plant "the token read once, never renewed" "$UI" \
  's/asked.current = \{ \.\.\.asked.current, apiBaseUrl, bearerToken, investigationId, pollMs \};/asked.current = { ...asked.current, apiBaseUrl, investigationId, pollMs };/' \
  "starts one job, whatever the panel is given later: a new request object, a renewed token"
plant "the Conduit's 403 sentence replaced by the Glass's own" "$UI" \
  's/            started.words \?\?\n//' \
  "says a reader below Editor cannot start one in the Conduit's own sentence, and asks nothing more"
plant "a followed job said with this request's figures" "$UI" \
  's/\{!following && \(/{true \&\& (/' \
  "follows the job already running when the reader has one on this case"
plant "a 401 on a reading taken for a passing trouble" "$API" \
  's/if \(response.status === 401\) \{/if (false) {/' \
  "stops asking, and says so, when its sign-in has ended"
plant "readings that fail asked for ever" "$UI" \
  's/>= TROUBLES_BEFORE_STOPPING\)/>= Infinity)/' \
  "stops asking after a minute of readings that fail, and says the job carries on"
plant "a 403 at the start read as any failure" "$API" \
  's/if \(response.status === 403\) \{/if (false) {/' \
  "says a reader below Editor cannot start one in the Conduit's own sentence, and asks nothing more"
plant "right_required read as a case level too low" "$API" \
  's/if \(detail\?\.error === "right_required"\) return/if (false) return/' \
  "says an account without the right to expand cannot start one"
plant "a 404 at the start read as any failure" "$API" \
  's/    if \(response.status === 404\) return \{ ok: false, kind: "not_found" \};\n  *return \{ ok: false, kind: "failed", message: `The batch job could not be started/    return { ok: false, kind: "failed", message: `The batch job could not be started/' \
  "says a case the reader cannot open could not be, and starts nothing"
plant "a job already running read as a refusal" "$API" \
  's/response.status === 409 && body.error === "batch_expansion_running"/false/' \
  "follows the job already running when the reader has one on this case"
plant "the running job's id not followed (the new request's taken instead)" "$UI" \
  's/\[started.running.id, started.running.words\]/["j1", started.running.words]/' \
  "follows the job already running when the reader has one on this case"
plant "a stage's words replaced by the Glass's own" "$UI" \
  's/setShown\(\{ phase: "watching", words: job.words \|\| "The batch job is under way.", trouble: null \}\);/setShown({ phase: "watching", words: "The batch job is under way.", trouble: null });/' \
  "says each stage in the server's own words"
plant "a refusal's words replaced by the Glass's own" "$UI" \
  's/  if \(job.words\) return job.words;\n//' \
  "says a refused job in the server's words, and opens nothing"
plant "a refused job offered a second try" "$UI" \
  's/setShown\(\{ phase: "stopped", again: false, words: refusalWords\(job\) \}\);/setShown({ phase: "stopped", again: true, words: refusalWords(job) });/' \
  "says a refused job in the server's words, and opens nothing"
plant "a state not known read as waiting" "$API" \
  's/!STATES.has\(body.state\)/false/' \
  "never reads a state it does not know as progress"
plant "a job not this reader's read as progress not read" "$API" \
  's/if \(response.status === 404\) return \{ ok: false, kind: "not_found" \};\n    if \(response.status === 401\)/if (response.status === 401)/' \
  "says a job that is not this reader's, or is gone, can no longer be found"
plant "the result not opened when the job is done" "$UI" \
  's/onViewOpenedRef.current\(result.opened\);//' \
  "opens the job's result as the view, and says the server's words and that it is open"
plant "a done job's deleted-view words replaced by the Glass's own" "$UI" \
  's/words: job.words \|\| "The batch expansion finished, but the view it saved has since been deleted." \}\);/words: "The batch job finished." });/' \
  "says a done job whose view has since been deleted in the server's words, and opens nothing"
plant "the carry-on note left up once the job ends" "$UI" \
  's/\{\(shown.phase === "starting" \|\| shown.phase === "watching"\) \&\& \(/{true \&\& (/' \
  "says the job carries on when closed, only while it runs"
plant "a result view past the canvas's limit said as any failure" "$UI" \
  's/\} else if \(result.kind === "limit_exceeded"\) \{/} else if (false) {/' \
  "says a result view past the canvas's limit is kept and was not cut to fit"
plant "a failed job offered no second try" "$UI" \
  's/again: true, words: job.words \|\| "The batch expansion could not finish/again: false, words: job.words || "The batch expansion could not finish/' \
  "says a failed job in the server's words, and offers to try it again"
plant "progress not read taken as the end" "$UI" \
  's/          trouble,\n        \}\)\);\n      \}/          trouble,\n        }));\n        return;\n      }/' \
  "says when the progress could not be read, and goes on asking"
plant "the asking not stopped once closed" "$UI" \
  's/if \(timer !== undefined\) clearTimeout\(timer\);/live = true;/' \
  "stops asking once closed"

out="$(run)"
if grep -q "Tests .*passed" <<<"$out" && ! grep -q "failed" <<<"$(grep 'Tests ' <<<"$out")"; then
  echo "unplanted: $(grep -E 'Tests ' <<<"$out" | head -1 | xargs)"
else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
