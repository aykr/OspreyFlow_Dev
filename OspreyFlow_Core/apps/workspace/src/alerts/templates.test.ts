// The templates' severities are the Conduit's defaults (`services/api/alerts.py`), read from its
// source, so the Rules tab never promises a severity the queue will not show.
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { TEMPLATES } from "./templates";

const SOURCE = readFileSync(new URL("../../../../services/api/alerts.py", import.meta.url), "utf8");

function pythonDict(name: string): Record<string, string> {
  const body = SOURCE.split(`${name}:`)[1]?.split("}")[0] ?? "";
  return Object.fromEntries([...body.matchAll(/"(\w+)": "(\w+)"/g)].map((m) => [m[1], m[2]]));
}

describe("the rule templates", () => {
  it("say the severity the Conduit gives each typology's alerts", () => {
    const byTypology = pythonDict("TYPOLOGY_SEVERITY");
    const fallback = pythonDict("DEFAULT_SEVERITY").typology;
    expect(fallback).toBe("medium");
    for (const template of TEMPLATES) {
      expect([template.typology, template.severity]).toEqual([template.typology, byTypology[template.typology] ?? fallback]);
    }
  });
});
