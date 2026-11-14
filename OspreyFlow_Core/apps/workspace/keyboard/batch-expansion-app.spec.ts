// The batch job's panel (ADR-151) under axe inside the real Glass, in the three looks: the App's own layout, not a
// harness. `batch-expansion.spec.ts` scans the panel alone, and `canvas-expand-cap.spec.ts` over the canvas harness;
// what neither can see is what only the App draws around it — the rail, the timeline, the banners, the drawers, the
// page's own stacking — over or under a panel fixed at the page's foot. Here the real `/` is signed in through a
// fake identity provider (`fakeIdentityProvider.ts`), its case opened from the tab, a node delivered on the case's
// delta stream (a routed WebSocket, its snapshot in the Conduit's shape), and the panel opened as a reader opens it:
// the canvas's own expansion refused by the cap's 409, then *Run as a batch job*, by keyboard. The Conduit is faked
// with what the case's workspace reads, its batch routes answering as rules-b's route does
// (`services/api/app.py`'s batch expansions); anything else is a 404, as a route the fake does not know.
// Each of the panel's three standing states — running, failed, done — is scanned in dark, light and GOV.UK, through
// `checkUndecidedContrast` (rule 15: a scan reading only `violations` passes 1:1 text). No keyboard action is new
// (the panel's are `batch-expansion.spec.ts`'s), so this file registers none.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkUndecidedContrast } from "../a11y/undecidedContrast";
import { API, fakeIdentityProvider } from "./fakeIdentityProvider";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const CASE = "case-1";
const REFUSED = { error: "limit_exceeded", cap_kind: "nodes", cap: 5000, would_be: 6210, options: ["save_as_view", "filter", "promote_to_batch"] };
const NODES = ["Kestrel", "Harrier"].map((name, i) => ({
  id: `p${i + 1}`,
  type: "Person",
  properties: { family_name: name },
  source_system_ids: [],
  provenance: { sources: [] },
  classification: "OFFICIAL",
  handling: [],
}));
const VIEW = { id: "v-batch", case_id: CASE, name: "Kestrel, expanded", created_by: "analyst-1", created_at: "2026-11-14T10:00:00Z", shared: false, chosen: 2 };

type Ending = "running" | "failed" | "done";
const job = (state: string, words: string, more: Record<string, unknown> = {}) => ({ id: "j1", state, words, view: null, nodes: null, links: null, refusal: null, ...more });
const ENDS: Record<Ending, object> = {
  running: job("running", "Expanding from 1 node."),
  failed: job("failed", "The batch expansion could not finish, and nothing was saved. Try again, or narrow the expansion."),
  done: job("done", "Saved 6,210 nodes and 9,004 links as your private view “Kestrel, expanded”.", { view: VIEW, nodes: 6210, links: 9004 }),
};

async function fakeConduit(page: Page, ending: Ending): Promise<void> {
  // Registered first, so the routes below (later, so first matched) answer what they name.
  await page.route(`${API}/**`, (route) => route.fulfill({ status: 404, json: { detail: "not in this fake" } }));
  const answer = (path: string, json: unknown) => page.route(`${API}${path}`, (route) => route.fulfill({ json }));
  await answer("/v1/me", { id: "analyst-1", clearance: "OFFICIAL", org_unit: "unit-a", roles: [], receivable_handling_codes: [] });
  await answer("/v1/me/rights", { rights: ["investigate"] });
  await answer("/v1/ontology", { version: 1, entity_types: [{ name: "Person", pole_class: "person", channel: "cyan", shape: "circle", properties: [] }], edge_types: [] });
  await answer("/v1/map/providers", { default: "none", providers: [] });
  await answer("/v1/handling-scheme", { classification: ["OFFICIAL"], handling_codes: {} });
  const theCase = { id: CASE, name: "Kestrel case", level: "editor", created_at: "2026-11-01T09:00:00Z", created_by: "analyst-1" };
  await answer("/v1/investigations", [theCase]);
  await answer(`/v1/investigations/${CASE}`, theCase);
  await answer(`/v1/investigations/${CASE}/datasets`, []);
  await answer("/v1/ws-ticket", { ticket: "t1" });
  await page.routeWebSocket(/\/v1\/investigations\/case-1\/stream/, (ws) => {
    // The handshake (`last_acknowledged_seq`) is answered with the case as this reader may see it.
    ws.onMessage(() => ws.send(JSON.stringify({ seq: 1, op: "snapshot", nodes: NODES, edges: [] })));
  });
  // The canvas's expansion: under the expand gate's 500, so it is asked for, and refused by the cap.
  await page.route(`${API}/v1/investigations/${CASE}/expand/preview`, (route) =>
    route.fulfill({ json: { candidate_node_count: 40, candidate_edge_count: 0, link_count: 2 } }),
  );
  await page.route(`${API}/v1/investigations/${CASE}/expand`, (route) => route.fulfill({ status: 409, json: REFUSED }));
  await page.route(`${API}/v1/investigations/${CASE}/batch-expansions`, (route) =>
    route.fulfill({ status: 202, json: job("queued", "Waiting for the batch expansion to start.") }),
  );
  await page.route(`${API}/v1/investigations/${CASE}/batch-expansions/j1`, (route) => route.fulfill({ json: ENDS[ending] }));
}

async function openThePanelInTheApp(page: Page, ending: Ending, look: "dark" | "light" | "govuk"): Promise<void> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fakeIdentityProvider(page, { session: true, silentRounds: 0 });
  await fakeConduit(page, ending);
  await page.addInitScript(() => {
    sessionStorage.setItem("ospreyflow.investigationId", "case-1");
    sessionStorage.setItem("ospreyflow.place", "case");
    localStorage.setItem("ospreyflow.welcome-closed.analyst-1", "1");
  });
  // `?brand=govuk` is the development build's way to the GOV.UK look (`brand/brand.ts`'s `brandFromUrl`).
  await page.goto(look === "govuk" ? "/?brand=govuk" : "/");
  if (look === "govuk") await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect(canvas).toBeVisible({ timeout: 20_000 });
  if (look === "light") await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  // The case's nodes on the canvas (its status line counts them), one selected by keyboard, and its expansion
  // refused by the cap.
  await expect(page.getByRole("status").filter({ hasText: /nodes/ }).first()).toContainText("2");
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  const refusal = page.getByRole("alertdialog", { name: "Too large to expand" });
  await page.keyboard.press("Enter");
  await expect(refusal).toBeVisible();
  const run = refusal.getByRole("button", { name: "Run as a batch job", exact: true });
  for (let i = 0; i < 20 && !(await run.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(run).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Batch job: the whole expansion" })).toBeFocused();
}

const panel = (page: Page) => page.getByRole("region", { name: "Batch job: the whole expansion" });
const DRAWN: Record<Ending, (page: Page) => Promise<void>> = {
  running: (page) => expect(panel(page).getByRole("status")).toHaveText("Expanding from 1 node."),
  failed: (page) => expect(panel(page).getByRole("button", { name: "Try the batch job again" })).toBeVisible(),
  done: (page) => expect(panel(page).getByRole("button", { name: "Open the view" })).toBeVisible(),
};

for (const look of ["dark", "light", "govuk"] as const) {
  for (const ending of ["running", "failed", "done"] as const) {
    test(`the batch job's panel in the App, ${ending}, has no automated WCAG 2.2 A or AA violation (${look})`, async ({ page }) => {
      test.setTimeout(90_000);
      await openThePanelInTheApp(page, ending, look);
      await DRAWN[ending](page);
      // Nothing of the App's covers the panel: its heading and each of its buttons is the topmost thing at its centre.
      for (const target of [panel(page).getByRole("heading"), ...(await panel(page).getByRole("button").all())]) {
        const onTop = await target.evaluate((el) => {
          const box = el.getBoundingClientRect();
          const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
          return hit !== null && (el === hit || el.contains(hit));
        });
        expect(onTop, `${await target.textContent()} is covered by the App's layout`).toBe(true);
      }
      // The look is still the one asked for when scanned (the App applies its own theme at load).
      if (look === "light") await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
      if (look === "govuk") await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
      const results = await new AxeBuilder({ page }).include(".batch-expansion").withTags(WCAG_TAGS).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      const contrast = await checkUndecidedContrast(page, results);
      expect(contrast.unlisted, "colour contrast axe left undecided").toEqual([]);
    });
  }
}
