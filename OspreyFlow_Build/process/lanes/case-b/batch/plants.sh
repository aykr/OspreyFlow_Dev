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
  "says a reader without the right to edit the case cannot start one, and starts nothing"
plant "a 404 at the start read as any failure" "$API" \
  's/    if \(response.status === 404\) return \{ ok: false, kind: "not_found" \};\n//' \
  "says a case the reader cannot open could not be, and starts nothing"
plant "the batch job's own limit at the start read as any failure" "$API" \
  's/response.status === 409 && body.error === "limit_exceeded"/false/' \
  "says an expansion past the batch job's own limit is refused at the start, in the reader's figure"
plant "a job refused as it runs read as failed" "$API" \
  's/case "refused": \{/case "refused-not": {/' \
  "says a job whose result passed its limit stopped, saved nothing and cut nothing"
plant "a state not known read as waiting" "$API" \
  's/default:\n        return \{ state: "failed", message: "The server answered with a state the Glass does not know." \};/default:\n        return { state: "queued" };/' \
  "never reads a state it does not know as progress"
plant "a job no longer found read as one still going" "$API" \
  's/if \(response.status === 404\) return \{ state: "not_found" \};/if (response.status === 404) return { state: "queued" };/' \
  "says a job no longer found could not be"
plant "the result not opened when the job is done" "$UI" \
  's/onViewOpenedRef.current\(result.opened\);//' \
  "opens the job's result as the view and says so when the job is done"
plant "a result view past the canvas's limit said as any failure" "$UI" \
  's/\} else if \(result.kind === "limit_exceeded"\) \{\n        setShown\(\{/} else if (false) {\n        setShown({/' \
  "says a result view past the canvas's limit is kept and was not cut to fit"
plant "a failed job offered no second try" "$UI" \
  's/again: true,\n            words: `The batch job failed on the server/again: false,\n            words: `The batch job failed on the server/' \
  "says a failed job failed, in the server's words, and offers to try it again"
plant "progress not read taken as the end" "$UI" \
  's/trouble: `\$\{job.message\} Still trying.`,\n          \}\)\);\n          break;/trouble: `\${job.message} Still trying.`,\n          }));\n          return;/' \
  "says when the progress could not be read, and goes on asking"
plant "the asking not stopped once closed" "$UI" \
  's/if \(timer !== undefined\) clearTimeout\(timer\);/live = true;/' \
  "stops asking once closed"

out="$(run)"
if grep -q "Tests .*passed" <<<"$out" && ! grep -q "failed" <<<"$(grep 'Tests ' <<<"$out")"; then
  echo "unplanted: $(grep -E 'Tests ' <<<"$out" | head -1 | xargs)"
else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
