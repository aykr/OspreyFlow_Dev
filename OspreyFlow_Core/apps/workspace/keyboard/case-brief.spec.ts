// The case's brief by keyboard alone (ADR-128 decision 3, rule 13): the Author sets the priority
// requirement, adds a requirement, edits one (Escape cancels and returns focus to the button that
// opened it), marks one answered and reopens it, attaches a saved trend, detaches it and removes a
// requirement after confirming; and a person who only reads the case reaches an attachment and is
// offered no edit. No `page.mouse`, no `.click()`. Each step asserts the request sent and what is
// shown afterwards, which is read back from the server this spec plays.
import { expect, test, type Page } from "@playwright/test";

import { CASE_BRIEF_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

type Attachment = { kind: string; id: string; title: string };
type Requirement = { id: string; text: string; status: "open" | "answered"; answered_at: string | null; attachments: Attachment[] };

const TREND = { id: "t1", title: "Throw-overs by week" };

async function serve(page: Page, options: { level?: string; requirements?: Requirement[]; priority?: string } = {}) {
  const sent: { method: string; url: string; body: unknown }[] = [];
  const brief = { priority: options.priority ?? "", requirements: options.requirements ?? [] as Requirement[] };
  let next = brief.requirements.length;
  const json = (status: number, body: unknown) => ({ status, contentType: "application/json", body: JSON.stringify(body) });
  await page.route("**/*/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url()).pathname;
    const method = request.method();
    const body = method === "GET" ? undefined : request.postDataJSON();
    sent.push({ method, url, body });
    const base = "/v1/investigations/c1/brief";
    if (url === "/v1/investigations") {
      return route.fulfill(json(200, [{ id: "c1", name: "C", level: options.level ?? "author", created_at: "", created_by: "" }]));
    }
    if (url === base && method === "GET") return route.fulfill(json(200, brief));
    if (url === `${base}/priority` && method === "PUT") {
      brief.priority = (body as { text: string }).text;
      return route.fulfill(json(200, brief));
    }
    if (url === `${base}/requirements` && method === "POST") {
      next += 1;
      brief.requirements.push({ id: `r${next}`, text: (body as { text: string }).text, status: "open", answered_at: null, attachments: [] });
      return route.fulfill(json(201, brief));
    }
    const status = url.match(/^\/v1\/investigations\/c1\/brief\/requirements\/([^/]+)\/status$/);
    if (status && method === "PUT") {
      const found = brief.requirements.find((r) => r.id === status[1]);
      found!.status = (body as { status: "open" | "answered" }).status;
      found!.answered_at = found!.status === "answered" ? "2026-10-26T09:00:00Z" : null;
      return route.fulfill(json(200, brief));
    }
    const attach = url.match(/^\/v1\/investigations\/c1\/brief\/requirements\/([^/]+)\/attachments$/);
    if (attach && method === "POST") {
      const posted = body as { kind: string; id: string };
      brief.requirements.find((r) => r.id === attach[1])!.attachments.push({ ...posted, title: TREND.title });
      return route.fulfill(json(200, brief));
    }
    const detach = url.match(/^\/v1\/investigations\/c1\/brief\/requirements\/([^/]+)\/attachments\/([^/]+)\/([^/]+)$/);
    if (detach && method === "DELETE") {
      const found = brief.requirements.find((r) => r.id === detach[1])!;
      found.attachments = found.attachments.filter((a) => !(a.kind === detach[2] && a.id === detach[3]));
      return route.fulfill(json(200, brief));
    }
    const one = url.match(/^\/v1\/investigations\/c1\/brief\/requirements\/([^/]+)$/);
    if (one && method === "PUT") {
      brief.requirements.find((r) => r.id === one[1])!.text = (body as { text: string }).text;
      return route.fulfill(json(200, brief));
    }
    if (one && method === "DELETE") {
      brief.requirements = brief.requirements.filter((r) => r.id !== one[1]);
      return route.fulfill(json(200, brief));
    }
    if (url === "/v1/investigations/c1/trends" && method === "GET") return route.fulfill(json(200, [TREND]));
    return route.fulfill(json(404, {}));
  });
  await page.goto("/keyboard/case-brief-harness.html");
  return { sent, brief };
}

const opened = (page: Page) => page.evaluate(() => window.__CASE_BRIEF__?.opened);
const requirement = (id: string, text: string, over: Partial<Requirement> = {}): Requirement => ({
  id,
  text,
  status: "open",
  answered_at: null,
  attachments: [],
  ...over,
});

test("the Author sets the priority requirement with Ctrl+Enter and focus returns to its button", async ({ page }) => {
  const { sent } = await serve(page);
  const section = page.getByRole("region", { name: "Brief" });
  await section.getByRole("button", { name: "Edit the priority requirement" }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByRole("textbox", { name: "Priority information requirement" })).toBeFocused();
  await page.keyboard.type("Who is orchestrating the throw-overs?");
  await page.keyboard.press("Control+Enter");
  await expect(section.getByText("Who is orchestrating the throw-overs?")).toBeVisible();
  expect(sent.find((s) => s.method === "PUT")?.body).toEqual({ text: "Who is orchestrating the throw-overs?" });
  await expect(section.getByRole("button", { name: "Edit the priority requirement" })).toBeFocused();
  registerCovered("CASE_BRIEF_ACTIONS", "set-the-priority-requirement-by-keyboard");
});

test("the Author adds a requirement by keyboard, with Ctrl+Enter and with the Add button", async ({ page }) => {
  const { sent } = await serve(page);
  const section = page.getByRole("region", { name: "Brief" });
  await section.getByRole("button", { name: "Add a requirement" }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByRole("textbox", { name: "New information requirement" })).toBeFocused();
  await page.keyboard.type("Who orchestrates the throw-overs?");
  await page.keyboard.press("Control+Enter");
  await expect(section.getByText("Who orchestrates the throw-overs?")).toBeVisible();
  expect(sent.find((s) => s.method === "POST")?.body).toEqual({ text: "Who orchestrates the throw-overs?" });
  // Focus is back on the button that opened the field; the button path adds a second.
  await expect(section.getByRole("button", { name: "Add a requirement" })).toBeFocused();
  await page.keyboard.press("Enter");
  await page.keyboard.type("Where and when do the packages arrive?");
  await section.getByRole("button", { name: "Add", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByText("Where and when do the packages arrive?")).toBeVisible();
  expect(sent.filter((s) => s.method === "POST").map((s) => s.body)).toEqual([
    { text: "Who orchestrates the throw-overs?" },
    { text: "Where and when do the packages arrive?" },
  ]);
  registerCovered("CASE_BRIEF_ACTIONS", "add-a-requirement-by-keyboard");
});

test("the Author edits a requirement by keyboard, and Escape cancels and returns focus to Edit", async ({ page }) => {
  const { sent } = await serve(page, { requirements: [requirement("r1", "Draft requirement")] });
  const section = page.getByRole("region", { name: "Brief" });
  await section.getByRole("button", { name: "Edit requirement 1" }).focus();
  await page.keyboard.press("Enter");
  const box = section.getByRole("textbox", { name: "Requirement 1" });
  await expect(box).toBeFocused();
  await box.fill("Dropped on Escape"); // text entry, not an activation: the keys below are
  await page.keyboard.press("Escape");
  await expect(box).toHaveCount(0);
  await expect(section.getByRole("button", { name: "Edit requirement 1" })).toBeFocused();
  await expect(section.getByText("Draft requirement")).toBeVisible();
  expect(sent.some((s) => s.method === "PUT")).toBe(false);
  registerCovered("CASE_BRIEF_ACTIONS", "escape-cancels-an-edit-and-returns-focus");

  await page.keyboard.press("Enter");
  await expect(box).toBeFocused();
  await box.fill("Final requirement");
  await page.keyboard.press("Control+Enter");
  await expect(section.getByText("Final requirement")).toBeVisible();
  expect(sent.find((s) => s.method === "PUT")?.body).toEqual({ text: "Final requirement" });
  await expect(section.getByRole("button", { name: "Edit requirement 1" })).toBeFocused();
  registerCovered("CASE_BRIEF_ACTIONS", "edit-a-requirement-by-keyboard");
});

test("the Author marks a requirement answered and reopens it by keyboard", async ({ page }) => {
  const { sent } = await serve(page, { requirements: [requirement("r1", "Who?")] });
  const section = page.getByRole("region", { name: "Brief" });
  await section.getByRole("button", { name: "Mark requirement 1 answered" }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByText("Answered", { exact: true })).toBeVisible();
  expect(sent.find((s) => s.url.endsWith("/status"))?.body).toEqual({ status: "answered" });
  // The same button is now Reopen, and focus stayed on it.
  await expect(section.getByRole("button", { name: "Reopen requirement 1" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(section.getByText("Open", { exact: true })).toBeVisible();
  expect(sent.filter((s) => s.url.endsWith("/status")).map((s) => s.body)).toEqual([{ status: "answered" }, { status: "open" }]);
  registerCovered("CASE_BRIEF_ACTIONS", "mark-a-requirement-answered-and-reopen-it-by-keyboard");
});

test("the Author attaches a saved trend by keyboard, and then opens and detaches it", async ({ page }) => {
  const { sent } = await serve(page, { requirements: [requirement("r1", "Where and when?")] });
  const section = page.getByRole("region", { name: "Brief" });
  await section.getByRole("button", { name: "Attach to requirement 1" }).focus();
  await page.keyboard.press("Enter");
  const kind = section.getByRole("combobox", { name: "Kind of attachment" });
  await expect(kind).toBeFocused();
  // A native select's keys differ by platform (ArrowDown opens the list on some), so the choice is
  // made with selectOption, which sets it and fires `change`; reaching the select is by keyboard.
  await kind.selectOption("trend");
  const choice = section.getByRole("combobox", { name: "What to attach" });
  await expect(choice).toBeVisible();
  await choice.focus();
  await choice.selectOption("t1");
  await section.getByRole("button", { name: "Attach", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByRole("button", { name: "Open trend: Throw-overs by week" })).toBeVisible();
  expect(sent.find((s) => s.method === "POST" && s.url.endsWith("/attachments"))?.body).toEqual({ kind: "trend", id: "t1" });
  await expect(section.getByRole("button", { name: "Attach to requirement 1" })).toBeFocused();
  registerCovered("CASE_BRIEF_ACTIONS", "attach-a-trend-by-keyboard");

  await section.getByRole("button", { name: "Open trend: Throw-overs by week" }).focus();
  await page.keyboard.press("Enter");
  await expect.poll(() => opened(page)).toEqual([{ kind: "trend", id: "t1" }]);
  registerCovered("CASE_BRIEF_ACTIONS", "open-an-attachment-by-keyboard");

  await section.getByRole("button", { name: "Detach trend: Throw-overs by week" }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByRole("button", { name: "Open trend: Throw-overs by week" })).toHaveCount(0);
  // The Detach button is gone, so focus goes to Attach (the last attachment went), not to the page.
  await expect(section.getByRole("button", { name: "Attach to requirement 1" })).toBeFocused();
  expect(sent.find((s) => s.method === "DELETE")?.url).toBe("/v1/investigations/c1/brief/requirements/r1/attachments/trend/t1");
  registerCovered("CASE_BRIEF_ACTIONS", "detach-an-attachment-by-keyboard");
});

test("the Author removes a requirement only after confirming, by keyboard", async ({ page }) => {
  const { sent } = await serve(page, { requirements: [requirement("r1", "To keep"), requirement("r2", "To remove")] });
  const section = page.getByRole("region", { name: "Brief" });
  await section.getByRole("button", { name: "Remove requirement 2" }).focus();
  await page.keyboard.press("Enter");
  // Keep leaves it, and focus returns to Remove.
  await section.getByRole("button", { name: "Keep requirement 2" }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByText("To remove")).toBeVisible();
  await expect(section.getByRole("button", { name: "Remove requirement 2" })).toBeFocused();
  expect(sent.some((s) => s.method === "DELETE")).toBe(false);

  await page.keyboard.press("Enter");
  await section.getByRole("button", { name: "Confirm remove requirement 2" }).focus();
  await page.keyboard.press("Enter");
  await expect(section.getByText("To remove")).toHaveCount(0);
  await expect(section.getByText("To keep")).toBeVisible();
  expect(sent.find((s) => s.method === "DELETE")?.url).toBe("/v1/investigations/c1/brief/requirements/r2");
  registerCovered("CASE_BRIEF_ACTIONS", "remove-a-requirement-after-confirming-by-keyboard");
});

test("a person who only reads the case reaches an attachment and is offered no edit", async ({ page }) => {
  await serve(page, {
    level: "viewer",
    priority: "Who is orchestrating the throw-overs?",
    requirements: [requirement("r1", "Who?", { attachments: [{ kind: "trend", id: "t1", title: TREND.title }] })],
  });
  const section = page.getByRole("region", { name: "Brief" });
  await expect(section.getByText("Who?")).toBeVisible();
  await expect(section.getByRole("button", { name: /Edit|Add|Mark|Reopen|Attach|Detach|Remove/ })).toHaveCount(0);
  // The only thing to reach is the attachment, and Tab gets there.
  await page.keyboard.press("Tab");
  await expect(section.getByRole("button", { name: "Open trend: Throw-overs by week" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect.poll(() => opened(page)).toEqual([{ kind: "trend", id: "t1" }]);
  registerCovered("CASE_BRIEF_ACTIONS", "a-reader-reaches-an-attachment-and-is-offered-no-edit");
});

test("every registered case brief action has its own proving test case above", () => {
  assertAllCovered("CASE_BRIEF_ACTIONS", CASE_BRIEF_ACTIONS);
});
