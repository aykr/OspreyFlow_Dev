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

import { checkUndecidedContrast, type ListedFindings } from "./undecidedContrast";
import { readFindings } from "../src/color/textContrast";

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
  // ADR-147: Admin › Maps with a provider being added, a key being entered and an area being added
  // (platform lane P3), and with the basemap built, the glyphs installed and an area run.
  "maps-harness.html": ["open=add", "open=key", "open=area", "built=1"],
  // P4: the analyst's map with the place search's answer drawn, its "more match" words and its
  // refusal (its switch and search on every state).
  "map-view-harness.html": [
    "searched=1",
    "searched=more",
    "searched=fail",
    // P6: the case's gazetteers, each state of the panel (ADR-147 Amendment 2).
    "gazetteers=added",
    "gazetteers=reader",
    "gazetteers=nothing",
    "gazetteers=composite",
    "gazetteers=drawn",
    "gazetteers=unbuilt",
    "gazetteers=failed",
    "gazetteers=refused",
  ],
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
  // L2.12 (ADR-145 Amendment 4 decisions 8–10 and 12): the Figures opened from an alert, the Alert
  // monitoring board first on the Dashboards and as the journey opens it, a Reports Viewer's Home with
  // an alert's two ways on, and the Roles, teams and Authors page.
  "alert-figures-harness.html": ["from=alert", "board=1", "board=1&rule=hotlists&from=alert", "home=1", "help=1"],
  // ADR-146 decisions 2 and 6: Rules and Monitoring at an alert's address, and at one the reader may
  // not see.
  "rules-place-harness.html": ["address=a1", "address=not-yours", "evidence=1"],
  // ADR-146 decision 3 (L2.11a): Show as BPMN's drawing open, and a stored file it does not draw.
  "rule-standards-harness.html": ["open=1", "open=1&file=other"],
  // ADR-145 Amendment 2: the column's fresh-page default, the Inspector alone open.
  "panel-frames-harness.html": ["defaults=1"],
  // L2.3 part 1: the case screen's lightening, each prototype variant (the default is variant a).
  "case-screen-options-harness.html": ["variant=today", "variant=b", "variant=c"],
  // ADR-144 (L3.2b): case views as another member sees them, the Save as a view form, and the banner
  // over an opened view.
  "views-harness.html": ["as=bob", "show=form", "show=lens", "show=merged", "show=merged&notes=open", "asking=delete"],
  // ADR-143 decisions 4 to 7 (L3.3): a board open with its drawn and loaded items, its inspector, its
  // item and link forms and the withdrawal's question; another member's read-only view; a blank board;
  // the boards list with a board from a view chosen, the edit form and an item's menu open, a drawing
// with no case, and a drawn item with its picture shown in its inspector (L3.3).
  "boards-harness.html": [
    "press=From%20a%20view%20of%20this%20case",
    "nocase=1",
    "board=b-wing&pictured=1&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)",
    "board=b-wing",
    "board=b-wing&as=bob",
    "board=b-night",
    "board=b-wing&press=Declare%20a%20Location",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)%7CDraw%20a%20link%E2%80%A6",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)%7CWithdraw%20Unknown%20male%20%E2%80%9CTall%E2%80%9D",
    "board=b-wing&press=Person%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)%7CEdit%20Unknown%20male%20%E2%80%9CTall%E2%80%9D",
    "board=b-wing&press=menu%3APerson%20Unknown%20male%20%E2%80%9CTall%E2%80%9D%20(drawn)",
    // L3.4: the promotion sheet, with an item that cannot go and a warning; the sheet after sending,
    // with what was left out; Promotions from this board.
    "board=b-wing&press=Promote%E2%80%A6",
    "board=b-wing&policy=second_person_reviews&press=Promote%E2%80%A6%7CSend%20for%20review",
  ],
  // ADR-143 decision 10 and Amendment 2 decision 1 (L3.4): the Studio's Analyst promotions with a
  // promotion's details open for review, its rejection's reason asked, the revert command shown, the
  // proposer and a non-Author told why they cannot decide, and a removed case's merge sheet and delete
  // question.
  "promotions-harness.html": [
    "press=Review%20load%20promotion-wing-1",
    "press=Review%20load%20promotion-wing-1%7CReject%20with%20a%20reason",
    // L3.9: a drawn merge's details, with the matches its reviewer approves.
    "press=Review%20load%20promotion-drawn-1",
    "revert=1",
    "as=alice",
    "as=fred",
    "press=Merge%20into%20the%20dataset%20from%20Old%20wing",
    "press=Delete%E2%80%A6%20Old%20wing's%20layer",
  ],
  // ADR-143 Amendment 2 decision 6 (L3.9): the Studio's Merge into a dataset… with its sheet open (the
  // mapping with a type the target lacks, a match, the checks), after the dry run, after the merge, for
  // a second-person target, and with a type mapped onto another (Amendment 7).
  "drawn-merge-harness.html": [
    "choose=src&press=Map%20and%20match",
    "choose=src&press=Map%20and%20match%7CDry%20run",
    "choose=src&press=Map%20and%20match%7CDry%20run%7C4.%20Merge",
    "choose=src&policy=second_person_reviews&press=Map%20and%20match",
    // Amendment 7: a drawn type mapped onto another of the target's types, its property places drawn.
    "choose=src&press=Map%20and%20match&map=Organisation",
  ],
  // ADR-143 Amendment 2 decision 8 (L3.6): a drawn watch's alert opened, with *Open the board*.
  "drawn-watch-alert-harness.html": ["open=w1"],
  // ADR-143 decision 9 (L3.5): the Model tab's proposals block with its decision form, the form's
  // error summary, and as the proposer.
  "model-proposals-harness.html": ["open=accept", "open=decline-error", "as=alice", "as=low"],
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
    // *What raises alerts*: the inventory (ADR-146 decision 5), the hotlists and the watched patterns
    // with their schedules (the alert inbox went in L2.10).
    "tab=watches",
    "tab=rules&sentence=preview",
    // ADR-139 decision 8: a sentence on connection strength.
    "tab=rules&sentence=strength",
    // ADR-139 Amendment 2: the figure on the client's scale.
    "tab=rules&sentence=strength-client",
    "tab=lists",
    // ADR-133 Amendment 9 (L2.11): the manager's Lists tab, read-only, with the latest refreshes.
    "tab=lists&lists=manage",
    // ADR-146 decision 3 (L2.11; the lane-reviewer's item 16): the rule editor on its dataset, a
    // rule on a screening list saved and tested, then shown as BPMN.
    "tab=rules&editor=tested",
    "tab=rules&editor=bpmn",
    "tab=rules&template=high_risk_jurisdiction",
    // ADR-133 stage (d): a whole-deployment rule waiting for a second person (Approve and Reject
    // offered), a scheduled rule's runs and versions open, a sentence set to run every week, a
    // high-severity alert whose close waits for approval, and a list refreshed on a schedule.
    "stage=d&tab=rules&opened=1",
    "stage=d&tab=rules&sentence=schedule",
    "stage=d&open=a-close",
    "stage=d&tab=lists&lists=manage",
    // The GDS re-audit (step 9b, 2 November 2026): an alert opened with its close form (the five
    // closing reasons, step 7b), and a KYC screening alert opened (a close match to a listed party).
    "open=a-hot",
    "open=a-kyc",
    // ADR-146 (L2.10): a routed, suppressed alert opened by its team's lead (the lead's tools), the
    // queue showing every alert (the suppressed and the taken back marked apart), and the inventory
    // is `tab=watches`.
    "open=a-team",
    // ADR-146 decision 2: Rules and Monitoring's Held rows and Changes, and an address the reader may
    // not see.
    "tab=held",
    "tab=changes",
    "address=missing",
  ],
  // ADR-133 decision 6, stage (d): the Checks on load step (the default) and Verify's would-be alerts.
  "checks-on-load-harness.html": ["view=verify"],
  // ADR-140 Amendment 13 (L1.6): Studio › Sources' screening lists as a reader and as whoever may load
  // lists (a failed import in words), the import form with the blank template's column picks, the
  // schedule form, the register wizard over a SQL connection, and a SQL source's page.
  "sources-connectors-harness.html": [
    "serve=1", "serve=1&manage=1", "view=import&template=blank", "view=schedule",
    "view=wizard&serve=1", "view=source&serve=1",
    // The lane review of L1.6: the wizard's read step for each kind of connection.
    "view=wizard&serve=1&connection=c-sql&step=1", "view=wizard&serve=1&connection=c-api&step=1",
    "view=wizard&serve=1&connection=c-json&step=1",
    // ADR-145 Amendment 4 decision 12 (L1.8): the lists and a source's page to someone holding no Studio
    // right, each action described by why and who can.
    "serve=1&rights=none", "view=source&serve=1&rights=none",
  ],
  // ADR-140 decision 1 (redesign phase 2): the Studio's Model, Sources and Runs places, a day's run
  // report with its revert command, and the held rows opened from it (Pipelines is the default).
  "ingest-studio-harness.html": [
    "tab=model", "tab=sources", "tab=runs", "tab=runs&cell=1", "tab=runs&cell=1&held=1",
    // L2.7: the Model tab's count and the reminder above the other tabs.
    "proposed=1",
    // L1.8: each place, and a day's run report, to someone holding no Studio right: why and who can, in words.
    "rights=none", "rights=none&tab=model", "rights=none&tab=sources", "rights=none&tab=runs&cell=1",
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
    // Phase 8 (ADR-140 decisions 3, 12, 13 and 16): a SQL step's drawer with Check SQL's words, a fuzzy
    // match's drawer, the pipeline's YAML in expert mode, Test disclosing an expert step, and an expert
    // step read whole by a person without the right to write one.
    "contacts=built&staged=sql&mode=expert&rights=expert", "contacts=built&staged=fuzzy&mode=expert&rights=expert",
    "contacts=built&staged=yaml&mode=expert&rights=expert", "contacts=built&staged=expert-test&mode=expert&rights=expert",
    "pipeline=expert-step&expert=1&mode=expert",
    // ADR-140 Amendment 9 decision 4 (L1.7): Studio › Releases.
    "tab=releases&rights=releases",
  ],
  // ADR-140 Amendment 4: the Connections section, served by the page itself. ADR-145 decision 5:
  // every section in the side list, a coming placeholder open.
  // L2.7 (ADR-145 decision 11): Needs you drawn open, its entries and their tips; the Studio with
  // two proposed link types, its Model tab's count and the reminder above the other tabs.
  // ADR-110 Amendment 19: the reader's own scheduled loads' notices, and the line saying how many more.
  "needs-you-harness.html": ["open=1", "open=1&notices=1"],
  "admin-harness.html": [
    "open=connections&rights=administer_system",
    "rights=manage_people,manage_dashboards,operate_schedules,administer_system,manage_ontology,read_audit&open=Uploads%20(coming)",
    // L2.4 part 2: Datasets' details (policy with its warning, Authors, linked cases), Change
    // owner… open, a removed case's dry run shown, and System's Dataset owners may be.
    "rights=administer_system&serve=datasets&show=details",
    "rights=administer_system&serve=datasets&show=owner",
    "rights=administer_system&serve=datasets&show=dry-run",
    // L2.5c: a delete's dry run with Admin's own Delete after it.
    "rights=administer_system&serve=datasets&show=delete",
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
    // L2.5b: Disable… with L3.8's items and the note that some are withheld.
    "rights=manage_people&serve=people&show=withheld",
    // L2.6: Audit's stream (withheld and shown words, paging) and its rule audit asked without a
    // case; Operations' What ages with an overdue promotion waiting, above the schedules.
    "rights=read_audit,read_rule_audit&serve=audit",
    "rights=read_audit,read_rule_audit&serve=audit&show=rules",
    "rights=operate_schedules&serve=operations",
    // L2.7: Policies' Grading scheme, read-only with its command; Connections with an API connection
    // listed and the form's SQL fields drawn.
    "rights=administer_system&serve=policies&open=Grading%20scheme",
    "rights=administer_system&serve=connections&open=Connections&show=sql",
  ],
};

// The undecided-contrast findings on main when the measure was added (rules-b's T3, 10 November 2026),
// each carried by its owner (CARRIES) rather than excused, in `contrastFindings.json`: by the test's
// title and the node's selector, with the text it held and either the ratio it measured (a floor:
// worse fails) or the exact reason it could not be measured and what its own surfaces gave (a floor
// too). Fixed ones come off; a new one is never added to make a run green. The owners, by page:
// the map's attribution chip over the map's canvas (platform); the case screen's variant b ⋯ and
// places' open More views under GOV.UK (shell); the boards' handles and labels where a link line or
// another item lies at them (case); Home's key cap at `opacity: 0.8` (home). Show as BPMN's words, once listed, measure on their task box since T3b.
const CONTRAST_FINDINGS: Record<string, ListedFindings> = readFindings(
  JSON.parse(readFileSync(new URL("./contrastFindings.json", import.meta.url), "utf8")),
);

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

// Every look's title, as each test below is named, so a listed finding under a mistyped title fails.
const TITLES = new Set<string>();

for (const name of pages) {
  const variants = ["dark", "light", ...(appliesBrand(name) ? ["govuk"] : [])] as const;
  for (const state of ["", ...(EXTRA_STATES[name] ?? [])]) {
    for (const variant of variants) {
      const query = [state, variant === "govuk" ? "brand=govuk" : ""].filter(Boolean).join("&");
      const title = `${name}${state ? ` ${state}` : ""} (${variant})`;
      TITLES.add(title);
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
        // axe's undecided colour contrast, measured here (1.4.3): a shortfall or an unmeasurable
        // node fails, unless it is a listed finding carried by its owner, and a listed one that is
        // gone fails too, so the list never outlives what it excuses.
        const { unlisted, gone } = await checkUndecidedContrast(page, results, CONTRAST_FINDINGS[title]);
        expect(unlisted, "colour contrast axe left undecided, too low or unmeasurable").toEqual([]);
        expect(gone, "listed contrast findings no longer found as listed: update CONTRAST_FINDINGS").toEqual([]);
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

test("every listed contrast finding names a look this file scans", () => {
  expect(Object.keys(CONTRAST_FINDINGS).filter((title) => !TITLES.has(title))).toEqual([]);
});
