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
    grep -m1 -E "AssertionError|Error:|expected" <<<"$out" | sed 's/^/    /'
  else
    echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "✓|×|FAIL|Tests " <<<"$out" | head -20; fails=1
  fi
}

plant "a 403 at the start read as any failure" "$API" \
  's/    if \(response.status === 403\) return \{ ok: false, kind: "forbidden" \};\n//' \
  "says a reader below Editor cannot start one, and asks nothing more"
plant "right_required read as a case level too low" "$API" \
  's/detail\?.error === "right_required" \? "right_required" : "forbidden"/"forbidden"/' \
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
  's/if \(response.status === 404\) return \{ ok: false, kind: "not_found" \};\n    if \(!response.ok\) return \{ ok: false, kind: "unreachable"/if (!response.ok) return { ok: false, kind: "unreachable"/' \
  "says a job that is not this reader's, or is gone, can no longer be found"
plant "the result not opened when the job is done" "$UI" \
  's/onViewOpenedRef.current\(result.opened\);//' \
  "opens the job's result as the view, and says the server's words and that it is open"
plant "a result view past the canvas's limit said as any failure" "$UI" \
  's/\} else if \(result.kind === "limit_exceeded"\) \{/} else if (false) {/' \
  "says a result view past the canvas's limit is kept and was not cut to fit"
plant "a failed job offered no second try" "$UI" \
  's/again: true, words: job.words \|\| "The batch job failed on the server."/again: false, words: job.words || "The batch job failed on the server."/' \
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
