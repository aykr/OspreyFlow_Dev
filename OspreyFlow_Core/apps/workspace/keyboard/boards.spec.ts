// Drawing boards by keyboard alone (ADR-143 decision 5: "every board action has its keyboard case";
// rule 13): open, make (blank and from the selection) and share a board; declare an item, inspect it,
// move it by the arrow keys, edit it and withdraw it after asking once; open the link form from the
// selected item and from an item's menu (Shift+F10); add a picture; decide a suggested match both
// ways; start a drawing with no case; go back to the boards. No `page.mouse`, no `.click()` in these.
//
// The pointer gestures (C7: drag moves; the link handle, Alt-drag and right-click draw a link) are
// below the keyboard cases, each named as a pointer case and not registered: they are not what rule
// 13 asks for, and they are tested so a gesture cannot silently stop working.
import { expect, test, type Page } from "@playwright/test";

import { BOARD_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

async function open(page: Page, query = ""): Promise<void> {
  await page.goto(`/keyboard/boards-harness.html${query}`);
  await expect(page.getByRole("heading", { name: /Drawing boards|Wing B|Night shift/ }).first()).toBeVisible();
}

const sent = (page: Page) => page.evaluate(() => window.__BOARDS__!.sent);

async function press(page: Page, name: string | RegExp): Promise<void> {
  const button = page.getByRole("button", { name, exact: typeof name === "string" });
  await button.focus();
  await expect(button).toBeFocused();
  await page.keyboard.press("Enter");
}

async function typeInto(page: Page, label: string | RegExp, text: string): Promise<void> {
  const field = page.getByLabel(label);
  await field.focus();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type(text);
}

const item = (page: Page, name: RegExp) => page.getByRole("button", { name });

test("a board is opened from the boards list by keyboard", async ({ page }) => {
  await open(page);
  await press(page, "Open Wing B");
  await expect(page.getByRole("heading", { name: "Wing B" })).toBeVisible();
  await expect(item(page, /^Person Unknown male “Tall” \(drawn\)/)).toBeVisible();
  await expect(item(page, /^Person Mercer \(loaded\)/)).toBeVisible();
  registerCovered("BOARD_ACTIONS", "open-a-board-from-the-boards-list-by-keyboard");
});

test("a blank board is made by keyboard", async ({ page }) => {
  await open(page);
  await typeInto(page, "Board name", "Visits board");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Visits board" })).toBeVisible();
  const made = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/boards"));
  expect(made?.body).toEqual({ name: "Visits board", start: "blank" });
  registerCovered("BOARD_ACTIONS", "make-a-blank-board-by-keyboard");
});

test("a board is made from the selection by keyboard", async ({ page }) => {
  await open(page);
  await typeInto(page, "Board name", "From the canvas");
  const fromSelection = page.getByRole("radio", { name: /From the selection \(2 items/ });
  await page.getByRole("radio", { name: "Blank" }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(fromSelection).toBeChecked();
  await press(page, "Make the board");
  await expect(page.getByRole("heading", { name: "From the canvas" })).toBeVisible();
  const made = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/boards"));
  expect(made?.body).toEqual({ name: "From the canvas", start: "selection", node_ids: ["p-mercer", "p-ward"] });
  registerCovered("BOARD_ACTIONS", "make-a-board-from-the-selection-by-keyboard");
});

test("a private board is shared with the case by keyboard", async ({ page }) => {
  await open(page, "?board=b-night");
  await press(page, "Share with the case");
  await expect(page.getByText("Shared with the case")).toBeVisible();
  expect((await sent(page)).some((s) => s.method === "POST" && s.path.endsWith("/boards/b-night/share"))).toBe(true);
  registerCovered("BOARD_ACTIONS", "share-a-board-with-the-case-by-keyboard");
});

test("an item is declared by keyboard: marked, graded and sourced, its type's name filled from its label", async ({ page }) => {
  await open(page, "?board=b-wing");
  const person = page.getByRole("radio", { name: "Person" });
  await person.focus();
  await page.keyboard.press("Space");
  await expect(person).toBeChecked();
  await press(page, "Declare a Person");
  const label = page.getByLabel("What do you call it?");
  await expect(label).toBeFocused();
  await page.keyboard.type("Driver of the blue van");
  // A native select is the browser's own keyboard control; it is set as the other keyboard specs set one.
  await page.getByLabel("Handling marking").selectOption("OFFICIAL");
  await typeInto(page, "Source note", "Gate log, 5 Nov");
  await press(page, "Add to board");
  await expect(item(page, /^Person Driver of the blue van \(drawn\)/)).toBeFocused();
  const declared = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/items"));
  expect(declared?.body).toMatchObject({
    type: "Person",
    label: "Driver of the blue van",
    source_note: "Gate log, 5 Nov",
    grading: { scheme: "5x5x5", source: "B", intelligence: "2", handling: "1" },
    properties: { family_name: "Driver of the blue van" },
  });
  expect((declared?.body as { marking: string }).marking).toBe("OFFICIAL");
  registerCovered("BOARD_ACTIONS", "declare-an-item-by-keyboard");
});

test("a refusal is said in the Conduit's own words, naming the ceiling", async ({ page }) => {
  await open(page, "?board=b-wing");
  await press(page, "Declare a Location");
  await page.keyboard.type("Too high");
  await page.getByLabel("Handling marking").selectOption("OFFICIAL-SENSITIVE");
  await typeInto(page, "Source note", "n");
  await press(page, "Add to board");
  await expect(page.getByRole("alert")).toContainText("above this case's ceiling, OFFICIAL-SENSITIVE");
});

test("an item is inspected by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  const inspector = page.getByRole("region", { name: "Unknown male “Tall”" });
  await expect(inspector).toContainText("Drawn by");
  await expect(inspector).toContainText("B21 (5x5x5)");
  await expect(inspector).toContainText("Wing officer report, 4 Nov");
  registerCovered("BOARD_ACTIONS", "inspect-an-item-by-keyboard");
});

test("an item is moved by the arrow keys, and the board keeps where it is", async ({ page }) => {
  await open(page, "?board=b-wing");
  const tall = item(page, /^Person Unknown male “Tall” \(drawn\)/);
  await tall.focus();
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("Shift+ArrowUp");
  const moves = (await sent(page)).filter((s) => s.method === "PUT" && s.path.endsWith("/layout"));
  expect(moves.at(-1)?.body).toEqual({ positions: { "d-tall": { x: 0.32, y: 0.6 } } });
  await expect(tall).toBeFocused();
  registerCovered("BOARD_ACTIONS", "move-an-item-by-the-arrow-keys");
});

async function drawTheLink(page: Page): Promise<void> {
  await page.getByLabel("Links to").selectOption("p-ward");
  await page.getByRole("radio", { name: "associate of" }).focus();
  await page.keyboard.press("Space");
  await typeInto(page, "Source note", "Visits log");
  await press(page, "Draw the link");
}

test("a link is drawn from the selected item by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await press(page, "Draw a link…");
  await expect(page.getByRole("dialog", { name: /New link from Unknown male “Tall”/ })).toBeVisible();
  await drawTheLink(page);
  const link = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/links"));
  expect(link?.body).toMatchObject({ type: "ASSOCIATE_OF", source: "d-tall", target: "p-ward", source_note: "Visits log" });
  await expect(item(page, /^Person Unknown male “Tall” \(drawn\)/)).toBeFocused();
  registerCovered("BOARD_ACTIONS", "draw-a-link-from-the-selected-item-by-keyboard");
});

test("a link is drawn from an item's menu, opened by Shift+F10", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Mercer \(loaded\)/).first().focus();
  await page.keyboard.press("Shift+F10");
  const menu = page.getByRole("menu", { name: "Item actions" });
  await expect(menu.getByRole("menuitem", { name: "Draw a link from here" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("dialog", { name: "New link from Mercer" })).toBeVisible();
  await drawTheLink(page);
  const link = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/links"));
  expect(link?.body).toMatchObject({ source: "p-mercer", target: "p-ward" });
  registerCovered("BOARD_ACTIONS", "draw-a-link-from-an-items-menu-by-keyboard");
});

test("an item is edited by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await press(page, "Edit Unknown male “Tall”");
  await expect(page.getByLabel("What do you call it?")).toBeFocused();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("Tall man, Wing B");
  await page.getByLabel("Source", { exact: true }).selectOption("A");
  await press(page, "Save the change");
  const edit = (await sent(page)).find((s) => s.method === "PATCH");
  expect(edit?.path).toBe("/v1/investigations/c1/board-items/i-tall");
  expect(edit?.body).toMatchObject({ label: "Tall man, Wing B", grading: { source: "A" } });
  await expect(item(page, /^Person Tall man, Wing B \(drawn\)/)).toBeFocused();
  registerCovered("BOARD_ACTIONS", "edit-an-item-by-keyboard");
});

test("an item is withdrawn by keyboard after asking once, with the links drawn to it", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await press(page, "Withdraw Unknown male “Tall”");
  await expect(page.getByRole("dialog", { name: "Withdraw Unknown male “Tall”?" })).toContainText("kept in the audit");
  expect((await sent(page)).some((s) => s.path.endsWith("/withdraw"))).toBe(false);
  await press(page, "Withdraw the item");
  await expect(item(page, /Unknown male “Tall”/)).toHaveCount(0);
  const withdrawn = (await sent(page)).filter((s) => s.path.endsWith("/withdraw"));
  expect(withdrawn.map((s) => s.path)).toEqual(["/v1/investigations/c1/board-items/i-tall/withdraw"]);
  registerCovered("BOARD_ACTIONS", "withdraw-an-item-after-asking-once-by-keyboard");
});

test("a picture is added to a drawn item by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Picture of Unknown male “Tall”").setInputFiles({ name: "tall.png", mimeType: "image/png", buffer: Buffer.from("png") });
  await page.getByLabel("The picture's marking").selectOption("OFFICIAL");
  await press(page, "Add the picture");
  const put = (await sent(page)).find((s) => s.method === "PUT" && s.path.includes("/nodes/d-tall/picture"));
  expect(put?.path).toContain("name=tall.png");
  expect(put?.path).toContain("marking=OFFICIAL");
  registerCovered("BOARD_ACTIONS", "add-a-picture-to-a-drawn-item-by-keyboard");
});

test("Same is decided on a suggested match by keyboard, writing one decision and merging nothing", async ({ page }) => {
  await open(page, "?board=b-wing");
  const suggestions = page.getByRole("list", { name: "Looks like a loaded item" });
  await expect(suggestions).toContainText("M. Mercer looks like Mercer (a name alike, 86%)");
  await press(page, "Same: M. Mercer is Mercer");
  const decided = (await sent(page)).filter((s) => s.method === "POST" && s.path.endsWith("/matches"));
  expect(decided.map((s) => s.body)).toEqual([{ drawn: "d-ms", loaded: "p-mercer", same: true }]);
  await expect(page.getByText("Nothing drawn here looks like a loaded item.")).toBeVisible();
  registerCovered("BOARD_ACTIONS", "decide-same-on-a-suggested-match-by-keyboard");
});

test("Not the same is decided on a suggested match by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await press(page, "Not the same: M. Mercer and Mercer");
  const decided = (await sent(page)).filter((s) => s.method === "POST" && s.path.endsWith("/matches"));
  expect(decided.map((s) => s.body)).toEqual([{ drawn: "d-ms", loaded: "p-mercer", same: false }]);
  registerCovered("BOARD_ACTIONS", "decide-not-the-same-on-a-suggested-match-by-keyboard");
});

test("a drawing is started with no case by keyboard: its dataset, its case and its board", async ({ page }) => {
  await open(page);
  await typeInto(page, "Drawing name", "Night visits");
  await page.getByLabel("Highest marking it may hold").selectOption("OFFICIAL-SENSITIVE");
  await press(page, "Start the drawing");
  const started = (await sent(page)).find((s) => s.path === "/v1/drawings");
  expect(started?.body).toEqual({ name: "Night visits", highest_marking: "OFFICIAL-SENSITIVE", pack: null });
  await expect.poll(() => page.evaluate(() => window.__BOARDS__!.caseMade)).toEqual({ caseId: "c-new", boardId: "b-new" });
  registerCovered("BOARD_ACTIONS", "start-a-drawing-with-no-case-by-keyboard");
});

test("Back to the boards is reached from a board by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await press(page, "Back to the boards");
  await expect(page.getByRole("list", { name: "Boards in this case" })).toBeVisible();
  registerCovered("BOARD_ACTIONS", "go-back-to-the-boards-by-keyboard");
});

test("another member sees a shared board read-only: nothing to declare, edit or withdraw", async ({ page }) => {
  await open(page, "?board=b-wing&as=bob");
  await expect(page.getByText("Read only: drawn by alice")).toBeVisible();
  await expect(page.getByRole("button", { name: /^Declare / })).toHaveCount(0);
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: /^Edit |^Withdraw / })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Same: / })).toHaveCount(0);
  // The arrow keys move nothing.
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("ArrowRight");
  expect((await sent(page)).some((s) => s.method === "PUT")).toBe(false);
});

test("every registered board action has its own proving test case above", () => {
  assertAllCovered("BOARD_ACTIONS", BOARD_ACTIONS);
});

// --- pointer gestures (C7), not registered ---------------------------------------------------------

async function centre(page: Page, name: RegExp): Promise<{ x: number; y: number }> {
  const box = await item(page, name).first().boundingBox();
  if (!box) throw new Error("not drawn");
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

test("pointer: dragging an item moves it", async ({ page }) => {
  await open(page, "?board=b-wing");
  const from = await centre(page, /Unknown male “Tall”/);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x + 80, from.y - 40, { steps: 5 });
  await page.mouse.up();
  const moves = (await sent(page)).filter((s) => s.method === "PUT" && s.path.endsWith("/layout"));
  expect(Object.keys((moves.at(-1)?.body as { positions: object }).positions)).toEqual(["d-tall"]);
  expect((await sent(page)).some((s) => s.path.endsWith("/links"))).toBe(false);
});

test("pointer: dragging the link handle onto another item opens the link form between them", async ({ page }) => {
  await open(page, "?board=b-wing");
  const handle = page.locator('[data-board-item="d-tall"] .board-item__handle');
  const box = await handle.boundingBox();
  const to = await centre(page, /^Person Ward \(loaded\)/);
  await page.mouse.move(box!.x + 5, box!.y + 5);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 6 });
  await page.mouse.up();
  await expect(page.getByRole("dialog", { name: /New link from Unknown male “Tall”/ })).toBeVisible();
  await expect(page.getByLabel("Links to")).toHaveValue("p-ward");
});

test("pointer: Alt-dragging an item draws a link instead of moving it", async ({ page }) => {
  await open(page, "?board=b-wing");
  const from = await centre(page, /Unknown male “Tall”/);
  const to = await centre(page, /M\. Mercer/);
  await page.keyboard.down("Alt");
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 6 });
  await page.mouse.up();
  await page.keyboard.up("Alt");
  await expect(page.getByLabel("Links to")).toHaveValue("d-ms");
  expect((await sent(page)).some((s) => s.method === "PUT")).toBe(false);
});

test("pointer: right-click offers Draw a link from here", async ({ page }) => {
  await open(page, "?board=b-wing");
  const at = await centre(page, /^Person Ward \(loaded\)/);
  await page.mouse.click(at.x, at.y, { button: "right" });
  await page.getByRole("menuitem", { name: "Draw a link from here" }).click();
  await expect(page.getByRole("dialog", { name: "New link from Ward" })).toBeVisible();
});
