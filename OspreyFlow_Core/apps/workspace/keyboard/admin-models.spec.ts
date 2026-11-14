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

test("an engine is added by keyboard", async ({ page }) => {
  await press(page, "Add an engine");
  await page.getByLabel("Provider", { exact: true }).focus();
  await page.keyboard.press("End"); // the last provider listed
  await typeInto(page, /Extraction and Ask: the provider/, "claude-x");
  await page.getByLabel(/Under a privacy contract/).focus();
  await page.keyboard.press("Space");
  await typeInto(page, /reference/, "DPA 2026/09");
  await press(page, "Add the engine");
  await expect(page.getByRole("status")).toContainText("is added");
  expect(await asked(page)).toContain("POST /engines");
  registerCovered(REGISTRY, "add-a-model-engine-by-keyboard");
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
  await page.getByLabel("Kind of engine", { exact: true }).focus();
  // Type-ahead on the closed list, as the gateway's case does: on macOS End and the arrow keys open
  // a closed list instead of moving the choice, so "End" left the kind unchanged there.
  await page.keyboard.type("Amazon"); // "Amazon Bedrock in London, by the gateway's own IAM role"
  await expect(page.getByLabel("Engine name", { exact: true })).toHaveValue("bedrock");
  await expect(page.getByText(/no key is kept/)).toBeVisible();
  await typeInto(page, "Label analysts see", "Bedrock");
  await typeInto(page, /Extraction and Ask: the provider/, "anthropic.claude-3-haiku");
  await press(page, "Add the engine");
  await expect(page.getByRole("status")).toContainText("no key is needed");
  expect(await asked(page)).toContain("POST /engines");
  expect((await sentBody(page, "POST /engines"))?.provider).toMatchObject({ name: "bedrock", kind: "bedrock", auth: "iam_role", api_base: null });
  await expect(page.getByRole("table", { name: "Engines", exact: true })).toContainText("IAM role: no key kept");
  await expect(page.getByRole("button", { name: /key for Bedrock/ })).toHaveCount(0);
  await press(page, "Test the connection to Bedrock");
  expect(await asked(page)).toContain("POST /engines/bedrock/test");
  registerCovered(REGISTRY, "add-bedrock-by-iam-role-by-keyboard");
});

test("the organisation's own gateway is added by keyboard, signed in by its token", async ({ page }) => {
  await onCloudPlatform(page);
  await press(page, "Add an engine");
  await page.getByLabel("Kind of engine", { exact: true }).focus();
  // Type-ahead on the closed list (on macOS an arrow key opens it instead of moving the choice).
  await page.keyboard.type("Your"); // "Your organisation's own AI gateway"
  await expect(page.getByLabel("Engine name", { exact: true })).toBeEditable();
  await typeInto(page, "Engine name", "acme_ai");
  await expect(page.getByText(/Signs in by a token/)).toBeVisible();
  await typeInto(page, /Address of your gateway/, "https://ai.example/v1");
  await typeInto(page, /Extraction and Ask: the provider/, "gpt-4o-mini");
  await press(page, "Add the engine");
  await expect(page.getByRole("status")).toContainText("acme_ai is added. Enter its key next");
  expect(await asked(page)).toContain("POST /engines");
  // What was added, not only that POST was asked (the review's item 8).
  expect((await sentBody(page, "POST /engines"))?.provider).toMatchObject({
    name: "acme_ai",
    kind: "gateway",
    auth: "key",
    api_base: "https://ai.example/v1",
  });
  await press(page, "Enter key for acme_ai");
  await expect(page.getByRole("textbox", { name: /Key for acme_ai/ })).toHaveValue("");
  registerCovered(REGISTRY, "add-the-organisations-gateway-by-keyboard");
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
