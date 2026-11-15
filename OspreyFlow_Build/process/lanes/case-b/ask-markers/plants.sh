#!/usr/bin/env bash
# Rule 15 for the Ask & Chat answer's markers and wording (the owner's word, 15 November 2026): each plant breaks one
# of the four points, or `about`'s two conditions (the orchestrator's: built only from the asker's brief; never sent
# to the model), in the code's own shape, and the named case goes red; restored from saved copies, never `git
# checkout`. Offline: the closed ports, no lane. Run from the repository root.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)"
CORE=OspreyFlow_Core
WS=$CORE/apps/workspace
Q=$CORE/services/api/questions.py
EB=$CORE/services/api/evidence_brief.py
P=$WS/src/questions/QuestionsPanel.tsx
E=$WS/src/models/engines.tsx
SAVED="$(mktemp -d)"; for f in "$Q" "$EB" "$P" "$E"; do cp "$f" "$SAVED/$(basename "$f")"; done
restore() { for f in "$Q" "$EB" "$P" "$E"; do cp "$SAVED/$(basename "$f")" "$f"; done; }
trap 'restore; rm -rf "$SAVED"' EXIT
fails=0
py() { (cd "$CORE" && env -u OSPREY_LANE ARCADEDB_HTTP_PORT=59991 POSTGRES_PORT=59992 POSTGRES_PASSWORD=throwaway \
  VALKEY_PORT=59993 CLICKHOUSE_HTTP_PORT=59994 .venv/bin/pytest -c ../OspreyFlow_Build/pytest.ini -q -p no:cacheprovider -rf \
  ../OspreyFlow_Build/tests/services/api/test_questions_graph_facts.py 2>&1); }
js() { (cd "$WS" && npx vitest run src/questions/QuestionsPanel.test.tsx 2>&1); }
plant() { # name, file, perl substitution, runner, the case (a substring of its name)
  local name="$1" file="$2" sub="$3" runner="$4" case="$5" out
  perl -0pi -e "$sub" "$file"
  if cmp -s "$file" "$SAVED/$(basename "$file")"; then echo "PLANT DID NOT APPLY: $name"; fails=1; return; fi
  out="$($runner)"; restore
  if grep -E "^FAILED|×" <<<"$out" | grep -qF "$case"; then echo "AS IT MUST BE (red): $name"; grep -E "^FAILED|×" <<<"$out" | grep -F "$case" | head -1 | sed -E 's/^ *//; s/ - .*//'
  else echo "NOT RED FOR ITS REASON: $name (wanted: $case)"; grep -E "^FAILED|×|passed|failed" <<<"$out" | head -4; fails=1; fi
}
plant "about read from a scope wider than the asker may see" "$Q" \
  's/nodes, edges = await self._working_set.visible_membership\(investigation_id, principal\)/nodes, edges = await self._working_set.visible_membership(investigation_id, principal.model_copy(update={"clearance": "SECRET"}))/' \
  py "test_no_fact_s_about_names_a_node_the_asker_may_not_see"
plant "about sent to the model in the brief" "$EB" \
  's/            lines.append\(_fact_line\(number, edge, held, dataset_labels\)\)/            lines.append(_fact_line(number, edge, held, dataset_labels) + " (" + _fact_about(edge, held[edge.source], held[edge.target]) + ")")/' \
  py "test_what_the_model_is_sent_is_byte_for_byte_as_before"
plant "about not carried to the Glass" "$Q" \
  's/                about=held\[n\].about,\n//' \
  py "test_a_cited_fact_says_what_it_is_in_the_canvas_s_names"
plant "a marker drawn as a padded button (the wide gaps)" "$P" \
  's/className=\{currentBrand\(\) === "govuk" \? "govuk-link answer-marker" : "answer-marker"\}/className="btn btn--quiet"/' \
  js "puts a marker one space after the words it follows"
plant "the model's spaces around a marker kept" "$P" \
  's/  const spaced = spacedAroundMarkers\(parts\);/  const spaced = parts;/' \
  js "puts a marker one space after the words it follows"
plant "a marker named by its number alone" "$P" \
  's/aria-label=\{`Show on the graph: \$\{shows\}, \$\{label\}`\}/aria-label={label}/' \
  js "names each marker by what choosing it shows"
plant "no line under the answer" "$P" \
  's/Select a marker to show that item on the graph\./ /' \
  js "names each marker by what choosing it shows"
plant "the local engine with its capital inside the sentence" "$E" \
  's/const label = offered === LOCAL_LABEL \? `t\$\{LOCAL_LABEL.slice\(1\)\}` : offered;/const label = offered;/' \
  js "writes the local engine in lower case inside Answered by"
plant "a bracket nested in what was read" "$P" \
  's/      \? `; \$\{counted\(read.documents_without_text, "document has", "documents have"\)\} no text to read`/      ? ` (\${counted(read.documents_without_text, "document has", "documents have")} no text to read)`/' \
  js "never nests a bracket in what was read"
p="$(py)"; j="$(js)"
if grep -qE "[0-9]+ passed" <<<"$p" && ! grep -qE "[0-9]+ failed" <<<"$p" && grep -qE "Tests  [0-9]+ passed" <<<"$j" && ! grep -qE "Tests .*failed" <<<"$j"; then
  echo "unplanted: $(grep -E '[0-9]+ passed' <<<"$p" | tail -1); vitest $(grep 'Tests ' <<<"$j" | xargs)"; else echo "UNPLANTED NOT GREEN"; fails=1; fi
[ "$fails" = 0 ] && echo "every plant red for its reason, unplanted green" || { echo "SOME PLANT WRONG"; exit 1; }
