// A keyboard-only walkthrough of Admin › Models (ADR-135 Amendment 2, `CLAUDE.md` rule 13): every
// action, by focus and key presses alone — no `page.mouse`, no `.click()` — each proving its call
// reached the Conduit's stand-in (`models-harness.tsx`, which records each request).
import { expect, test, type Page } from "@playwright/test";

import { MODELS_ACTIONS, assertAllCovered, registerCovered } from "./actionRegistry";

const REGISTRY = "MODELS_ACTIONS";
const SYNTHETIC_KEY = "sk-synthetic-keyboard-test-key";

const asked = (page: Page) => page.evaluate(() => (window as unknown as { modelsAsked: string[] }).modelsAsked);

async function press(page: Page, name: string) {
  await page.getByRole("button", { name, exact: true }).focus();
  await page.keyboard.press("Enter");
}

async function typeInto(page: Page, label: string | RegExp, text: string) {
  await page.getByLabel(label).focus();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type(text);
}

test.beforeEach(async ({ page }) => {
  await page.goto("/keyboard/models-harness.html");
  await expect(page.getByRole("table", { name: "Engines", exact: true })).toBeVisible();
});

// ADR-135 Amendment 14: a provider chosen from the list, its model typed, its key checked, then Add.
test("an engine is added by keyboard, checked before Add", async ({ page }) => {
  await press(page, "Add an engine");
  await page.getByLabel("Provider", { exact: true }).focus();
  // Type-ahead on the closed list (on macOS an arrow key opens it instead of moving the choice).
  await page.keyboard.type("Anthropic");
  await expect(page.getByLabel("Label analysts see", { exact: true })).toHaveValue("Anthropic");
  await expect(page.getByLabel("Transcription: model name")).toHaveCount(0);
  await typeInto(page, "Extraction and Ask: model name", "claude-sonnet-5-5");
  await typeInto(page, /^Key/, SYNTHETIC_KEY);
  await page.getByLabel(/Under a privacy contract/).focus();
  await page.keyboard.press("Space");
  await typeInto(page, /reference/, "DPA 2026/09");
  await expect(page.getByText(/^Analysts will see:/)).toContainText("Anthropic (under contract)");
  await press(page, "Check");
  await expect(page.getByRole("status")).toContainText("Add the engine within 15 minutes");
  await expect(page.getByLabel(/^Key/)).toHaveValue("");
  await press(page, "Add the engine");
  await expect(page.getByRole("status")).toContainText("Anthropic is added and offered to analysts");
  expect(await asked(page)).toEqual(expect.arrayContaining(["POST /checks", "POST /checks/chk-1/add"]));
  expect(await asked(page)).not.toContain("POST /engines");
  expect(await page.content()).not.toContain(SYNTHETIC_KEY);
  registerCovered(REGISTRY, "add-a-model-engine-by-keyboard");
});

test("a passed check is cancelled by keyboard, from the form and from the list", async ({ page }) => {
  await press(page, "Add an engine");
  await typeInto(page, "Extraction and Ask: model name", "gemini-3.8-flash");
  await typeInto(page, /^Key/, SYNTHETIC_KEY);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Add the engine", exact: true })).toBeVisible();
  await press(page, "Cancel");
  await expect(page.getByRole("status")).toContainText("its check and key are removed");
  expect(await asked(page)).toContain("DELETE /checks/chk-1");
  await page.goto("/keyboard/models-harness.html?held=1");
  await expect(page.getByRole("table", { name: "Being checked" })).toContainText("Anthropic");
  await press(page, "Cancel the check of Anthropic");
  await expect(page.getByRole("status")).toContainText("Anthropic was not added");
  expect(await asked(page)).toContain("DELETE /checks/chk-held");
  registerCovered(REGISTRY, "cancel-a-model-engine-check-by-keyboard");
});

// What reached the Conduit's stand-in in each request's body (never a key's: the harness keeps none).
const sentBody = async (page: Page, request: string) =>
  page.evaluate(
    (wanted) =>
      (window as unknown as { modelsSent: { request: string; body: Record<string, unknown> }[] }).modelsSent.find((s) => s.request === wanted)
        ?.body,
    request,
  );

// The cloud-platform profile (ADR-135 Amendment 7 decision 1), where the two kinds are offered.
async function onCloudPlatform(page: Page) {
  await page.goto("/keyboard/models-harness.html?cloud=1");
  await expect(page.getByRole("table", { name: "Engines", exact: true })).toBeVisible();
}

// ADR-135 Amendment 4: the kind of engine is chosen by keyboard, and an IAM-role engine offers no key.
test("Bedrock in London is added by keyboard, signed in by the IAM role with no key asked for", async ({ page }) => {
  await onCloudPlatform(page);
  await press(page, "Add an engine");
  await page.getByLabel("Provider", { exact: true }).focus();
  await page.keyboard.type("Amazon"); // "Amazon Bedrock"
  await expect(page.getByText(/in London only: no key and no address/)).toBeVisible();
  await expect(page.getByLabel(/^Key/)).toHaveCount(0);
  await typeInto(page, "Label analysts see", "Bedrock");
  await typeInto(page, "Extraction and Ask: model name", "amazon.nova-pro-v1:0");
  await press(page, "Check");
  await press(page, "Add the engine");
  await expect(page.getByRole("status")).toContainText("Bedrock is added");
  expect((await sentBody(page, "POST /checks"))?.provider).toMatchObject({ name: "bedrock", kind: "bedrock", auth: "iam_role", api_base: null });
  await expect(page.getByRole("table", { name: "Engines", exact: true })).toContainText("IAM role: no key kept");
  await expect(page.getByRole("button", { name: /key for Bedrock/ })).toHaveCount(0);
  await press(page, "Test the connection to Bedrock");
  expect(await asked(page)).toContain("POST /engines/bedrock/test");
  registerCovered(REGISTRY, "add-bedrock-by-iam-role-by-keyboard");
});

test("the organisation's own gateway is added by keyboard at its address, by its token", async ({ page }) => {
  await press(page, "Add an engine");
  await page.getByLabel("Provider", { exact: true }).focus();
  await page.keyboard.type("Another"); // "Another provider or your own gateway", on every profile
  await typeInto(page, "Address (https://)", "https://ai.example/v1");
  await typeInto(page, "Extraction and Ask: model name", "acme-chat");
  await typeInto(page, /^Token/, SYNTHETIC_KEY);
  await press(page, "Check");
  await press(page, "Add the engine");
  await expect(page.getByRole("status")).toContainText("is added and offered to analysts");
  // What was checked, not only that it was asked (the review's item 8), and never its token.
  const checked = await sentBody(page, "POST /checks");
  expect(checked?.provider).toMatchObject({ name: "gateway", kind: "gateway", auth: "key", api_base: "https://ai.example/v1" });
  expect(checked).not.toHaveProperty("key");
  registerCovered(REGISTRY, "add-the-organisations-gateway-by-keyboard");
});

test("a provider's own address is changed for a gateway in front of it, by keyboard", async ({ page }) => {
  await press(page, "Add an engine");
  await expect(page.getByText("Address: https://generativelanguage.googleapis.com")).toBeVisible();
  await press(page, "Change the address of Google Gemini");
  await typeInto(page, /Address of the gateway in front of it/, "https://proxy.example/gemini");
  await typeInto(page, "Extraction and Ask: model name", "gemini-3.8-flash");
  await typeInto(page, /^Key/, SYNTHETIC_KEY);
  await press(page, "Check");
  await expect(page.getByRole("button", { name: "Add the engine", exact: true })).toBeVisible();
  expect((await sentBody(page, "POST /checks"))?.provider).toMatchObject({ name: "gemini", api_base: "https://proxy.example/gemini" });
  registerCovered(REGISTRY, "change-a-model-providers-address-by-keyboard");
});

test("a refused key is said at the key field, by keyboard, and nothing can be added", async ({ page }) => {
  await press(page, "Add an engine");
  await typeInto(page, "Extraction and Ask: model name", "gemini-3.8-flash");
  await typeInto(page, /^Key/, "synthetic-refuse-key");
  await press(page, "Check");
  await expect(page.getByRole("alert")).toContainText("Nothing was kept");
  await expect(page.getByLabel(/^Key/)).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByLabel(/^Key/)).toHaveAccessibleDescription("The provider refused the key.");
  await expect(page.getByRole("button", { name: "Add the engine", exact: true })).toHaveCount(0);
  registerCovered(REGISTRY, "see-a-model-check-refused-by-keyboard");
});

test("an engine is edited by keyboard", async ({ page }) => {
  await press(page, "Edit Gemini");
  await typeInto(page, "Label analysts see", "Google Gemini");
  await press(page, "Save the engine");
  await expect(page.getByRole("status")).toContainText("gemini is saved");
  expect(await asked(page)).toContain("PUT /engines/gemini");
  registerCovered(REGISTRY, "edit-a-model-engine-by-keyboard");
});

test("a lost key is entered again by keyboard, and the field is empty afterwards", async ({ page }) => {
  await press(page, "Enter key for OpenAI");
  await typeInto(page, /Key for OpenAI/, SYNTHETIC_KEY);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status")).toContainText("the key is set");
  expect(await asked(page)).toContain("PUT /engines/openai/key");
  expect(await page.content()).not.toContain(SYNTHETIC_KEY);
  registerCovered(REGISTRY, "enter-a-model-key-by-keyboard");
});

test("a key is rotated by keyboard", async ({ page }) => {
  await press(page, "Rotate key for Gemini");
  await typeInto(page, /New key for Gemini/, SYNTHETIC_KEY);
  await press(page, "Rotate the key");
  await expect(page.getByRole("status")).toContainText("the key is set");
  expect(await asked(page)).toContain("PUT /engines/gemini/key");
  registerCovered(REGISTRY, "rotate-a-model-key-by-keyboard");
});

test("a key is removed by keyboard", async ({ page }) => {
  await press(page, "Remove key for Gemini");
  await expect(page.getByRole("status")).toContainText("the key is removed");
  expect(await asked(page)).toContain("DELETE /engines/gemini/key");
  registerCovered(REGISTRY, "remove-a-model-key-by-keyboard");
});

test("an engine's connection is tested by keyboard", async ({ page }) => {
  await press(page, "Test the connection to Gemini");
  await expect(page.getByRole("status")).toContainText("Connected: the engine answered.");
  expect(await asked(page)).toContain("POST /engines/gemini/test");
  registerCovered(REGISTRY, "test-a-model-engine-by-keyboard");
});

test("each job's default engine is set by keyboard", async ({ page }) => {
  await page.getByLabel("Extraction and Ask", { exact: true }).focus();
  await page.keyboard.press("ArrowDown");
  await press(page, "Save the defaults");
  await expect(page.getByRole("status")).toContainText("default engine is saved");
  expect(await asked(page)).toContain("PUT /defaults");
  registerCovered(REGISTRY, "set-each-jobs-default-engine-by-keyboard");
});

test("an engine is removed by keyboard", async ({ page }) => {
  await press(page, "Remove OpenAI");
  await expect(page.getByRole("status")).toContainText("OpenAI is removed");
  expect(await asked(page)).toContain("DELETE /engines/openai");
  await expect(page.getByRole("button", { name: "Edit OpenAI" })).toHaveCount(0);
  registerCovered(REGISTRY, "remove-a-model-engine-by-keyboard");
});

test("an engine's limits are set by keyboard", async ({ page }) => {
  await press(page, "Set limits for Gemini");
  await typeInto(page, "Requests a minute", "30");
  await typeInto(page, "Tokens a minute", "50000");
  await typeInto(page, /Token budget/, "500000");
  await page.getByLabel("Budget period", { exact: true }).focus();
  await page.keyboard.press("End"); // the last listed, "a month"
  await press(page, "Save the limits");
  await expect(page.getByRole("status")).toContainText("its limits are saved");
  expect(await asked(page)).toContain("PUT /engines/gemini/limits");
  await expect(page.getByRole("table", { name: "Engines", exact: true })).toContainText(
    "30 requests a minute; 50,000 tokens a minute; 500,000 tokens a month",
  );
  registerCovered(REGISTRY, "set-a-model-engines-limits-by-keyboard");
});

test("the usage's period is chosen by keyboard, and days are chosen by keyboard", async ({ page }) => {
  const usageAsked = async () => (await asked(page)).filter((a) => a.startsWith("GET /usage"));
  await expect(page.getByRole("table", { name: "Usage by engine and job" })).toContainText("61,100");
  // Type-ahead on the closed list (on macOS an arrow key opens it instead of moving the choice).
  await page.getByLabel("Period", { exact: true }).focus();
  await page.keyboard.type("This"); // "this month"
  await expect.poll(async () => (await usageAsked()).length).toBe(2);
  await page.keyboard.press("Tab");
  await page.waitForTimeout(1100); // the list's type-ahead forgets after a second
  await page.getByLabel("Period", { exact: true }).focus();
  await page.keyboard.type("Days"); // "days I choose"
  await page.getByLabel("First day").focus();
  await page.keyboard.type("02112026");
  await page.getByLabel("Last day").focus();
  await page.keyboard.type("03112026");
  await press(page, "Show the usage");
  await expect.poll(async () => (await usageAsked()).at(-1)).toBe("GET /usage?start=2026-11-02&end=2026-11-03");
  registerCovered(REGISTRY, "choose-the-model-usage-period-by-keyboard");
});

test("every registered Models action has its own proving test case above", () => {
  assertAllCovered("MODELS_ACTIONS", MODELS_ACTIONS);
});
