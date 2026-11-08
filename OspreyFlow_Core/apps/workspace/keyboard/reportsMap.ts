// Chapter 4's *Intelligence reports* map (ADR-140 Amendment 10), built through the Map editor's own
// controls by keys alone: shared by `ingest-studio.spec.ts`, against the harness, and by
// `live/studio-reports-walk.spec.ts`, against a running Conduit. The map is the committed one, read
// from `fixtures/pid_intel_reports_map.json` (held to the YAML by
// `tests/demo_fixtures/test_reports_map_fixture.py`).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, type Page } from "@playwright/test";

async function press(page: Page, name: string, exact = true) {
  await page.getByRole("button", { name, exact }).focus();
  await page.keyboard.press("Enter");
}

export type Binding = { field?: string; literal?: string; transform?: string; optional?: boolean };
export type MapEntity = { ref: string; pole_class: string; type: string; match_on?: string; on_match?: string;
  when?: { field: string; is: string }; properties: Record<string, Binding>; content?: { kind: string; field: string };
  handling: Record<string, { field: string }> };  // prettier-ignore
export type MapEdge = { type: string; from: string; to: string; when?: { field: string; is: string }; handling: Record<string, { field: string }> };
export type ReportsMap = { row_template: { entities: MapEntity[]; edges: MapEdge[] };
  unmapped_fields: { field: string; action: string; note?: string }[]; deduplicate: { key: Binding[] } };  // prettier-ignore
export const REPORTS_MAP = JSON.parse(
  readFileSync(fileURLToPath(new URL("./fixtures/pid_intel_reports_map.json", import.meta.url)), "utf8"),
) as ReportsMap;

/** What a saved map means, as the server reads it: a key holding `null` is absent, and a link with
 * `properties: {}` has none (`RecipeEdge.properties` defaults to `{}`). Nothing else is forgiven. */
export function meaning(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(meaning);
  if (value === null || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value)
      .filter(([key, v]) => v !== null && v !== undefined && !(key === "properties" && Object.keys(v as object).length === 0))
      .map(([key, v]) => [key, meaning(v)]),
  );
}

export async function choose(page: Page, label: string, value: string) {
  const select = page.getByRole("combobox", { name: label, exact: true });
  await select.focus();
  await select.selectOption(value);
}

export async function tick(page: Page, name: string) {
  const box = page.getByRole("checkbox", { name, exact: true });
  await box.focus();
  await page.keyboard.press("Space");
  await expect(box).toBeChecked();
}

/** The keyboard bind: Choose on the column (unless it is already chosen), then Bind here. */
export async function bind(page: Page, column: string, target: string) {
  if (await page.getByRole("button", { name: `Choose column ${column}`, exact: true }).isVisible()) {
    await press(page, `Choose column ${column}`);
  }
  await press(page, `Bind ${column} here: ${target}`);
}

/** One property's own controls: the inspector shows each under its name. */
export const propertyRow = (page: Page, name: string) =>
  page.locator("strong").filter({ hasText: new RegExp(`^${name}$`) }).locator("xpath=..");

export async function bindHandling(page: Page, handling: Record<string, { field: string }>) {
  await tick(page, "Override handling for this element");
  const labels: Record<string, string> = { classification: "Classification", handling_code: "Handling code",
    action_code: "Action code", sanitisation_code: "Sanitisation code", originator: "Originator", owning_unit: "Owning unit" };  // prettier-ignore
  for (const part of Object.keys(handling)) {
    const select = page.getByRole("combobox", { name: `${labels[part]} for this element`, exact: true });
    await select.focus();
    await select.selectOption({ label: `From column ${handling[part]!.field}` });
  }
}

export async function setCondition(page: Page, when: { field: string; is: string }) {
  await tick(page, "Conditional element");
  await choose(page, "Condition column", when.field);
  await choose(page, "Condition test", when.is);
}

export async function buildEntity(page: Page, entity: MapEntity) {
  await press(page, "+ entity");
  const ref = page.getByRole("textbox", { name: "Entity ref", exact: true });
  await ref.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type(entity.ref);
  await choose(page, "POLE class", entity.pole_class);
  await choose(page, "Entity type", entity.type);
  const matchOn = page.getByRole("textbox", { name: "Match on", exact: true });
  await matchOn.focus();
  await page.keyboard.type(entity.match_on ?? "");
  if (entity.on_match === "reference") {
    await page.getByRole("radio", { name: "reference existing" }).focus();
    await page.keyboard.press("Space");
  }
  for (const [name, binding] of Object.entries(entity.properties)) {
    await choose(page, "Add a property", name);
    const row = propertyRow(page, name);
    if (binding.literal !== undefined) {
      await row.getByRole("combobox", { name: "Binding kind" }).focus();
      await row.getByRole("combobox", { name: "Binding kind" }).selectOption("literal");
      await row.getByRole("textbox", { name: "Literal value" }).focus();
      await page.keyboard.type(binding.literal);
      continue;
    }
    await bind(page, binding.field!, name);
    if (binding.transform) {
      await row.getByRole("combobox", { name: "Transform" }).focus();
      await row.getByRole("combobox", { name: "Transform" }).selectOption(binding.transform);
    }
    if (binding.optional) {
      await row.getByRole("checkbox", { name: /^Optional/ }).focus();
      await page.keyboard.press("Space");
    }
  }
  if (entity.when) await setCondition(page, entity.when);
  if (entity.content) {
    await choose(page, "Its own text", entity.content.kind);
    await choose(page, "Column holding its text", entity.content.field);
  }
  await bindHandling(page, entity.handling);
  await expect(page.getByRole("button", { name: `Entity ${REPORTS_MAP.row_template.entities.indexOf(entity) + 1}: ${entity.ref} (${entity.type})` })).toBeVisible();
}

export async function buildLink(page: Page, edge: MapEdge) {
  await choose(page, "From entity", edge.from);
  await choose(page, "To entity", edge.to);
  await choose(page, "Link type", edge.type);
  await press(page, "Add link");
  if (edge.when) await setCondition(page, edge.when);
  await bindHandling(page, edge.handling);
}

/** Every entity and link of the map, then the ignored columns with their notes, in the Map editor. */
export async function mapTheReports(page: Page) {
  for (const entity of REPORTS_MAP.row_template.entities) await buildEntity(page, entity);
  for (const edge of REPORTS_MAP.row_template.edges) await buildLink(page, edge);
  for (const ignored of REPORTS_MAP.unmapped_fields) {
    await page.getByRole("textbox", { name: `Note for ignoring ${ignored.field}` }).focus();
    await page.keyboard.type(ignored.note ?? "");
    await press(page, `Ignore ${ignored.field}`);
  }
}
