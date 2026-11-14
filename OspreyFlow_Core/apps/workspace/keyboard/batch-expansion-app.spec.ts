// The batch job's panel (ADR-151) under axe inside the real Glass, in the three looks: the App's own layout, not a
// harness. `batch-expansion.spec.ts` scans the panel alone, and `canvas-expand-cap.spec.ts` over the canvas harness;
// what neither can see is what only the App draws around a panel fixed at the page's foot: here the canvas with its
// corner controls, the status bar (with the case's withheld sentence), the rail and the classification strip. No
// drawer is open and no phase banner shown, so neither is claimed. The real `/` is signed in through a fake identity
// provider (`fakeIdentityProvider.ts`), its case opened from the tab, its two nodes delivered on the case's delta
// stream (a routed WebSocket answering the handshake with the reader's full snapshot, `withheld` set as `sync`
// sets it), and the panel opened as a reader opens it, by keyboard: a node selected, its expansion counted by the
// preview past the confirm gate and past the cap (`would_breach`, as the Conduit counts both from the same view),
// *Add all* confirmed, `/expand` refused by the cap's 409, then *Run as a batch job*. The Conduit is faked with
// what the case's workspace reads; its batch routes answer as rules-b's route does (`services/api/app.py`'s batch
// expansions): a start that is not the refused expansion, or not signed, is refused. Anything else is a 404.
// Each of the panel's three standing states — running, failed, done — is scanned in dark, light and GOV.UK through
// `checkUndecidedContrast`. Over the App's page axe leaves the panel's words' contrast undecided
// ("elmPartiallyObscuring", the fixed panel over the canvas), so a scan reading only `violations` would pass them
// unmeasured. No keyboard action is new (the panel's are `batch-expansion.spec.ts`'s), so this file registers none.
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

async function fakeConduit(page: Page, ending: Ending): Promise<{ starts: unknown[] }> {
  const starts: unknown[] = [];
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
    // The handshake (`last_acknowledged_seq`) is answered with the case as this reader may see it: `sync`'s full
    // snapshot, which always says whether anything is withheld (ADR-124 decision 5).
    ws.onMessage(() => ws.send(JSON.stringify({ seq: 1, op: "snapshot", nodes: NODES, edges: [], withheld: true })));
  });
  // The expansion as the Conduit counts it, from the same projected view as `/expand`: past the confirm gate, and
  // past the cap, which the preview names (`would_breach`) and `/expand` then refuses.
  await page.route(`${API}/v1/investigations/${CASE}/expand/preview`, (route) =>
    route.fulfill({ json: { candidate_node_count: 6210, candidate_edge_count: 9004, link_count: 0, would_breach: REFUSED } }),
  );
  await page.route(`${API}/v1/investigations/${CASE}/expand`, (route) => route.fulfill({ status: 409, json: REFUSED }));
  await page.route(`${API}/v1/investigations/${CASE}/batch-expansions`, (route) => {
    const request = route.request();
    if (!request.headers()["authorization"]?.startsWith("Bearer ")) return route.fulfill({ status: 401, json: { detail: "Not signed in." } });
    if (request.method() !== "POST") return route.fulfill({ status: 405, json: { detail: "Method Not Allowed" } });
    const body = request.postDataJSON() as unknown;
    starts.push(body);
    // `BatchExpansionInput` is `extra="forbid"`: anything but the refused expansion is the route's 422 here.
    if (JSON.stringify(body) !== JSON.stringify({ request: { node_ids: ["p1"], depth: 1, edge_types: null } }))
      return route.fulfill({ status: 422, json: { detail: "not the refused expansion" } });
    return route.fulfill({ status: 202, json: job("queued", "Waiting for the batch expansion to start.") });
  });
  await page.route(`${API}/v1/investigations/${CASE}/batch-expansions/j1`, (route) => route.fulfill({ json: ENDS[ending] }));
  return { starts };
}

/** Tab, from where focus is, to `button` within the dialog the reader is in, then Enter. */
async function reachAndPress(page: Page, button: ReturnType<Page["getByRole"]>): Promise<void> {
  for (let i = 0; i < 20 && !(await button.evaluate((el) => el === document.activeElement)); i++) await page.keyboard.press("Tab");
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

async function openThePanelInTheApp(page: Page, ending: Ending, look: "dark" | "light" | "govuk"): Promise<unknown[]> {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await fakeIdentityProvider(page, { session: true, silentRounds: 0 });
  const { starts } = await fakeConduit(page, ending);
  await page.addInitScript((light) => {
    sessionStorage.setItem("ospreyflow.investigationId", "case-1");
    sessionStorage.setItem("ospreyflow.place", "case");
    localStorage.setItem("ospreyflow.welcome-closed.analyst-1", "1");
    // The reader's own choice of theme (`theme/theme.ts`), so the App applies it at load, canvas and all.
    if (light) localStorage.setItem("ospreyflow.theme", "light");
  }, look === "light");
  // `?brand=govuk` is the development build's way to the GOV.UK look (`brand/brand.ts`'s `brandFromUrl`).
  await page.goto(look === "govuk" ? "/?brand=govuk" : "/");
  const canvas = page.getByRole("application", { name: "Network canvas" });
  await expect(canvas).toBeVisible({ timeout: 20_000 });
  // Both of the case's nodes on the canvas (its status line counts them; not "12 nodes"), one selected by keyboard.
  await expect(page.getByRole("status").filter({ hasText: /(^|\D)2\s*nodes/ })).not.toHaveCount(0);
  await canvas.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Enter");
  const gate = page.getByRole("alertdialog", { name: "Large expansion" });
  // The preview counts the view the expansion would make; the gate says what it adds to the two already drawn.
  await expect(gate).toContainText("This would add 6,208 nodes");
  await reachAndPress(page, gate.getByRole("button", { name: "Add all 6,208", exact: true }));
  const refusal = page.getByRole("alertdialog", { name: "Too large to expand" });
  await expect(refusal).toBeVisible();
  await reachAndPress(page, refusal.getByRole("button", { name: "Run as a batch job", exact: true }));
  return starts;
}

// Found by its class until it has been scanned, so the scan runs on whatever the App drew.
const drawn = (page: Page) => page.locator(".batch-expansion");
const panel = (page: Page) => page.getByRole("region", { name: "Batch job: the whole expansion" });
const DRAWN: Record<Ending, (page: Page) => Promise<void>> = {
  running: (page) => expect(drawn(page).locator(".batch-expansion__status")).toHaveText("Expanding from 1 node."),
  failed: (page) => expect(drawn(page).locator("button", { hasText: "Try the batch job again" })).toBeVisible(),
  done: (page) => expect(drawn(page).locator("button", { hasText: "Open the view" })).toBeVisible(),
};

for (const look of ["dark", "light", "govuk"] as const) {
  for (const ending of ["running", "failed", "done"] as const) {
    test(`the batch job's panel in the App, ${ending}, has no automated WCAG 2.2 A or AA violation (${look})`, async ({ page }) => {
      test.setTimeout(90_000);
      const starts = await openThePanelInTheApp(page, ending, look);
      await DRAWN[ending](page);
      expect(starts, "the job started was the refused expansion, once").toEqual([{ request: { node_ids: ["p1"], depth: 1, edge_types: null } }]);
      // Nothing of the App's covers the panel: its heading, each line of its words and each of its buttons is the
      // topmost thing at its centre. Pointer events are lifted for the test, as `undecidedContrast.ts` lifts them,
      // so an overlay that lets the pointer through (a tooltip, the canvas's corner) is still found; pseudo-elements
      // too, which `*` alone does not match (an App element's `::after` drawn over the panel was missed without).
      const lift = await page.addStyleTag({ content: "*, *::before, *::after { pointer-events: auto !important; }" });
      const lines = drawn(page).locator(".batch-expansion__title, .batch-expansion__figure, .batch-expansion__status, .batch-expansion__message, button");
      for (const target of await lines.all()) {
        if (!(await target.textContent())?.trim()) continue;
        const onTop = await target.evaluate((el) => {
          const box = el.getBoundingClientRect();
          const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
          return hit !== null && (el === hit || el.contains(hit));
        });
        expect(onTop, `${await target.textContent()} is covered by the App's layout`).toBe(true);
      }
      await lift.evaluate((el) => el.remove());
      // The look is the one asked for when scanned.
      if (look === "light") await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
      if (look === "govuk") await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
      const results = await new AxeBuilder({ page }).include(".batch-expansion").withTags(WCAG_TAGS).analyze();
      expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      const contrast = await checkUndecidedContrast(page, results);
      expect(contrast.unlisted, "colour contrast axe left undecided").toEqual([]);
      // And as a reader reaches it: the region named by its own heading, the heading holding focus from the refusal's
      // choice. This is what finds the App's markup hiding the panel (an `aria-hidden` ancestor: axe's scan is held to
      // the panel by `include` and does not see one outside it), or naming it with another element's words (no axe
      // rule in these tags requires a region's name to be its heading's).
      await expect(panel(page).getByRole("heading", { name: "Batch job: the whole expansion" })).toBeFocused();
    });
  }
}
