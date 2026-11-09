// Studio › Sources' connectors and screening lists by keyboard alone (rule 13; ADR-140 Amendment 13):
// a dataset subscribed to a list by its id, a list imported through a format's template and through the
// blank template's column picks, Refresh now, a schedule, a dataset's own list's rows, a source registered
// through a SQL connection by its read, and Refresh now on that source. The fake server refuses what the
// Conduit refuses (rule 15): a subscription to an id it does not hold, a blank list with no mapping, a
// SQL source sent with a file instead of its read.
import { expect, test, type Page, type Route } from "@playwright/test";

import { SOURCES_CONNECTORS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "SOURCES_CONNECTORS_ACTIONS";
const HARNESS = "/keyboard/sources-connectors-harness.html";

type Body = Record<string, unknown>;
interface Held {
  id: string;
  name: string;
  template: string;
  location: string;
  version: number;
  entries: number;
  schedule_words: string | null;
  schedule: Body | null;
}

function list(l: Held) {
  return { ...l, synthetic: true, licence: "synthetic", created_by: "eng-1", created_at: "2026-11-08T09:00:00Z",
           updated_at: l.version ? "2026-11-08T09:05:00Z" : null };  // prettier-ignore
}

async function serve(page: Page, opts: { canManage?: boolean } = {}) {
  const lists: Held[] = [
    { id: "01OFAC", name: "OFAC SDN (synthetic)", template: "ofac_sdn", location: "lists/SDN.CSV", version: 1, entries: 3,
      schedule_words: null, schedule: null },
  ];  // prettier-ignore
  const state = { subscribed: [] as string[], asked: [] as { method: string; path: string; body: unknown }[] };
  const json = (r: Route, body: unknown, status = 200) =>
    r.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/keyboard-test.invalid/**", async (r) => {
    const url = new URL(r.request().url());
    const method = r.request().method();
    const body = (r.request().postDataJSON() ?? null) as Body | null;
    const path = url.pathname;
    state.asked.push({ method, path, body });
    const subs = () => ({
      lists: lists.map((l) => ({ id: l.id, name: l.name, template: l.template, version: l.version, entries: l.entries,
        updated_at: null, failing: false, schedule_words: l.schedule_words })),
      subscribed: state.subscribed,
    });  // prettier-ignore
    if (path === "/v1/datasets/ds-a/screening-subscriptions") return json(r, subs());
    const sub = path.match(/^\/v1\/datasets\/ds-a\/screening-subscriptions\/(.+)$/);
    if (sub) {
      const id = decodeURIComponent(sub[1]!);
      if (!lists.some((l) => l.id === id)) return json(r, { detail: { detail: "There is no deployment-wide list of that id." } }, 404);
      state.subscribed = method === "PUT" ? [...new Set([...state.subscribed, id])] : state.subscribed.filter((x) => x !== id);
      return json(r, subs());
    }
    if (path === "/v1/datasets/ds-a/reference-lists/offered") {
      return json(r, [{ id: "rl-est", name: "establishments", kind: "reference", version: 1, deployment_wide: false },
        ...lists.filter((l) => state.subscribed.includes(l.id)).map((l) => ({ id: l.id, name: l.name, kind: "screening",
          version: l.version, deployment_wide: true }))]);  // prettier-ignore
    }
    if (path === "/v1/studio/screening-lists") {
      if (!opts.canManage) return json(r, { detail: "forbidden" }, 403);
      if (method === "GET") return json(r, lists.map(list));
      if (body?.template === "blank" && !body.mapping) return json(r, { detail: { detail: "the blank template needs a mapping" } }, 422);
      const made: Held = { id: `01NEW${lists.length}`, name: String(body?.name), template: String(body?.template),
        location: String(body?.location), version: 0, entries: 0, schedule_words: null, schedule: null };  // prettier-ignore
      lists.push(made);
      return json(r, list(made), 201);
    }
    const refresh = path.match(/^\/v1\/studio\/screening-lists\/(.+)\/refresh$/);
    if (refresh) {
      const l = lists.find((x) => x.id === refresh[1]);
      if (!l) return json(r, {}, 404);
      const changed = l.version === 0;
      if (changed) Object.assign(l, { version: 1, entries: 3 });
      return json(r, { list_id: l.id, outcome: changed ? "updated" : "unchanged", version: l.version,
        words: changed ? `${l.name} is now version 1: 3 entries; 3 added, 0 changed, 0 delisted`
                       : `${l.name} is unchanged at version ${l.version}: no new version was kept` });  // prettier-ignore
    }
    const schedule = path.match(/^\/v1\/studio\/screening-lists\/(.+)\/schedule$/);
    if (schedule) {
      const l = lists.find((x) => x.id === schedule[1])!;
      const s = (body?.schedule ?? null) as Body | null;
      l.schedule = s;
      l.schedule_words = s ? (s.every === "weekly" ? `every week on day ${String(s.weekday)} at ${String(s.hour).padStart(2, "0")}:00` : `every day at ${String(s.hour).padStart(2, "0")}:00`) : null;
      return json(r, list(l));
    }
    if (path === "/v1/datasets/ds-a/source-files") {
      return json(r, { root: "/in", files: [{ name: "estabs.csv", source_location: "/in/uploaded/ds-a/estabs.csv", size_bytes: 1, modified_at: 1 }] });
    }
    if (path === "/v1/datasets/ds-a/reference-lists/rl-est/import") {
      return json(r, { list_id: "rl-est", outcome: "updated", version: 2, words: "establishments is now version 2" });
    }
    if (path === "/v1/ingest/connections") {
      return json(r, [{ id: "files", kind: "files", name: "Files: the ingest root", created_by: "system", created_at: "" },
                      { id: "c-sql", kind: "sql", name: "NOMIS replica (synthetic)", created_by: "adm-1", created_at: "" },
                      { id: "c-api", kind: "api", name: "Telco lookup (synthetic)", created_by: "adm-1", created_at: "" },
                      { id: "c-json", kind: "json", name: "Bookings files", created_by: "adm-1", created_at: "" }]);  // prettier-ignore
    }
    if (path === "/v1/datasets/ds-a/sources" && method === "POST") {
      if (body?.connection_id !== "files" && (body?.read as Body | null)?.kind !== String(body?.connection_id).slice(2)) return json(r, { detail: { detail: "A source on a sql connection needs its own read." } }, 422);
      return json(r, { ...body, id: "src-new", dataset_id: "ds-a", location: `/in/uploaded/ds-a/${String(body?.location)}.csv`,
        version: 1, created_by: "eng-1", created_at: "2026-11-08T09:00:00Z" }, 201);  // prettier-ignore
    }
    if (path === "/v1/datasets/ds-a/sources/src-bookings/read") {
      return json(r, { source_id: "src-bookings", file: "/in/uploaded/ds-a/visit_bookings.csv", rows: 2, cursor: "5",
                       words: "2 rows read into visit_bookings.csv" });  // prettier-ignore
    }
    if (path.endsWith("/profile")) return json(r, { columns: [], rows_sampled: 0 });
    if (path.endsWith("/lineage")) return json(r, []);
    return json(r, {}, 404);
  });
  return state;
}

async function focused(page: Page): Promise<string> {
  return page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return "";
    const own = el.getAttribute("aria-label") ?? "";
    if (own) return own;
    const label = el.closest("label")?.querySelector(".label")?.textContent ?? "";
    return label || (el.textContent ?? "");
  });
}

async function tabTo(page: Page, name: RegExp, max = 60) {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (name.test((await focused(page)).trim())) return;
  }
  throw new Error(`Tab never reached ${String(name)}`);
}

async function typeInto(page: Page, label: RegExp, text: string) {
  await tabTo(page, label);
  await page.keyboard.type(text);
}

test("a dataset subscribes to a list by its id, and reads it", async ({ page }) => {
  const state = await serve(page);
  await page.goto(HARNESS);
  await tabTo(page, /^Subscribe this dataset to OFAC SDN \(synthetic\)$/);
  await page.keyboard.press("Space");
  await expect(page.getByRole("status")).toHaveText("This dataset now reads OFAC SDN (synthetic).");
  expect(state.asked.filter((a) => a.method === "PUT").map((a) => a.path)).toEqual(["/v1/datasets/ds-a/screening-subscriptions/01OFAC"]);
  await expect(page.getByRole("list", { name: "Lists this dataset reads" })).toContainText("OFAC SDN (synthetic), version 1 (deployment-wide, subscribed)");
  await expect(page.getByRole("button", { name: "Refresh now: OFAC SDN (synthetic)" })).toHaveCount(0);
  registerCovered(REGISTRY, "subscribe-a-dataset-to-a-screening-list-by-keyboard");
});

test("a list is imported through a format's template, refreshed now, and scheduled", async ({ page }) => {
  const state = await serve(page, { canManage: true });
  await page.goto(HARNESS);
  await tabTo(page, /^Import a list$/);
  await page.keyboard.press("Enter");
  await typeInto(page, /^List name$/, "UK list (synthetic)");
  await tabTo(page, /^Template$/);
  await page.getByRole("combobox", { name: "Template" }).selectOption("uk_sanctions_list");
  await typeInto(page, /^File in the ingest folder$/, "lists/uksl.xml");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("UK list (synthetic) is now version 1: 3 entries; 3 added, 0 changed, 0 delisted");
  const added = state.asked.find((a) => a.method === "POST" && a.path === "/v1/studio/screening-lists");
  expect(added?.body).toEqual({ name: "UK list (synthetic)", template: "uk_sanctions_list", location: "lists/uksl.xml", mapping: null });
  registerCovered(REGISTRY, "import-a-screening-list-through-a-template-by-keyboard");

  await page.locator("body").focus();
  await tabTo(page, /^Refresh now: UK list \(synthetic\)$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("UK list (synthetic) is unchanged at version 1: no new version was kept");
  registerCovered(REGISTRY, "refresh-a-screening-list-now-by-keyboard");

  await page.locator("body").focus();
  await tabTo(page, /^Schedule UK list \(synthetic\)$/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Refresh$/);
  await page.getByRole("combobox", { name: "Refresh" }).selectOption("weekly");
  await tabTo(page, /^On$/);
  await page.getByRole("combobox", { name: "On" }).selectOption("3");
  await tabTo(page, /^At \(UK time\)$/);
  await page.getByRole("combobox", { name: "At (UK time)" }).selectOption("6");
  await tabTo(page, /^Save schedule$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("UK list (synthetic): refreshed every week on day 3 at 06:00.");
  const scheduled = state.asked.find((a) => a.method === "PUT" && a.path.endsWith("/schedule"));
  expect(scheduled?.body).toEqual({ schedule: { every: "weekly", hour: 6, weekday: 3 } });
  registerCovered(REGISTRY, "schedule-a-screening-lists-refresh-by-keyboard");
});

test("a client's own list is imported through the blank template's column picks", async ({ page }) => {
  const state = await serve(page, { canManage: true });
  await page.goto(HARNESS);
  await tabTo(page, /^Import a list$/);
  await page.keyboard.press("Enter");
  await typeInto(page, /^List name$/, "Client list");
  await tabTo(page, /^Template$/);
  await page.getByRole("combobox", { name: "Template" }).selectOption("blank");
  await typeInto(page, /^File in the ingest folder$/, "client.csv");
  await typeInto(page, /^Reference column$/, "Client ref");
  await typeInto(page, /^Name column$/, "Full name");
  await typeInto(page, /^Aliases column \(optional\)$/, "Other names");
  await tabTo(page, /^Many values in one cell are separated by$/);
  await page.getByRole("combobox", { name: "Many values in one cell are separated by" }).selectOption(",");
  await tabTo(page, /^Each row is$/);
  await page.getByRole("combobox", { name: "Each row is" }).selectOption("column");
  await typeInto(page, /^Party type column$/, "Party type");
  await tabTo(page, /^Add and import$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("Client list is now version 1: 3 entries; 3 added, 0 changed, 0 delisted");
  const added = state.asked.find((a) => a.method === "POST" && a.path === "/v1/studio/screening-lists");
  expect((added?.body as Body).mapping).toEqual({
    ref: "Client ref", primary_name: "Full name", aliases: "Other names", date_of_birth: null, nationality: null,
    identifiers: null, programme: null, separator: ",", entity_type: null, entity_type_column: "Party type", listing: "sanction",
  });  // prettier-ignore
  registerCovered(REGISTRY, "import-a-client-list-through-the-blank-template-by-keyboard");
});

test("a dataset's own list's rows are imported from one of its files", async ({ page }) => {
  const state = await serve(page);
  await page.goto(HARNESS);
  await tabTo(page, /^Import rows for one of this dataset's lists$/);
  await page.keyboard.press("Enter");
  await typeInto(page, /^The list's id, as the domain model names it$/, "rl-est");
  await tabTo(page, /^File$/);
  await page.getByRole("combobox", { name: "File" }).selectOption("/in/uploaded/ds-a/estabs.csv");
  await tabTo(page, /^Import rows$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("establishments is now version 2");
  const sent = state.asked.find((a) => a.path.endsWith("/reference-lists/rl-est/import"));
  expect(sent?.body).toEqual({ location: "/in/uploaded/ds-a/estabs.csv", name: null, key_column: null });
  registerCovered(REGISTRY, "import-a-datasets-own-list-rows-by-keyboard");
});

test("a source is registered through a SQL connection by its read", async ({ page }) => {
  const state = await serve(page);
  await page.goto(`${HARNESS}?view=wizard`);
  await tabTo(page, /^Connection$/);
  await page.getByRole("combobox", { name: "Connection" }).selectOption("c-sql");
  await tabTo(page, /^Next$/);
  await page.keyboard.press("Enter");
  await typeInto(page, /^Source name$/, "Visit bookings");
  await typeInto(page, /^Table or view \(schema\.name\)$/, "nomis.visit_bookings");
  await tabTo(page, /^Next$/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Classification$/);
  await page.getByRole("combobox", { name: "Classification" }).selectOption("OFFICIAL");
  await expect(page.getByRole("heading", { name: "Register a source" })).toBeVisible();
  const steps = await page.getByRole("list", { name: "Steps" }).textContent();
  expect(steps).toContain("What to read");
  // Governance is completed as the sources spec does it; the read is what this case proves.
  const fill = async (label: RegExp, value: string) => {
    await tabTo(page, label);
    const el = page.locator(":focus");
    if ((await el.evaluate((e) => e.tagName)) === "SELECT") await el.selectOption(value);
    else await page.keyboard.type(value);
  };
  await fill(/^Handling code$/, "P");
  await fill(/^Originator$/, "unit-1");
  await fill(/^Owning unit$/, "unit-1");
  await fill(/^Legal basis$/, "Synthetic demonstration");
  await tabTo(page, /^Register$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__SOURCES__?.registered.length)).toBe(1);
  const sent = state.asked.find((a) => a.method === "POST" && a.path === "/v1/datasets/ds-a/sources");
  expect(sent?.body).toMatchObject({ connection_id: "c-sql", location: "visit_bookings",
    read: { kind: "sql", table: "nomis.visit_bookings", columns: [] } });  // prettier-ignore
  registerCovered(REGISTRY, "register-a-source-through-a-sql-connection-by-keyboard");
});

/** Through the wizard to Register on a connection, with the read step filled by `fillRead`. */
async function registerThrough(page: Page, connection: string, fillRead: () => Promise<void>) {
  await page.goto(`${HARNESS}?view=wizard`);
  await tabTo(page, /^Connection$/);
  await page.getByRole("combobox", { name: "Connection" }).selectOption(connection);
  await tabTo(page, /^Next$/);
  await page.keyboard.press("Enter");
  await fillRead();
  await tabTo(page, /^Next$/);
  await page.keyboard.press("Enter");
  for (const [label, value] of [
    [/^Classification$/, "OFFICIAL"], [/^Handling code$/, "P"], [/^Originator$/, "unit-1"],
    [/^Owning unit$/, "unit-1"], [/^Legal basis$/, "Synthetic demonstration"],
  ] as const) {
    await tabTo(page, label);
    const el = page.locator(":focus");
    if ((await el.evaluate((e) => e.tagName)) === "SELECT") await el.selectOption(value);
    else await page.keyboard.type(value);
  }  // prettier-ignore
  await tabTo(page, /^Register$/);
  await page.keyboard.press("Enter");
  await expect.poll(() => page.evaluate(() => window.__SOURCES__?.registered.length)).toBe(1);
}

test("a source is registered through an API connection by its read", async ({ page }) => {
  const state = await serve(page);
  await registerThrough(page, "c-api", async () => {
    await typeInto(page, /^Source name$/, "Telco numbers");
    await typeInto(page, /^Path under the connection's address$/, "/v1/numbers");
    await typeInto(page, /^Where the records are/, "data.items");
  });
  const sent = state.asked.find((a) => a.method === "POST" && a.path === "/v1/datasets/ds-a/sources");
  expect(sent?.body).toMatchObject({ connection_id: "c-api", location: "telco_numbers",
    read: { kind: "api", path: "/v1/numbers", records_at: "data.items" } });  // prettier-ignore
  registerCovered(REGISTRY, "register-a-source-through-an-api-connection-by-keyboard");
});

test("a source is registered through a JSON connection by its read", async ({ page }) => {
  const state = await serve(page);
  await registerThrough(page, "c-json", async () => {
    await typeInto(page, /^Source name$/, "Bookings");
    await typeInto(page, /^File names to read/, "bookings-*.json");
    await typeInto(page, /^Where the records are/, "records");
  });
  const sent = state.asked.find((a) => a.method === "POST" && a.path === "/v1/datasets/ds-a/sources");
  expect(sent?.body).toMatchObject({ connection_id: "c-json", location: "bookings",
    read: { kind: "json", pattern: "bookings-*.json", records_at: "records" } });  // prettier-ignore
  registerCovered(REGISTRY, "register-a-source-through-a-json-connection-by-keyboard");
});

test("a dataset unsubscribes from a list, and no longer reads it", async ({ page }) => {
  const state = await serve(page);
  await page.goto(HARNESS);
  await tabTo(page, /^Subscribe this dataset to OFAC SDN \(synthetic\)$/);
  await page.keyboard.press("Space");
  await expect(page.getByRole("status")).toHaveText("This dataset now reads OFAC SDN (synthetic).");
  await page.keyboard.press("Space");
  await expect(page.getByRole("status")).toHaveText("This dataset no longer reads OFAC SDN (synthetic).");
  expect(state.asked.filter((a) => a.method === "DELETE").map((a) => a.path)).toEqual(["/v1/datasets/ds-a/screening-subscriptions/01OFAC"]);
  await expect(page.getByRole("list", { name: "Lists this dataset reads" })).not.toContainText("OFAC");
  registerCovered(REGISTRY, "unsubscribe-a-dataset-from-a-screening-list-by-keyboard");
});

test("a list's schedule is stopped, so it is refreshed by hand only", async ({ page }) => {
  const state = await serve(page, { canManage: true });
  await page.goto(HARNESS);
  await tabTo(page, /^Schedule OFAC SDN \(synthetic\)$/);
  await page.keyboard.press("Enter");
  await tabTo(page, /^Refresh by hand only$/);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toHaveText("OFAC SDN (synthetic): refreshed by hand only.");
  const stopped = state.asked.find((a) => a.method === "PUT" && a.path.endsWith("/schedule"));
  expect(stopped?.body).toEqual({ schedule: null });
  registerCovered(REGISTRY, "refresh-a-screening-list-by-hand-only-by-keyboard");
});

test("a SQL source is read again by Refresh now", async ({ page }) => {
  const state = await serve(page);
  await page.goto(`${HARNESS}?view=source`);
  await tabTo(page, /^Refresh now$/);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Read again: 2 rows read into visit_bookings.csv.")).toBeVisible();
  expect(state.asked.filter((a) => a.method === "POST").map((a) => a.path)).toEqual(["/v1/datasets/ds-a/sources/src-bookings/read"]);
  registerCovered(REGISTRY, "refresh-a-connector-source-now-by-keyboard");
});

test("every registered Sources connector action has its own proving test case above", () => {
  assertAllCovered("SOURCES_CONNECTORS_ACTIONS", SOURCES_CONNECTORS_ACTIONS);
});
