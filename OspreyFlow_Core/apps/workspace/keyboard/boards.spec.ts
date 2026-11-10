// Drawing boards by keyboard alone (ADR-143 decision 5: "every board action has its keyboard case";
// rule 13): open, make (blank, from a view and from the selection) and share a board; declare an item,
// with a document of the case as its source and an icon of its own; inspect it, move it by the arrow
// keys, edit it and withdraw it after asking once (from the inspector and from its menu, Shift+F10);
// open the link form from the selected item and from an item's menu; add a picture, or choose one on
// the board; decide a suggested match both ways; start a drawing with no case; go back to the boards;
// promote drawn items from the sheet, and close it by Escape (L3.4). No `page.mouse`, no `.click()` in these.
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
  await page.keyboard.press("ArrowDown");
  await expect(fromSelection).toBeChecked();
  await press(page, "Make the board");
  await expect(page.getByRole("heading", { name: "From the canvas" })).toBeVisible();
  const made = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/boards"));
  expect(made?.body).toEqual({ name: "From the canvas", start: "selection", node_ids: ["p-mercer", "p-ward"] });
  registerCovered("BOARD_ACTIONS", "make-a-board-from-the-selection-by-keyboard");
});

test("a board is made from a view of the case by keyboard", async ({ page }) => {
  await open(page);
  await typeInto(page, "Board name", "From visits");
  const fromView = page.getByRole("radio", { name: "From a view of this case" });
  await page.getByRole("radio", { name: "Blank" }).focus();
  await page.keyboard.press("ArrowDown");
  await expect(fromView).toBeChecked();
  await expect(page.getByLabel(/^The view/)).toHaveValue("v-visits");
  await press(page, "Make the board");
  await expect(page.getByRole("heading", { name: "From visits" })).toBeVisible();
  const made = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/boards"));
  expect(made?.body).toEqual({ name: "From visits", start: "view", view_id: "v-visits" });
  registerCovered("BOARD_ACTIONS", "make-a-board-from-a-view-by-keyboard");
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

async function choosePerson(page: Page): Promise<void> {
  const person = page.getByRole("radio", { name: "Person" });
  await person.focus();
  await page.keyboard.press("Space");
  await expect(person).toBeChecked();
}

test("an item is declared by keyboard with a document of the case as its source and an icon of its own", async ({ page }) => {
  await open(page, "?board=b-wing");
  await choosePerson(page);
  await press(page, "Declare a Person");
  await page.keyboard.type("Visitor in the photo");
  // No note: the document on the board is the source (decision 4: a note, a document, or both).
  await page.getByLabel("A document of the case (optional)").selectOption("doc-photo");
  await page.getByLabel(/^Icon/).selectOption({ index: 1 });
  const icon = await page.getByLabel(/^Icon/).inputValue();
  expect(icon).not.toBe("");
  await press(page, "Add to board");
  await expect(item(page, /^Person Visitor in the photo \(drawn\)/)).toBeFocused();
  const declared = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/items"));
  expect(declared?.body).toMatchObject({ label: "Visitor in the photo", source_note: null, source_document: "doc-photo", icon });
  registerCovered("BOARD_ACTIONS", "declare-an-item-with-a-source-document-by-keyboard");
  registerCovered("BOARD_ACTIONS", "choose-an-items-icon-by-keyboard");
});

test("an item with neither a source note nor a document is refused before it is sent", async ({ page }) => {
  await open(page, "?board=b-wing");
  await choosePerson(page);
  await press(page, "Declare a Person");
  await page.keyboard.type("No source");
  await press(page, "Add to board");
  await expect(page.getByRole("alert")).toContainText("Give a source note or choose a document of the case");
  expect((await sent(page)).some((s) => s.method === "POST" && s.path.endsWith("/items"))).toBe(false);
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

test("an item is withdrawn by keyboard after asking once, with the links drawn to it named", async ({ page }) => {
  await open(page, "?board=b-wing");
  // A link drawn to it first, so the question has a link to name.
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await press(page, "Draw a link…");
  await drawTheLink(page);
  // The form gives focus back to the item once the board is read again: wait for it.
  await expect(item(page, /^Person Unknown male “Tall” \(drawn\)/)).toBeFocused();
  await press(page, "Withdraw Unknown male “Tall”");
  const question = page.getByRole("dialog", { name: "Withdraw Unknown male “Tall”?" });
  await expect(question).toContainText("kept in the audit");
  await expect(question).toContainText("The link drawn to it on this board, withdrawn with it: associate of (Ward).");
  await expect(question).toContainText("every link drawn to it (on this board or another of the case) and its picture");
  expect((await sent(page)).some((s) => s.path.endsWith("/withdraw"))).toBe(false);
  await press(page, "Withdraw the item");
  await expect(item(page, /Unknown male “Tall”/)).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "withdrawn" })).toHaveText(
    // The Conduit's answer named a link on another board too: counted, as it said.
    "Unknown male “Tall” withdrawn, with 2 links drawn to it (associate of, 1 on another board). It is kept in the audit.",
  );
  const withdrawn = (await sent(page)).filter((s) => s.path.endsWith("/withdraw"));
  expect(withdrawn.map((s) => s.path)).toEqual(["/v1/investigations/c1/board-items/i-tall/withdraw"]);
  registerCovered("BOARD_ACTIONS", "withdraw-an-item-after-asking-once-by-keyboard");
});

async function fromTheMenu(page: Page, name: RegExp, action: string): Promise<void> {
  await item(page, name).focus();
  await page.keyboard.press("Shift+F10");
  const menu = page.getByRole("menu", { name: "Item actions" });
  await expect(menu.getByRole("menuitem").first()).toBeFocused();
  // Down the menu to the action, by the arrow keys alone.
  for (let i = 0; i < 6; i += 1) {
    if (await menu.getByRole("menuitem", { name: action, exact: true }).evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("ArrowDown");
  }
  await expect(menu.getByRole("menuitem", { name: action, exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
}

test("an item is inspected from its menu by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await fromTheMenu(page, /^Person Unknown male “Tall” \(drawn\)/, "Inspect");
  await expect(page.getByRole("region", { name: "Unknown male “Tall”" })).toContainText("Drawn by");
  registerCovered("BOARD_ACTIONS", "inspect-an-item-from-its-menu-by-keyboard");
});

test("an item is edited from its menu by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await fromTheMenu(page, /^Person Unknown male “Tall” \(drawn\)/, "Edit");
  await expect(page.getByLabel("What do you call it?")).toBeFocused();
  await page.keyboard.press("ControlOrMeta+A");
  await page.keyboard.type("Tall man");
  await press(page, "Save the change");
  const edit = (await sent(page)).find((s) => s.method === "PATCH");
  expect(edit?.body).toMatchObject({ label: "Tall man" });
  registerCovered("BOARD_ACTIONS", "edit-an-item-from-its-menu-by-keyboard");
});

test("an item is withdrawn from its menu by keyboard after asking once", async ({ page }) => {
  await open(page, "?board=b-wing");
  await fromTheMenu(page, /^Person Unknown male “Tall” \(drawn\)/, "Withdraw");
  await expect(page.getByRole("dialog", { name: "Withdraw Unknown male “Tall”?" })).toBeVisible();
  expect((await sent(page)).some((s) => s.path.endsWith("/withdraw"))).toBe(false);
  await press(page, "Withdraw the item");
  await expect(item(page, /Unknown male “Tall”/)).toHaveCount(0);
  registerCovered("BOARD_ACTIONS", "withdraw-an-item-from-its-menu-by-keyboard");
});

test("the menu key opens an item's menu too", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("ContextMenu");
  await expect(page.getByRole("menu", { name: "Item actions" }).getByRole("menuitem").first()).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(item(page, /^Person Unknown male “Tall” \(drawn\)/)).toBeFocused();
});

test("another member's drawn item on one's own board offers no Edit, Withdraw or picture", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Bob’s sketch \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  const inspector = page.getByRole("region", { name: "Bob’s sketch" });
  await expect(inspector).toContainText("Drawn by");
  await expect(inspector.getByRole("button", { name: /^Edit |^Withdraw / })).toHaveCount(0);
  await expect(page.getByLabel(/^Picture of /)).toHaveCount(0);
  await page.keyboard.press("Shift+F10");
  await expect(page.getByRole("menu", { name: "Item actions" }).getByRole("menuitem")).toHaveText(["Draw a link from here", "Inspect"]);
});

test("a loaded item's menu offers no Edit or Withdraw", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Mercer \(loaded\)/).first().focus();
  await page.keyboard.press("Shift+F10");
  const menu = page.getByRole("menu", { name: "Item actions" });
  await expect(menu.getByRole("menuitem")).toHaveText(["Draw a link from here", "Inspect"]);
});

test("a picture is added to a drawn item by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await page.getByLabel("Picture of Unknown male “Tall”").setInputFiles({ name: "tall.png", mimeType: "image/png", buffer: Buffer.from("png") });
  await page.getByLabel("The picture's marking").selectOption("OFFICIAL");
  // Its own source note is required (C17 a): without one nothing is sent.
  await press(page, "Add the picture");
  await expect(page.getByRole("alert")).toContainText("Say where the picture comes from.");
  expect((await sent(page)).some((s) => s.method === "PUT" && s.path.includes("/picture"))).toBe(false);
  await typeInto(page, "Where the picture comes from", "Wing B camera, 4 Nov");
  await press(page, "Add the picture");
  const put = (await sent(page)).find((s) => s.method === "PUT" && s.path.includes("/nodes/d-tall/picture"));
  const query = new URL(`http://x${put!.path}`).searchParams;
  expect(Object.fromEntries(query)).toEqual({ name: "tall.png", marking: "OFFICIAL", source_note: "Wing B camera, 4 Nov" });
  await expect(page.getByRole("status").filter({ hasText: "Picture added" })).toHaveText("Picture added to Unknown male “Tall”.");
  registerCovered("BOARD_ACTIONS", "add-a-picture-to-a-drawn-item-by-keyboard");
});

test("a picture on the board is chosen for a drawn item by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await item(page, /^Person Unknown male “Tall” \(drawn\)/).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Or a picture on the board")).toHaveValue("doc-photo");
  await page.getByLabel("The link's marking").selectOption("OFFICIAL");
  await press(page, "Use this picture");
  const chosen = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/nodes/d-tall/picture"));
  expect(chosen?.body).toEqual({ document_id: "doc-photo", marking: "OFFICIAL" });
  await expect(page.getByRole("status").filter({ hasText: "Picture chosen" })).toHaveText("Picture chosen for Unknown male “Tall”.");
  registerCovered("BOARD_ACTIONS", "choose-a-picture-on-the-board-by-keyboard");
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

test("an open board shows the case's Alerts panel, its rows words with nothing to open", async ({ page }) => {
  // ADR-146 decision 9 (rules-b's panel, mounted on a board at L3.4). Not an action: the board
  // never works an alert, so nothing here is reached by keyboard but the panel's own text.
  await open(page, "?board=b-wing");
  await expect(page.getByRole("table", { name: "Open alerts by source and age" })).toBeVisible();
  await expect(page.getByText(/Visits to Wing B/)).toBeVisible();
  expect((await sent(page)).some((s) => s.path === "/v1/investigations/c1/reports?weeks=12")).toBe(true);
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

// --- promotion (ADR-143 decision 8, L3.4) ---------------------------------------------------------

test("drawn items are promoted from the sheet by keyboard", async ({ page }) => {
  await open(page, "?board=b-wing");
  await press(page, "Promote…");
  const sheet = page.getByRole("dialog", { name: "Promote into Prison intel" });
  await expect(sheet).toBeVisible();
  await expect(page.getByRole("heading", { name: "Promote into Prison intel" })).toBeFocused();
  // The item failing a check cannot be ticked, and says why.
  await expect(page.getByLabel(/Item: Night caller/)).toBeDisabled();
  await expect(sheet.getByText(/Cannot go: Marked SECRET/)).toBeVisible();
  // Untick M. Mercer by Space; Tall stays ticked.
  const mercer = page.getByLabel(/Item: M\. Mercer/);
  await mercer.focus();
  await page.keyboard.press("Space");
  await expect(mercer).not.toBeChecked();
  await press(page, "Promote");
  await expect(page.getByRole("heading", { name: "Promotion sent" })).toBeFocused();
  const posted = (await sent(page)).find((s) => s.method === "POST" && s.path.endsWith("/promotions"));
  expect((posted?.body as { item_ids: string[] }).item_ids).toContain("i-tall");
  expect((posted?.body as { item_ids: string[] }).item_ids).not.toContain("i-ms");
  await expect(page.getByRole("dialog", { name: "Promotion sent" }).getByText("Left out, and why")).toBeVisible();
  await expect(page.getByRole("region", { name: "Promotions from this board" })).toContainText("Committed");
  await press(page, "Close");
  await expect(page.getByRole("button", { name: "Promote…" })).toBeFocused();
  registerCovered("BOARD_ACTIONS", "promote-drawn-items-by-keyboard");
});

test("a drawer the promotion routes do not admit is offered no Promote…", async ({ page }) => {
  // CARRIES (docs, D2a): an Editor draws on their own board but may not promote; the Conduit says so.
  await open(page, "?board=b-wing&promote=no");
  // A drawer still: the palette to declare an item is drawn.
  await expect(page.getByRole("group", { name: "Type of item to declare" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Promote…" })).toHaveCount(0);
});

test("the promotion sheet closes on Escape, back to Promote…", async ({ page }) => {
  await open(page, "?board=b-wing&policy=second_person_reviews");
  await press(page, "Promote…");
  await expect(page.getByRole("button", { name: "Send for review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Promote into Prison intel" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: /Promote into/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Promote…" })).toBeFocused();
  expect((await sent(page)).some((s) => s.method === "POST" && s.path.endsWith("/promotions"))).toBe(false);
  registerCovered("BOARD_ACTIONS", "close-the-promotion-sheet-by-escape");
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
