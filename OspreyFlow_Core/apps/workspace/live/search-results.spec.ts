// **The search results page against the real search route (ADR-145 Amendment 15 Part A, ADR-149).**
//
// The jsdom and keyboard tests drive `SearchResults` against a fake answer. This file asks the real
// Conduit's `POST /v1/investigations/{id}/search`, so it shows what the fake cannot (rule 15's second
// worked example): that the route accepts the exact bodies the page sends, that it refuses what the
// page must say it refused, and that the counts on screen are the route's own (rule 7).
//
// Opt in as every live spec does (`live.ts`): OSPREY_TEST_LIVE_GLASS=1 and the three OSPREY_LIVE_*
// variables, against a stack holding Fixture Corp. OSPREY_LIVE_INVESTIGATION_ID must be the case Fixture Corp was
// seeded into (`seed_fixture_corp --investigation-scope`): the seed is what makes a case read its dataset (ADR-099),
// and a fresh case reads none, so search there finds nothing (`search_access.py`: "An empty case sees nothing").
// Only Show on graph changes the case's working set, so it runs on a case no earlier case of this file has seeded.
import { type APIRequestContext, expect, type Page, test } from "@playwright/test";
import { apiBaseUrl, investigationId, liveOnly, required, workspaceUrl } from "./live";

test.beforeEach(liveOnly);

/** Fixture Corp's first resolution pair: an identifier the search is sure to find. */
const QUERY = "QQ118439C";
const PAGE_SIZE = 20;

const box = (page: Page) => page.locator('.top-bar [role="combobox"]');
const results = (page: Page) => page.locator("section.search-results");

async function ask(request: APIRequestContext, investigation: string, body: Record<string, unknown>) {
  return request.post(`${apiBaseUrl()}/v1/investigations/${encodeURIComponent(investigation)}/search`, {
    headers: { Authorization: `Bearer ${required("OSPREY_LIVE_BEARER_TOKEN")}` },
    data: body,
  });
}

async function search(page: Page, words: string): Promise<void> {
  await box(page).fill(words);
  await box(page).press("Enter");
  await expect(results(page)).toBeVisible({ timeout: 30_000 });
}

test("Enter opens the results, and the total on screen is the route's own", async ({ page, request }) => {
  await page.goto(workspaceUrl());
  await search(page, QUERY);

  const answer = await ask(request, investigationId(), { query: QUERY, group: null, filters: {}, page: 1, page_size: PAGE_SIZE });
  expect(answer.status(), await answer.text()).toBe(200);
  const body = (await answer.json()) as { total: number; counts_exact: boolean; source: string };
  expect(body.total).toBeGreaterThan(0);
  const records = body.total === 1 ? "1 record" : `${body.total} records`;
  await expect(results(page).locator(".search-results__total")).toHaveText(
    `${records}${body.counts_exact ? "" : " (counts may be incomplete)"}`,
  );
  if (body.source === "fallback") await expect(results(page).locator(".search-results__limited")).toBeVisible();
});

test("every body the page sends is one the route accepts", async ({ page }) => {
  await page.goto(workspaceUrl());
  const sent: unknown[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && /\/search$/.test(new URL(r.url()).pathname)) sent.push(r.postDataJSON());
  });
  const refused: number[] = [];
  page.on("response", (r) => {
    if (r.request().method() === "POST" && /\/search$/.test(new URL(r.url()).pathname) && !r.ok()) refused.push(r.status());
  });

  await search(page, QUERY);
  const groups = results(page).getByRole("group", { name: "Result groups" }).getByRole("button");
  if ((await groups.count()) > 1) await groups.nth(1).click();
  const dataset = results(page).getByRole("checkbox").first();
  if (await dataset.count()) await dataset.check();
  await expect(results(page)).toBeVisible();

  expect(sent.length).toBeGreaterThan(0);
  expect(refused, `the route refused bodies the page sent: ${JSON.stringify(sent)}`).toEqual([]);
});

test("Show on graph sends the result's records to the case's working set, and the Conduit takes them", async ({ page, request }) => {
  // What the page sends is held to what the route answered: every record the first result stands for, by id. Read
  // from the network, not the screen: the Conduit's working set is what Show on graph changes (`/seed`).
  const answer = await ask(request, investigationId(), { query: QUERY, group: null, filters: {}, page: 1, page_size: PAGE_SIZE });
  expect(answer.status(), await answer.text()).toBe(200);
  const first = ((await answer.json()) as { results: { node_ids: string[] }[] }).results[0];
  expect(first, `the route found nothing for ${QUERY}`).toBeDefined();

  await page.goto(workspaceUrl());
  await search(page, QUERY);
  const seeded = page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname.endsWith("/seed"));
  await results(page).getByRole("button", { name: /^Show on graph: / }).first().click();
  const response = await seeded;
  expect(response.status(), await response.text()).toBeLessThan(300);
  const sent = (response.request().postDataJSON() as { nodes: { id: string }[] }).nodes.map((n) => n.id).sort();
  expect(sent).toEqual([...first!.node_ids].sort());
  await expect(results(page)).toBeHidden();
  await expect(page.getByRole("application", { name: "Network canvas" })).toBeVisible();
});

test("a query longer than the route takes is refused on screen with the limit named, never cut (rule 2)", async ({ page }) => {
  // The route refuses more than 200 characters (`schemas/search.py`'s MAX_QUERY_CHARS) with FastAPI's 422, whose
  // detail is a list; the page names the limit from it. The jsdom and keyboard cases prove the words against the body
  // as measured from the model; this one proves the real route still sends that body.
  await page.goto(workspaceUrl());
  await search(page, "a".repeat(201));
  await expect(results(page).getByRole("alert")).toContainText(
    "The search could not be done: a search can be at most 200 characters, and this one has 201.",
    { timeout: 30_000 },
  );
});
