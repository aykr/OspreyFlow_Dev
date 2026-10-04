// How the canvas draws a link by its type's basis (ADR-081, Amendment 1). The line style is never
// authored: a Direct link is solid and a Probabilistic one is dotted, whatever colour or thickness
// its type declares. These cases read the pixels the canvas has actually painted along each link, so
// they fail if the dotted program is not the one drawing, which a test of the program's name alone
// could not show. The harness's `?fixture=link-style&kind=<kind>` has one pair of people joined by one link drawn
// that way, which the canvas fits to the whole screen.
import { expect, test, type Page } from "@playwright/test";

declare global {
  interface Window {
    __CANVAS__?: { viewportPositionOf: (nodeId: string) => { x: number; y: number } | null };
  }
}

const FIXTURE = (kind: string) => `/keyboard/harness.html?fixture=link-style&kind=${kind}`;
/** Pixels kept clear at each end of a link: the node, and the arrowhead where there is one. */
const TRIM = 30;

interface Reading {
  length: number;
  runs: number; // separate stretches of ink along the link
  duty: number; // the share of the link that has ink
  across: number; // the widest ink, at right angles to the link, in pixels
  red: number;
  green: number;
  blue: number; // the average colour of the ink
}

async function readLink(page: Page, kind: string): Promise<Reading> {
  const a = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id), `${kind}-a`);
  const b = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id), `${kind}-b`);
  if (!a || !b) throw new Error(`no position for the ${kind} pair`);
  // The harness's own buttons sit over part of the canvas; hide them so only the canvas is read.
  await page.addStyleTag({ content: "button, select, label { visibility: hidden !important; }" });
  const png = (await page.screenshot()).toString("base64");
  return page.evaluate(
    async ({ png, a, b, trim }) => {
      const img = new Image();
      img.src = `data:image/png;base64,${png}`;
      await img.decode();
      const canvas = document.createElement("canvas");
      canvas.width = img.width;
      canvas.height = img.height;
      const ctx = canvas.getContext("2d")!;
      ctx.drawImage(img, 0, 0);
      const px = (x: number, y: number) => ctx.getImageData(Math.round(x), Math.round(y), 1, 1).data;
      const back = px(2, 2);
      const delta = (d: Uint8ClampedArray) =>
        Math.max(Math.abs(d[0]! - back[0]!), Math.abs(d[1]! - back[1]!), Math.abs(d[2]! - back[2]!));
      const length = Math.hypot(b.x - a.x, b.y - a.y);
      const ux = (b.x - a.x) / length;
      const uy = (b.y - a.y) / length;
      const nx = -uy;
      const ny = ux;
      const ink: boolean[] = [];
      let across = 0;
      let r = 0;
      let g = 0;
      let bl = 0;
      let n = 0;
      for (let t = trim; t < length - trim; t += 1) {
        let best = 0;
        let width = 0;
        for (let o = -4; o <= 4; o += 1) {
          const d = px(a.x + ux * t + nx * o, a.y + uy * t + ny * o);
          const v = delta(d);
          if (v > 8) width += 1;
          if (v > best) {
            best = v;
            if (o === 0 || Math.abs(o) <= 1) {
              r += d[0]!;
              g += d[1]!;
              bl += d[2]!;
              n += 1;
            }
          }
        }
        across = Math.max(across, width);
        ink.push(best > 8);
      }
      // A one-pixel line can skip a pixel or two where it is rasterised; a gap of two pixels or less is
      // that, not a gap in the line. A dotted link's gaps are four pixels or more.
      for (let i = 0; i < ink.length; i += 1) {
        if (ink[i]) continue;
        let end = i;
        while (end < ink.length && !ink[end]) end += 1;
        if (i > 0 && end < ink.length && end - i <= 2) for (let k = i; k < end; k += 1) ink[k] = true;
        i = end;
      }
      let runs = 0;
      ink.forEach((on, i) => {
        if (on && !ink[i - 1]) runs += 1;
      });
      const duty = ink.length === 0 ? 0 : ink.filter(Boolean).length / ink.length;
      return { length, runs, duty, across, red: n ? r / n : 0, green: n ? g / n : 0, blue: n ? bl / n : 0 };
    },
    { png, a, b, trim: TRIM },
  );
}

async function open(page: Page, kind: string): Promise<void> {
  await page.goto(FIXTURE(kind));
  // Let the layout settle: the pair stops moving, and its link is long enough to read. (Links are not
  // drawn while the canvas is moving, so reading earlier would find none.)
  let last = "";
  await expect
    .poll(
      async () => {
        const p = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id), `${kind}-a`);
        const q = await page.evaluate((id) => window.__CANVAS__?.viewportPositionOf(id), `${kind}-b`);
        if (!p || !q || Math.hypot(p.x - q.x, p.y - q.y) <= TRIM * 2 + 40) return false;
        const now = JSON.stringify([p, q]);
        const still = now === last;
        last = now;
        return still;
      },
      { intervals: [400] },
    )
    .toBe(true);
  await page.waitForTimeout(800);
}

async function read(page: Page, kind: string): Promise<Reading> {
  await open(page, kind);
  return readLink(page, kind);
}

test("a Direct link is solid: one unbroken stretch of ink", async ({ page }) => {
  for (const kind of ["solid", "arrow"]) {
    const reading = await read(page, kind);
    expect(reading.length, `${kind} link is long enough to read`).toBeGreaterThan(TRIM * 2 + 40);
    expect(reading.runs, `${kind} link runs`).toBe(1);
    expect(reading.duty, `${kind} link duty`).toBeGreaterThan(0.95);
  }
});

test("a Probabilistic link is dotted: many short stretches with gaps between", async ({ page }) => {
  for (const kind of ["dotted", "dotted-arrow"]) {
    const reading = await read(page, kind);
    expect(reading.length, `${kind} link is long enough to read`).toBeGreaterThan(TRIM * 2 + 40);
    expect(reading.runs, `${kind} link runs`).toBeGreaterThanOrEqual(4);
    expect(reading.duty, `${kind} link duty`).toBeGreaterThan(0.2);
    expect(reading.duty, `${kind} link duty`).toBeLessThan(0.7);
  }
});

test("a link of a Direct type that carries its own probabilistic mark is dotted (ADR-081 step B)", async ({ page }) => {
  const marked = await read(page, "marked"); // type KNOWS is Direct; the link says probabilistic
  expect(marked.length, "marked link is long enough to read").toBeGreaterThan(TRIM * 2 + 40);
  expect(marked.runs, "marked link runs").toBeGreaterThanOrEqual(4);
  expect(marked.duty, "marked link duty").toBeLessThan(0.7);
  const plain = await read(page, "solid"); // the same type with no mark stays solid
  expect(plain.runs).toBe(1);
});

test("a dotted link is drawn in the colour its type declares, and a solid thick one is thick", async ({ page }) => {
  const dotted = await read(page, "dotted"); // colour: jade
  expect(dotted.green).toBeGreaterThan(dotted.red + 15);
  expect(dotted.green).toBeGreaterThan(dotted.blue + 5);

  const thick = await read(page, "thick"); // thickness 5, colour: rose
  expect(thick.runs).toBe(1); // a Direct link, even with a declared colour, is solid
  expect(thick.across).toBeGreaterThanOrEqual(4);
  expect(thick.red).toBeGreaterThan(thick.green + 15);

  const plain = await read(page, "solid"); // declares nothing: the ordinary line
  expect(plain.across).toBeLessThan(thick.across);
});
