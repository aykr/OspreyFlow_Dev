// v0.6.0 #6, the orchestrator's ruling (b) of 15 November 2026: names are words, set in the page's face; `.value` (mono)
// is for a value to copy (tokens.css: "every identifier, hash, timestamp and account number"). The confirming pass
// trusts `.value`, so a name wrongly classed `.value` is its blind spot: each site read and called a name is held here,
// at its own source, so the class does not come back. A site called a value (Home's signed-in username) keeps it.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..");
const source = (file: string) => readFileSync(join(SRC, file), "utf-8");

/** [file, the name's own expression as rendered, what it is] */
const NAMES: [string, string, string][] = [
  ["help/RolesHelpPage.tsx", "{p.name}", "a place's name"],
  ["help/RolesHelpPage.tsx", "{r.name}", "a role's name"],
  ["help/RolesHelpPage.tsx", "{l.name}", "a level's name"],
  ["help/RolesHelpPage.tsx", "{rightName(right)}", "a right's name"],
  ["ingest/checks/ChecksScreen.tsx", "{rule.name}", "a load rule's name"],
  ["reports/DataFeedsTab.tsx", "{f.label}", "a data feed's label"],
  ["matrix/MatrixView.tsx", "{row.name}", "an entity's name, a row's header"],
  ["reports/PackItemView.tsx", "{item.entity.name}", "an entity's name in a pack"],
  ["questions/QuestionsPanel.tsx", "{source.name}", "a source's name"],
  ["questions/QuestionsPanel.tsx", "{candidateLabel(candidate)}", "a proposed entity's type and name"],
  ["alerts/RuleEditor.tsx", "{dataset.name}", "a dataset's name"],
  ["inspector/SelectionList.tsx", "{name}", "a selected entity's name"],
  ["home/HomePage.tsx", "{s.name}", "a service's name"],
];

/** The opening tag nearest before the expression: the element it is drawn in. */
function tagAround(text: string, expression: string): string[] {
  const tags: string[] = [];
  for (let at = text.indexOf(expression); at >= 0; at = text.indexOf(expression, at + 1)) {
    const open = text.lastIndexOf("<", at);
    tags.push(text.slice(open, text.indexOf(">", open) + 1));
  }
  return tags;
}

describe("a name is set in the page's face, never classed as a value to copy", () => {
  it.each(NAMES)("%s: %s (%s)", (file, expression) => {
    const tags = tagAround(source(file), expression);
    expect(tags.length, `${expression} is drawn in ${file}`).toBeGreaterThan(0);
    for (const tag of tags) expect(tag, tag).not.toMatch(/className=\{?["`][^"`]*\bvalue\b/);
  });

  it("a value to copy keeps its mono: Home's signed-in username", () => {
    expect(tagAround(source("home/HomePage.tsx"), "{person.username}").join(" ")).toMatch(/className="value"/);
  });
});
