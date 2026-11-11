// The contrast probe's guards, each shown red with that guard removed (the orchestrator's review of
// T3b at 9697ad3, items 1 and 2). Run through `node a11y/plants/run.mjs`, never by the a11y config.
//
// Every plant lays something over half of Show as BPMN's task label, "If a Person meets", whose own
// surfaces give it 13:1, so a probe that wrongly takes the cover as hiding the words judges only the
// uncovered half and passes them silently. Each plant names the outcome of the real probe and of every
// variant (`variants.mjs`): `silentWithout` lists the variants that must pass the words silently (the
// guard's red); every other variant must give the real probe's outcome. A guard the browser already
// enforces (its hit test respects `clip-path` and `border-radius`) cannot be shown red; its plant says
// so in `unreachable` and shows the real probe and the variant agree.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkUndecidedContrast, type AxeIncomplete } from "../undecidedContrast";
import { VARIANTS } from "./variants.mjs";

type Probe = typeof checkUndecidedContrast;
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];
const WORDS = "If a Person meets";

interface Plant {
  name: string;
  /** Lays the plant in the page; the words' tspan carries id `zz-words`. */
  lay: (page: Page) => Promise<void>;
  real: "flagged" | "passes";
  silentWithout: (keyof typeof VARIANTS)[];
  unreachable?: string;
}

/** A fixed element over the right half of the words, with `style`, inside `wrap` when given. */
const halfCover = (page: Page, style: string, wrap = "") =>
  page.evaluate(([style, wrap]) => {
    const r = document.getElementById("zz-words")!.getBoundingClientRect();
    const place = `position:fixed; z-index:1000; left:${r.left + r.width / 2}px; top:${r.top - 6}px; width:${r.width}px; height:${r.height + 12}px;`;
    const cover = document.createElement("div");
    if (wrap) {
      const outer = document.createElement("div");
      outer.style.cssText = `${place} ${wrap}`;
      cover.style.cssText = `position:absolute; inset:0; ${style}`;
      outer.append(cover);
      document.body.append(outer);
    } else {
      cover.style.cssText = `${place} ${style}`;
      document.body.append(cover);
    }
  }, [style, wrap] as const);

/** A modal dialog away from the words, so the browser's hit test misses them (modal inertness, no attribute). */
const modalWith = (page: Page, ancestor: string, svg: string) =>
  page.evaluate(([ancestor, svg]) => {
    const root = document.getElementById("zz-words")!.closest("svg")!;
    root.style.cssText += svg;
    (root.parentElement as HTMLElement).style.cssText += ancestor;
    const st = document.createElement("style");
    st.textContent = "dialog.zz::backdrop { background: transparent; }";
    document.head.append(st);
    const d = document.createElement("dialog");
    d.className = "zz";
    d.textContent = "A modal far from the words";
    d.style.cssText = "margin:0; left:0; top:0; position:fixed";
    document.body.append(d);
    d.showModal();
  }, [ancestor, svg] as const);

const PLANTS: Plant[] = [
  { name: "a cover with its own opacity", lay: (p) => halfCover(p, "background:#fff; opacity:0.5"), real: "flagged", silentWithout: ["no-opacity-walk"] },
  { name: "a cover in a translucent wrapper", lay: (p) => halfCover(p, "background:#fff", "opacity:0.5"), real: "flagged", silentWithout: ["no-opacity-walk", "own-opacity-only"] },
  {
    name: "a cover painted to its content box, the words under its padding",
    lay: (p) => halfCover(p, "background:#fff; background-clip:content-box; box-sizing:content-box; padding-bottom:40px; height:0"),
    real: "flagged",
    silentWithout: ["no-background-clip"],
  },
  { name: "a cover with a filter", lay: (p) => halfCover(p, "background:#fff; filter:opacity(0.3)"), real: "flagged", silentWithout: ["no-filter"] },
  { name: "a cover in a filtered wrapper", lay: (p) => halfCover(p, "background:#fff", "filter:opacity(0.3)"), real: "flagged", silentWithout: ["cover-only-walk", "no-filter"] },
  { name: "a cover with a blend", lay: (p) => halfCover(p, "background:#fff; mix-blend-mode:difference"), real: "flagged", silentWithout: ["no-blend"] },
  { name: "a cover in a blended wrapper", lay: (p) => halfCover(p, "background:#fff", "mix-blend-mode:difference"), real: "flagged", silentWithout: ["cover-only-walk", "no-blend"] },
  {
    name: "a cover with a mask",
    lay: (p) => halfCover(p, "background:#fff; mask-image:linear-gradient(transparent, transparent); -webkit-mask-image:linear-gradient(transparent, transparent)"),
    real: "flagged",
    silentWithout: ["no-mask"],
  },
  {
    name: "a cover in a masked wrapper",
    lay: (p) => halfCover(p, "background:#fff", "mask-image:linear-gradient(rgba(0,0,0,0.3), rgba(0,0,0,0.3)); -webkit-mask-image:linear-gradient(rgba(0,0,0,0.3), rgba(0,0,0,0.3))"),
    real: "flagged",
    silentWithout: ["cover-only-walk", "no-mask"],
  },
  {
    name: "a cover under a mask border (item 2)",
    lay: (p) => halfCover(p, "background:#fff; -webkit-mask-box-image:linear-gradient(transparent, transparent)"),
    real: "flagged",
    silentWithout: ["no-mask-border"],
  },
  {
    name: "a cover clipped away from the words",
    lay: (p) => halfCover(p, "background:#fff; clip-path:inset(0 0 0 100%)"),
    real: "passes",
    silentWithout: [],
    unreachable: "Chromium's hit test respects clip-path: the clipped cover is never found over the words, so hides() is never asked",
  },
  {
    name: "a cover in a wrapper clipped away from the words",
    lay: (p) => halfCover(p, "background:#fff", "clip-path:inset(0 0 0 100%)"),
    real: "passes",
    silentWithout: [],
    unreachable: "as above, for the wrapper's clip",
  },
  {
    name: "an SVG rect with a CSS background over half the label (item 2)",
    lay: (p) =>
      p.evaluate(() => {
        const words = document.getElementById("zz-words") as unknown as SVGTSpanElement;
        const text = words.closest("text")!;
        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        const w = words.getBBox();
        rect.setAttribute("x", String(w.x + w.width / 2));
        rect.setAttribute("y", String(w.y - 4));
        rect.setAttribute("width", String(w.width));
        rect.setAttribute("height", String(w.height + 8));
        rect.setAttribute("fill", "rgba(255, 255, 255, 0.8)");
        rect.setAttribute("style", "background-color:#fff");
        text.after(rect);
      }),
    real: "flagged",
    silentWithout: ["no-svg-exclusion"],
  },
  {
    name: "an opaque cover, its edge a pixel from a probe point",
    lay: (p) => halfCover(p, "background:#fff"),
    real: "passes",
    silentWithout: [],
    unreachable: "the slack only widens the box hides() accepts; without it a point the browser hit-tests on the edge stays a cover, flagged, never a silent pass",
  },
  {
    name: "a rounded opaque cover, its 12px corners over the words",
    lay: (p) => halfCover(p, "background:#fff; border-radius:12px"),
    real: "passes",
    silentWithout: [],
    unreachable: "Chromium's hit test respects border-radius: a point outside the curve never finds the cover, so the corner test is never what decides",
  },
  {
    name: "a rounded opaque cover, its 50% (elliptical) corners over the words",
    lay: (p) => halfCover(p, "background:#fff; border-radius:50%"),
    // Each corner is read as a circle of the larger radius, stricter than the browser's ellipse: a
    // point inside the curve may be taken as outside it, so the cover stays a cover, never a pass.
    real: "flagged",
    silentWithout: ["no-corner-test"],
  },
  {
    name: "a modal elsewhere, the label's drawing overflowing a 1px box that clips nothing",
    lay: (p) => modalWith(p, "height:1px; overflow:visible", ""),
    real: "flagged",
    silentWithout: [],
    unreachable: "the modal misses every point alike, so without the narrowing every point is hidden and the words are unmeasurable (hidden at every point): flagged either way",
  },
  {
    name: "a modal elsewhere, the label's drawing absolute past a 1px box that clips",
    lay: (p) => modalWith(p, "height:1px; overflow:hidden", "position:absolute"),
    real: "flagged",
    silentWithout: [],
    unreachable: "as above: the out-of-flow drawing escapes the clip, and without the narrowing every point is hidden, so unmeasurable",
  },
];

async function open(page: Page) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/keyboard/rule-standards-harness.html?open=1");
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await page.locator(".show-as-bpmn").first().waitFor();
  await page.evaluate((words) => {
    const t = [...document.querySelectorAll(".show-as-bpmn tspan")].find((e) => e.textContent === words);
    if (!t) throw new Error(`no tspan "${words}"`);
    t.id = "zz-words";
  }, WORDS);
}

/** axe's own result, narrowed to the words' node, read before the plant (a modal hides it from axe). */
async function axeOnWords(page: Page): Promise<AxeIncomplete> {
  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  const incomplete = results.incomplete
    .filter((rule) => rule.id === "color-contrast")
    .map((rule) => ({ ...rule, nodes: rule.nodes.filter((n) => typeof n.target[0] === "string" && n.target.length === 1) }));
  const ours = [];
  for (const rule of incomplete) {
    for (const node of rule.nodes) {
      const isWords = await page.evaluate((sel) => document.querySelector(sel)?.id === "zz-words", node.target[0] as string);
      if (isWords) ours.push(node);
    }
  }
  expect(ours, "axe leaves the words' contrast undecided, as at every-harness's own call site").toHaveLength(1);
  return { incomplete: [{ id: "color-contrast", nodes: ours as AxeIncomplete["incomplete"][number]["nodes"] }] };
}

const probes: [string, Probe][] = [];
test.beforeAll(async () => {
  probes.push(["the probe", checkUndecidedContrast]);
  for (const name of Object.keys(VARIANTS)) {
    const mod = (await import(`./.variants/${name}.ts`)) as { checkUndecidedContrast: Probe };
    probes.push([name, mod.checkUndecidedContrast]);
  }
});

for (const plant of PLANTS) {
  test(plant.name, async ({ page }) => {
    await open(page);
    const results = await axeOnWords(page);
    await plant.lay(page);
    const lines = [`## ${plant.name}${plant.unreachable ? ` (unreachable: ${plant.unreachable})` : ""}`];
    const wrong: string[] = [];
    for (const [name, probe] of probes) {
      const found = (await probe(page, results, {})).unlisted.filter((u) => u.includes(WORDS));
      const got = found.length ? "flagged" : "passes";
      const want = name === "the probe" ? plant.real : plant.silentWithout.includes(name as keyof typeof VARIANTS) ? "passes" : plant.real;
      lines.push(`  ${got === want ? "  " : "!!"} ${name}: ${got}${found.length ? ` (${found.join(" | ")})` : ""}`);
      if (got !== want) wrong.push(`${name}: ${got}, the plant records ${want}`);
    }
    console.log(lines.join("\n"));
    expect(wrong, plant.name).toEqual([]);
  });
}
