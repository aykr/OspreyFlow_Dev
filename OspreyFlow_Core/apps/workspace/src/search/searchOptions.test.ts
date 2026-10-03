import { describe, expect, it } from "vitest";

import type { Node } from "../../../../packages/schemas/generated";
import {
  DEFAULT_SEARCH_OPTIONS,
  activeFilterCount,
  displayValue,
  matchOnScreen,
  suggestBody,
  type SearchOptions,
} from "./searchOptions";

function node(id: string, type: string, value: string): Node {
  return { id, type, properties: { value_normalised: value } } as unknown as Node;
}

const withOptions = (o: Partial<SearchOptions>): SearchOptions => ({ ...DEFAULT_SEARCH_OPTIONS, ...o });

describe("suggestBody", () => {
  it("sends only the query and limit when every filter is at its default", () => {
    expect(suggestBody("C13", 10, DEFAULT_SEARCH_OPTIONS)).toEqual({ query: "C13", limit: 10 });
  });

  it("sends each filter that has been changed, under the Conduit's own names", () => {
    const body = suggestBody("c13", 10, withOptions({ ignoreCase: true, mode: "contains", types: ["Endpoint"] }));
    expect(body).toEqual({ query: "c13", limit: 10, ignore_case: true, mode: "contains", types: ["Endpoint"] });
  });

  it("sends no type list when no type is chosen, so every type is searched", () => {
    expect(suggestBody("c13", 10, withOptions({ types: [] }))).not.toHaveProperty("types");
  });
});

describe("activeFilterCount", () => {
  it("is zero at the defaults", () => {
    expect(activeFilterCount(DEFAULT_SEARCH_OPTIONS)).toBe(0);
  });

  it("counts each changed filter once, however many types are chosen", () => {
    expect(activeFilterCount(withOptions({ ignoreCase: true }))).toBe(1);
    expect(activeFilterCount(withOptions({ mode: "exact" }))).toBe(1);
    expect(activeFilterCount(withOptions({ types: ["A", "B", "C"] }))).toBe(1);
    expect(activeFilterCount(withOptions({ onScreenOnly: true }))).toBe(1);
    expect(
      activeFilterCount(withOptions({ ignoreCase: true, mode: "exact", types: ["A"], onScreenOnly: true })),
    ).toBe(4);
  });
});

describe("matchOnScreen", () => {
  const nodes = [
    node("1", "Endpoint", "Jeff.Skilling@enron.com"),
    node("2", "Endpoint", "jeff.dasovich@enron.com"),
    node("3", "Person", "Jeffrey Archer"),
    node("4", "Endpoint", "xjeffx"),
  ];
  const ids = (found: { nodes: Node[] }) => found.nodes.map((n) => n.id);

  it("matches the start of a value, and is case-sensitive, by default", () => {
    expect(ids(matchOnScreen(nodes, "jeff", DEFAULT_SEARCH_OPTIONS, 10))).toEqual(["2"]);
  });

  it("ignores case when asked", () => {
    expect(ids(matchOnScreen(nodes, "JEFF", withOptions({ ignoreCase: true }), 10))).toEqual(["1", "2", "3"]);
  });

  it("matches anywhere in a value in contains mode", () => {
    expect(ids(matchOnScreen(nodes, "jeff", withOptions({ mode: "contains" }), 10))).toEqual(["2", "4"]);
  });

  it("matches the whole value only in exact mode, and not a longer one", () => {
    expect(ids(matchOnScreen(nodes, "xjeffx", withOptions({ mode: "exact" }), 10))).toEqual(["4"]);
    expect(ids(matchOnScreen(nodes, "xjeff", withOptions({ mode: "exact" }), 10))).toEqual([]);
  });

  it("keeps to the chosen entity types", () => {
    expect(ids(matchOnScreen(nodes, "Jeff", withOptions({ types: ["Person"] }), 10))).toEqual(["3"]);
  });

  it("treats typed characters as text, not a pattern", () => {
    const dotted = [node("a", "Endpoint", "a.b"), node("b", "Endpoint", "axb")];
    expect(ids(matchOnScreen(dotted, "a.b", withOptions({ mode: "contains", ignoreCase: true }), 10))).toEqual(["a"]);
    expect(ids(matchOnScreen(dotted, "a+(b", withOptions({ mode: "contains" }), 10))).toEqual([]);
  });

  it("stops at the limit and says more matched", () => {
    const many = Array.from({ length: 5 }, (_, i) => node(String(i), "Endpoint", `acct-${i}`));
    const found = matchOnScreen(many, "acct", DEFAULT_SEARCH_OPTIONS, 3);
    expect(found.nodes).toHaveLength(3);
    expect(found.more).toBe(true);
    expect(matchOnScreen(many, "acct", DEFAULT_SEARCH_OPTIONS, 5).more).toBe(false);
  });

  it("finds nothing for an empty query", () => {
    expect(matchOnScreen(nodes, "", DEFAULT_SEARCH_OPTIONS, 10).nodes).toEqual([]);
  });
});

// ADR-074 made names searchable on the server. The Glass has to show a person by name and, in its
// on-screen mode, find one by name, or a correct answer reads as a NINO and a name matches nothing.
describe("people and documents, by name", () => {
  const person = (id: string, family: string, given: string): Node =>
    ({
      id,
      type: "Person",
      properties: { nino: "QQ548351C", family_name: family, given_names: given },
    }) as unknown as Node;
  const document = { id: "d1", type: "Document", properties: { title: "Q3 Board Minutes" } } as unknown as Node;

  it("shows a person as their name, not their NINO", () => {
    expect(displayValue(person("p1", "Petrenko", "Illia"))).toBe("Petrenko, Illia");
  });

  it("shows a person with only a family name as that name", () => {
    const only = { id: "p2", type: "Person", properties: { nino: "QQ1", family_name: "Petrenko" } } as unknown as Node;
    expect(displayValue(only)).toBe("Petrenko");
  });

  it("still shows a person with no name by their NINO", () => {
    const nameless = { id: "p3", type: "Person", properties: { nino: "QQ176119C" } } as unknown as Node;
    expect(displayValue(nameless)).toBe("QQ176119C");
  });

  it("shows a document by its title", () => {
    expect(displayValue(document)).toBe("Q3 Board Minutes");
  });

  it("finds a person on screen by the start of the family name", () => {
    const found = matchOnScreen([person("p1", "Petrenko", "Illia"), person("p2", "Petrenco", "Ilia")], "Petrenko", DEFAULT_SEARCH_OPTIONS, 10);
    expect(found.nodes.map((n) => n.id)).toEqual(["p1"]);
  });

  it("finds a person on screen by given name, and a document by title", () => {
    const nodes = [person("p1", "Petrenko", "Illia"), document];
    expect(matchOnScreen(nodes, "Illia", DEFAULT_SEARCH_OPTIONS, 10).nodes.map((n) => n.id)).toEqual(["p1"]);
    expect(matchOnScreen(nodes, "Q3", DEFAULT_SEARCH_OPTIONS, 10).nodes.map((n) => n.id)).toEqual(["d1"]);
  });
});
