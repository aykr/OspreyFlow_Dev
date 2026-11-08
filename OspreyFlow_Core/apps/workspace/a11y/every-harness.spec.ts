// Every keyboard harness page, scanned by axe-core (the GDS baseline audit, build-order step 2b,
// 1 November 2026). `a11y.spec.ts` scans four real screens; the 38 harness pages under
// `keyboard/` each mount a real screen or panel, and before this file none but those four had an
// automated accessibility scan at all.
//
// The pages are discovered from the directory, never listed, so a new harness is scanned the day
// it is added (`CLAUDE.md` rule 13's lesson: a hard-coded walkthrough cannot see what it leaves
// out). Each is scanned in the dark and the light theme, and under the GOV.UK brand (ADR-132)
// wherever its harness applies the brand (`applyHarnessBrand`, read from the harness's own source;
// a harness that does not is a recorded gap in `process/gds/gds_remediation_plan.md`, not a pass).
//
// The tags are WCAG 2.0, 2.1 and 2.2 at A and AA: axe-core's tags are not hierarchical, and
// `a11y.spec.ts`'s `wcag2a`/`wcag2aa` alone never run `target-size` (2.5.8, WCAG 2.2) or
// `label-content-name-mismatch` (2.5.3, WCAG 2.1). Shown red first: the pipeline canvas's node
// buttons failed 2.5.3 before their names were taken from their visible text.
//
// An automated scan finds only part of WCAG; a pass here is not a claim of conformance.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { readdirSync, readFileSync } from "node:fs";

const KEYBOARD = new URL("../keyboard/", import.meta.url);
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

// Elements a harness adds around the screen under test, never part of the product: each is a
// focus sentinel a keyboard spec tabs to, named here so that nothing else is excluded.
const HARNESS_ONLY: Record<string, string[]> = {
  "link-change-harness.html": ["#after-form"],
};

// States a harness draws only when asked, scanned as well as its default. The start page as an
// analyst (no Studio or Admin right): since ADR-145 N6 (ADR-115 Amendment 6) it draws one card, the
// Glass's, where it once drew the other two gated (the live audit of 1 November 2026 found their text
// at 4.25:1); the state is kept so Home with a single card is scanned too.
const EXTRA_STATES: Record<string, string[]> = {
  // ADR-135 Amendment 2: Admin › Models with an engine being added, a key being entered, and a
  // local-only deployment (platform lane P1); Amendment 3: an engine's limits being set, the usage's
  // own days drawn, and the gateway not giving its usage (P2; the usage table is on every other state).
  "models-harness.html": ["open=add", "open=key", "local=1", "open=limits", "usage=chosen", "usage=fail"],
  // ADR-146 decisions 2 and 6: Home with Rules and Monitoring's card and an alert's row.
  "start-harness.html": ["rights=investigate", "figures=1&rights=investigate,triage_alerts,read_alert_queue"],
  // ADR-145 decision 2: the banner in the Studio, with its way back, and in Admin.
  // ADR-145 Amendment 2: Monitoring's badge (inside the GOV.UK notification banner under that
  // brand), and the rail's ⋯ More and the top bar's More views drawn open.
  // ADR-146 decision 2: Rules and Monitoring in the switcher with its count (inside the GOV.UK header
  // under that brand), and the place open, its banner a GOV.UK notification banner.
  "places-harness.html": [
    "place=ingest", "place=admin", "badge=1", "open=more", "open=views",
    "badge=1&rights=investigate,triage_alerts,read_alert_queue",
    "place=rules&rights=investigate,triage_alerts,read_alert_queue",
  ],
  // ADR-146 decisions 2 and 6: Rules and Monitoring at an alert's address, and at one the reader may
  // not see.
  "rules-place-harness.html": ["address=a1", "address=not-yours", "evidence=1"],
  // ADR-145 Amendment 2: the column's fresh-page default, the Inspector alone open.
  "panel-frames-harness.html": ["defaults=1"],
  // L2.3 part 1: the case screen's lightening, each prototype variant (the default is variant a).
  "case-screen-options-harness.html": ["variant=today", "variant=b", "variant=c"],
  // ADR-144 (L3.2b): case views as another member sees them, the Save as a view form, and the banner
  // over an opened view.
  "views-harness.html": ["as=bob", "show=form", "show=lens", "asking=delete"],
  // ADR-143 decisions 4 to 7 (L3.3): a board open with its drawn and loaded items, its inspector, its
  // item and link forms and the withdrawal's question; another member's read-only view; a blank board.
  "boards-harness.html": [
    "board=b-wing",
    "board=b-wing&as=bob",
    "board=b-night",
    "board=b-wing&press=Declare%20a%20Location",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)%7CDraw%20a%20link%E2%80%A6",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)%7CWithdraw%20Unknown%20male%20%E2%80%9CTall%E2%80%9D",
  ],
  // ADR-124 decision 2 as ADR-144 Amendment 2 changed it: the over-cap dialog with its Save as a view form.
  "view-over-cap-harness.html": ["state=form"],
  // ADR-099 Amendment 12: a new case's form on "Use an existing dataset", its dataset radios drawn.
  "case-datasets-harness.html": ["choice=existing"],
  // The Matrix view (GDS remediation plan A1) with rows selected, and long enough to page.
  "matrix-harness.html": ["select=p2,p4", "many=1", "strength=1"],
  // ADR-139: the two new filter metrics chosen; a link's strength explained in the Inspector; the
  // Connection strength tab as a proposer, as a case's Author and as an Editor.
  "metrics-panel-harness.html": ["filter=strength", "filter=rarity", "composition=client_parity"],
  "inspector-harness.html": ["strength=1", "strength=parity"],
  // ADR-139 Amendment 2: the case switched to client parity, as its Author sees it.
  "strength-harness.html": ["as=maker", "as=author", "as=editor", "as=author&composition=client_parity"],
  // ADR-133 stage (b): the Rules tab with a rule written as a sentence, its drawn pattern and its
  // preview shown.
  // ADR-133 stage (c): the Lists tab, as a reader and as whoever may load lists after a refresh
  // (its refreshes, a failure in words, the subscribe form), and an AML template filling the form.
  "monitoring-harness.html": [
    // The owner's answer of 1 November 2026: the Watches tab, now the only way to the hotlists,
    // the monitors and the alert inbox (the rail's Watches entry is gone).
    "tab=watches",
    "tab=rules&sentence=preview",
    // ADR-139 decision 8: a sentence on connection strength.
    "tab=rules&sentence=strength",
    // ADR-139 Amendment 2: the figure on the client's scale.
    "tab=rules&sentence=strength-client",
    "tab=lists",
    "tab=lists&lists=manage&refreshed=1",
    "tab=rules&template=high_risk_jurisdiction",
    // ADR-133 stage (d): a whole-deployment rule waiting for a second person (Approve and Reject
    // offered), a scheduled rule's runs and versions open, a sentence set to run every week, a
    // high-severity alert whose close waits for approval, and a list refreshed on a schedule with
    // its schedule form.
    "stage=d&tab=rules&opened=1",
    "stage=d&tab=rules&sentence=schedule",
    "stage=d&open=a-close",
    "stage=d&tab=lists&lists=manage",
    // The GDS re-audit (step 9b, 2 November 2026): an alert opened with its close form (the five
    // closing reasons, step 7b), and a KYC screening alert opened (a close match to a listed party).
    "open=a-hot",
    "open=a-kyc",
    // ADR-146 decision 2: Rules and Monitoring's Held rows and Changes, and an address the reader may
    // not see.
    "tab=held",
    "tab=changes",
    "address=missing",
  ],
  // ADR-133 decision 6, stage (d): the Checks on load step (the default) and Verify's would-be alerts.
  "checks-on-load-harness.html": ["view=verify"],
  // ADR-140 decision 1 (redesign phase 2): the Studio's Model, Sources and Runs places, a day's run
  // report with its revert command, and the held rows opened from it (Pipelines is the default).
  "ingest-studio-harness.html": [
    "tab=model", "tab=sources", "tab=runs", "tab=runs&cell=1", "tab=runs&cell=1&held=1",
    // ADR-140 Amendment 4: the register wizard's governance step, a source's page, and a source
    // chosen in a pipeline.
    "tab=sources&register=1", "tab=sources&source=1", "tab=sources&source=1&edit=1", "pipeline=source",
    // Phase 6 (ADR-108 Amendment 6, ADR-140 decision 3): a step's drawer in guided and in expert
    // mode, a source's and Map's Preview, Test and Deploy in the drawer, an expert step read in
    // guided mode, and the Map editor under its strip with a column chosen to bind.
    "pipeline=guided", "pipeline=expert&mode=expert", "pipeline=preview", "pipeline=map-preview",
    "pipeline=test", "pipeline=deploy", "pipeline=expert-step&expert=1", "pipeline=map",
    // Phase 6's exit (ADR-140 Amendment 10): the Map editor holding chapter 4's whole reports map.
    "pipeline=reports-map",
    // Phase 7b (ADR-140 Amendment 12): a Lookup's and a Join's drawer with their live samples, a
    // Derive's Preview, a Filter half set with the save gate's refusals, the Map editor over the
    // last step's table, and a Union's and a Dedupe's drawer.
    "contacts=built&staged=lookup", "contacts=built&staged=join", "contacts=built&staged=derive-preview",
    "contacts=1&staged=filter", "contacts=built&staged=map", "contacts=1&staged=union",
    "contacts=1&staged=dedupe",
  ],
  // ADR-140 Amendment 4: the Connections section, served by the page itself. ADR-145 decision 5:
  // every section in the side list, a coming placeholder open.
  "admin-harness.html": [
    "open=connections&rights=administer_system",
    "rights=manage_people,manage_dashboards,operate_schedules,administer_system,manage_ontology,read_audit&open=Audit%20(coming)",
    // L2.4 part 2: Datasets' details (policy with its warning, Authors, linked cases), Change
    // owner… open, a removed case's dry run shown, and System's Dataset owners may be.
    "rights=administer_system&serve=datasets&show=details",
    "rights=administer_system&serve=datasets&show=owner",
    "rights=administer_system&serve=datasets&show=dry-run",
    "rights=administer_system&serve=datasets&open=System",
    // L2.5: People's row with its case levels and a case with no Author, Disable… with its
    // transfers, and Roles: the lists, a role's form, a team with its lead and cover.
    "rights=manage_people&serve=people",
    "rights=manage_people&serve=people&show=disable",
    "rights=manage_people&serve=people&open=Roles",
    "rights=manage_people&serve=people&open=Roles&show=role-form",
    "rights=manage_people&serve=people&open=Roles&show=team",
    "rights=manage_people&serve=people&open=Roles&show=versions",
    "rights=manage_people&serve=people&show=refused",
  ],
};

const pages = readdirSync(KEYBOARD).filter((name) => name.endsWith(".html")).sort();

function appliesBrand(page: string): boolean {
  const source = new URL(page.replace(/\.html$/, ".tsx"), KEYBOARD);
  try {
    return readFileSync(source, "utf8").includes("applyHarnessBrand");
  } catch {
    return false;
  }
}

// WCAG 2.5.3 Label in Name for form fields, which axe-core does not test: its
// `label-content-name-mismatch` rule reads only controls named from their content (buttons, links),
// never an input, select or textarea whose `aria-label` overrides the visible `<label>` around it.
// Found by the GDS re-audit (step 9b, 2 November 2026): "Why, in words (required)" was spoken as
// "Reason for closing", so a speech-input user saying what they saw reached nothing. The visible
// label, up to its first comma, colon or bracket, must appear in the field's accessible name as
// whole words (2.5.3's requirement; the understanding document's best practice puts it first, and
// the rest may add context, as "On (day of the week)").
// Returns each offender as "visible → name", so a failure says what to change.
async function labelInNameOffenders(page: import("@playwright/test").Page): Promise<string[]> {
  return page.evaluate(() => {
    const offenders: string[] = [];
    for (const control of document.querySelectorAll<HTMLElement>("input, select, textarea")) {
      if (control instanceof HTMLInputElement && control.type === "hidden") continue;
      const name = control.getAttribute("aria-label");
      if (!name) continue;
      const label =
        control.closest("label") ??
        (control.id ? document.querySelector(`label[for="${CSS.escape(control.id)}"]`) : null);
      if (!label || !label.checkVisibility()) continue;
      const copy = label.cloneNode(true) as HTMLElement;
      copy.querySelectorAll("input, select, textarea, button, [aria-hidden='true']").forEach((n) => n.remove());
      const visible = (copy.textContent ?? "").replace(/\s+/g, " ").trim();
      const lead = visible.split(/[:,(]/)[0].trim().toLowerCase();
      const escaped = lead.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const words = new RegExp(`(^|[^\\p{L}\\p{N}])${escaped}($|[^\\p{L}\\p{N}])`, "u");
      if (lead && !words.test(name.toLowerCase())) offenders.push(`"${visible}" → "${name}"`);
    }
    return offenders;
  });
}

test("the scan found the harness pages", () => {
  // A wrong directory would make every test below vanish rather than fail.
  expect(pages.length).toBeGreaterThan(30);
});

for (const name of pages) {
  const variants = ["dark", "light", ...(appliesBrand(name) ? ["govuk"] : [])] as const;
  for (const state of ["", ...(EXTRA_STATES[name] ?? [])]) {
    for (const variant of variants) {
      const query = [state, variant === "govuk" ? "brand=govuk" : ""].filter(Boolean).join("&");
      const title = `${name}${state ? ` ${state}` : ""} (${variant})`;
      test(`${title} has no automated WCAG 2.2 A or AA violations`, async ({ page }) => {
        await page.emulateMedia({ reducedMotion: "reduce" });
        await page.goto(`/keyboard/${name}${query ? `?${query}` : ""}`);
        await page.waitForLoadState("networkidle");
        await page.evaluate(() => document.fonts.ready);
        if (variant === "light") {
          await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
        }
        if (variant === "govuk") {
          await expect(page.locator("html")).toHaveAttribute("data-brand", "govuk");
        }
        let builder = new AxeBuilder({ page }).withTags(WCAG_TAGS);
        for (const selector of HARNESS_ONLY[name] ?? []) builder = builder.exclude(selector);
        const results = await builder.analyze();
        expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
      });
    }
    // The words do not change with the theme or the brand, so one look per state.
    test(`${name}${state ? ` ${state}` : ""}: every labelled field's name contains its visible label (2.5.3)`, async ({
      page,
    }) => {
      await page.goto(`/keyboard/${name}${state ? `?${state}` : ""}`);
      await page.waitForLoadState("networkidle");
      expect(await labelInNameOffenders(page)).toEqual([]);
    });
  }
}
