// **Owner ruling R6, 27 September 2026 — the ingest folder, reached in a real browser.**
//
// Round 13b's over-the-wire exit test found that a rendered deployment gave an analyst no route by
// which to supply a source file at all: `POST /v1/ingest/recipes` takes a `source_location` the
// *Conduit's own container* must be able to read, and nothing was mounted there. R6's answer is a
// storage root bind-mounted read-only into the Conduit and listed by the Studio's own Connect
// stage, so the analyst picks a file instead of typing a path.
//
// `tests/scenarios/test_phase8_exit_over_the_wire.py` already proves that chain over HTTP. This
// file proves the half HTTP cannot: that a person sitting in front of the Glass can actually get
// to it. The two are deliberately different tiers and neither replaces the other — round 13b's
// own live tier exists because `make glass-map-verify`'s screenshot could not prove tiles rendered
// either.
//
// **Precondition, and it is a real one.** The deployment's ingest root must contain at least one
// file before this runs — `DEMO_GUIDE.md` §3.7a says how, for both a rendered deployment and the
// hand-run stack. An empty folder is a correct and perfectly valid state of the product, so this
// spec **fails rather than skips** when it finds one: a skip here would be indistinguishable from
// "the folder works", which is the shape `CLAUDE.md` rule 15 keeps naming.
import { expect, test } from "@playwright/test";

import { apiBaseUrl, freshWorkspaceUrl, liveOnly, required } from "./live";

test.beforeEach(liveOnly);

test("the Ingest Studio offers a file from the deployment's ingest folder", async ({
  page,
  request,
}) => {
  // Ask the route directly first, so a failure below can be attributed: if this is empty the
  // operator has staged nothing, and no amount of clicking will produce a file to pick.
  const listing = await request.get(`${apiBaseUrl()}/v1/ingest/source-files`, {
    headers: { Authorization: `Bearer ${required("OSPREY_LIVE_BEARER_TOKEN")}` },
  });
  expect(
    listing.ok(),
    "GET /v1/ingest/source-files was refused — the bearer token's principal needs the " +
      "`source_author` Studio role (harness/realm.py grants it to the --demo-analyst subject)",
  ).toBe(true);
  const files = ((await listing.json()) as { root: string; files: { name: string }[] }).files;
  expect(
    files.length,
    "the deployment's ingest folder is empty, so there is nothing for an analyst to select. " +
      "DEMO_GUIDE.md §3.7a says how to stage a file. Failing rather than skipping: a skip here " +
      "would look exactly like a pass.",
  ).toBeGreaterThan(0);

  await page.goto(await freshWorkspaceUrl(request));
  await page.getByRole("button", { name: "Ingest" }).click();

  // The picker is the whole point of R6: the analyst never types a path, because in a rendered
  // deployment there is no path they could type that the Conduit can open.
  const picker = page.getByLabel("Choose a file from the ingest folder");
  await expect(
    picker,
    "the Connect stage did not offer the ingest folder, so an analyst is back to typing a path " +
      "that the Conduit cannot read",
  ).toBeVisible();

  // Every file the route returned is offered, by name.
  for (const file of files) {
    await expect(picker.getByRole("option", { name: new RegExp(file.name) })).toHaveCount(1);
  }

  // Selecting one fills "Where is the data?" with the container path — the field the draft
  // carries through to Profile and Map unchanged.
  const firstOption = picker.locator("option").nth(1);
  const chosenValue = (await firstOption.getAttribute("value")) ?? "";
  expect(chosenValue).not.toEqual("");
  await picker.selectOption(chosenValue);

  await expect(
    page.getByLabel("Where is the data?"),
    "choosing a file did not populate the source location, so the draft would carry nothing",
  ).toHaveValue(chosenValue);
});
