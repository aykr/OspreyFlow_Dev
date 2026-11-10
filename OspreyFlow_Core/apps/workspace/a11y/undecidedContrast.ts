// WCAG 1.4.3 where axe-core cannot decide it (rules-b's T3, 10 November 2026). axe leaves
// `color-contrast` *incomplete*, never violated, when it cannot find the text's background: inside a
// fixed, transformed overlay (L2.11a's dialog plant stayed green), for 1:1 text it reads as
// deliberate hiding (platform-b's P6), over another element. Every axe scan in the workspace and the
// install harness calls `checkUndecidedContrast` after its violations (`a11y/*.spec.ts`,
// `../harness/a11y/*.spec.ts`, which import this file by path).
//
// This half reads, in the page, what the judgement needs: each node's computed styles up to `<html>`,
// which of those elements lie under each probed point of its text, a painted `::before`/`::after`
// laid over it, and what `elementsFromPoint` finds under and over the text. `src/color/textContrast.ts`
// judges it, in Node, unit-tested at every boundary. It fails closed: an element painted under or over
// the text that is neither the node nor an ancestor (map tiles under a chip, an overlay, a drawn line),
// a filter or blend, a colour it cannot read, a node in a frame or shadow root are offenders, never
// passes. Text axe calls partly covered is measured when the probe finds nothing foreign at its points
// (rules-b's T3 report, decision 3). Its limit: the probe samples points (the left, middle and right of
// up to five line boxes, the first, middle and last among them), not every pixel; a cover lying wholly
// between them is carried to T3b.
import type { Page } from "@playwright/test";

import {
  excuses,
  judge,
  type Judgement,
  type ListedFinding,
  type Sample,
} from "../src/color/textContrast";

/** What this reads of an axe-core result: the rules left incomplete, their nodes and axe's reasons. */
export interface AxeIncomplete {
  incomplete: {
    id: string;
    nodes: { target: unknown[]; any?: { data?: unknown }[] }[];
  }[];
}

/** Listed findings by selector: each excused only while it measures as listed (`excuses`). */
export type ListedFindings = Record<string, ListedFinding>;

interface Asked {
  selector: string | null;
  unreadable: string | null;
  axeReason: string | null;
}

async function read(page: Page, asked: Asked[]): Promise<Sample[]> {
  return page.evaluate((nodes) => {
    const REPLACED = new Set(["CANVAS", "IMG", "SVG", "VIDEO", "IFRAME", "PICTURE", "OBJECT", "EMBED"]);
    const name = (e: Element) =>
      `${e.tagName.toLowerCase()}${e.classList.length ? `.${e.classList[0]}` : ""}`;
    const transparent = (css: string) => /^rgba\(0, 0, 0, 0\)$|^transparent$/.test(css);
    const pseudoPaints = (e: Element, pseudo: string) => {
      const p = getComputedStyle(e, pseudo);
      const shows = p.content !== "none" && p.content !== "normal";
      return shows && (!transparent(p.backgroundColor) || p.backgroundImage !== "none");
    };
    // SVG's drawn parts: its shapes paint, its root's empty box does not (a board's link layer).
    const SHAPES = new Set(["LINE", "PATH", "RECT", "CIRCLE", "ELLIPSE", "POLYLINE", "POLYGON", "TEXT", "TSPAN", "IMAGE", "USE"]);
    // A foreign element that changes what is seen at the point (x, y): a replaced element or an SVG
    // shape, a background, a painted `::before`/`::after`, a filter or blend, an inset shadow, a border
    // under the point, or words of its own.
    const painted = (e: Element, x: number, y: number) => {
      const s = getComputedStyle(e);
      const tag = e.tagName.toUpperCase();
      if (tag === "SVG") return !transparent(s.backgroundColor) || s.backgroundImage !== "none";
      if (REPLACED.has(tag) || SHAPES.has(tag)) return true;
      if (!transparent(s.backgroundColor) || s.backgroundImage !== "none") return true;
      if (s.filter !== "none" || s.backdropFilter !== "none" || s.mixBlendMode !== "normal") return true;
      if (/inset/.test(s.boxShadow)) return true;
      if (pseudoPaints(e, "::before") || pseudoPaints(e, "::after")) return true;
      const r = e.getBoundingClientRect();
      const w = (side: string) => (s.getPropertyValue(`border-${side}-style`) === "none" ? 0 : parseFloat(s.getPropertyValue(`border-${side}-width`)) || 0);
      if (x < r.left + w("left") || x > r.right - w("right") || y < r.top + w("top") || y > r.bottom - w("bottom")) return true;
      return [...e.childNodes].some((n) => {
        if (n.nodeType !== Node.TEXT_NODE || (n.textContent ?? "").trim() === "") return false;
        const words = document.createRange();
        words.selectNodeContents(n);
        return [...words.getClientRects()].some((t) => x >= t.left && x <= t.right && y >= t.top && y <= t.bottom);
      });
    };
    // An ancestor hides what lies beneath it only when its own background is opaque and neither it
    // nor anything above it is translucent (an opacity lets the group's underlay through).
    const opaque = (e: Element) => {
      const bg = getComputedStyle(e).backgroundColor;
      if (!(/^rgb\(/.test(bg) || /^color\(srgb [^/]*\)$/.test(bg))) return false;
      for (let at: Element | null = e; at; at = at.parentElement) {
        if (getComputedStyle(at).opacity !== "1") return false;
      }
      return true;
    };
    const blank = (unreadable: string, selector: string, axeReason: string | null) => ({
      selector, unreadable, text: "", color: "", fontSize: "", fontWeight: "", chain: [],
      overlappedBy: null, axeReason,
    });
    return nodes.map(({ selector, unreadable, axeReason }) => {
      if (unreadable || !selector) return blank(unreadable ?? "no selector", selector ?? "?", axeReason);
      let el: HTMLElement | null = null;
      try {
        el = document.querySelector<HTMLElement>(selector);
      } catch {
        // An invalid selector: unreadable below.
      }
      if (!el) return blank("not found to measure", selector, axeReason);
      // The text's own boxes, scrolled into view, and points across each: its left, middle and right
      // at mid-height, for up to five line boxes.
      const range = document.createRange();
      range.selectNodeContents(el);
      const boxes = () => {
        const found = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
        return found.length ? found : [el.getBoundingClientRect()];
      };
      let rects = boxes();
      const inView = (r: DOMRect) => r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth;
      if (!rects.every(inView)) {
        el.scrollIntoView({ block: "center", inline: "center" });
        rects = boxes();
      }
      // The left, middle and right of up to five line boxes, spread from the first to the last.
      const picks = rects.length <= 5 ? rects : [0, 1, 2, 3, 4].map((k) => rects[Math.round((k * (rects.length - 1)) / 4)] as DOMRect);
      const points = picks.flatMap((r) => {
        const inset = Math.min(2, r.width / 4);
        const y = r.top + r.height / 2;
        return [[r.left + inset, y], [r.left + r.width / 2, y], [r.right - inset, y]] as const;
      });
      const chain = [];
      for (let at: Element | null = el; at; at = at.parentElement) {
        const s = getComputedStyle(at);
        let paintedPseudo: string | null = null;
        for (const pseudo of ["::before", "::after"]) {
          // Laid over the box (absolute or fixed), so it may lie under the text; an inline one sits
          // beside it, as a bullet does. axe's own `pseudoContent` reason fails it either way.
          if (pseudoPaints(at, pseudo) && /absolute|fixed/.test(getComputedStyle(at, pseudo).position)) {
            paintedPseudo = pseudo;
          }
        }
        const box = at.getBoundingClientRect();
        const covers = points.map(([x, y]) => x >= box.left && x <= box.right && y >= box.top && y <= box.bottom);
        chain.push({
          name: name(at), backgroundColor: s.backgroundColor, backgroundImage: s.backgroundImage,
          opacity: s.opacity, filter: s.filter, backdropFilter: s.backdropFilter,
          mixBlendMode: s.mixBlendMode, paintedPseudo, covers,
        });
      }
      if (axeReason === "pseudoContent" && !chain.some((l) => l.paintedPseudo) && chain[0]) {
        chain[0].paintedPseudo = "::before or ::after (axe: pseudoContent)";
      }
      // Under and over the text: at each point, from the top of the stack, every element until an
      // opaque ancestor; anything painted that is neither the node, inside it, nor an ancestor is a
      // surface the walk up the tree cannot see. `elementsFromPoint` leaves out whatever has
      // `pointer-events: none` (the map's chip, an overlay laid over the page), so for the probe every
      // element takes pointer events, by a style sheet removed straight after.
      let overlappedBy: string | null = null;
      const lift = document.createElement("style");
      lift.textContent = "*, *::before, *::after { pointer-events: auto !important; }";
      document.head.append(lift);
      try {
        for (const [x, y] of points) {
          if (overlappedBy) break;
          for (const e of document.elementsFromPoint(x, y)) {
            if (e === el || e.contains(el)) {
              if (opaque(e)) break;
              continue;
            }
            if (el.contains(e)) continue;
            if (painted(e, x, y)) {
              overlappedBy = name(e);
              break;
            }
          }
        }
      } finally {
        lift.remove();
      }
      const style = getComputedStyle(el);
      return {
        selector, unreadable: null, axeReason, chain, overlappedBy,
        text: (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40),
        color: style.color, fontSize: style.fontSize, fontWeight: style.fontWeight,
      };
    });
  }, asked);
}

/** Every colour-contrast node axe left incomplete in `results`, read and judged. */
export async function judgeUndecided(page: Page, results: AxeIncomplete): Promise<Judgement[]> {
  const asked: Asked[] = results.incomplete
    .filter((rule) => rule.id === "color-contrast")
    .flatMap((rule) =>
      rule.nodes.map((node) => {
        const data = node.any?.[0]?.data as { messageKey?: string } | undefined;
        const axeReason = data?.messageKey ?? null;
        const [only] = node.target;
        // A frame's or a shadow root's node: axe's target is a path, never one selector here.
        if (node.target.length !== 1 || typeof only !== "string") {
          return {
            selector: JSON.stringify(node.target),
            unreadable: "a node in a frame or a shadow root",
            axeReason,
          };
        }
        return { selector: only, unreadable: null, axeReason };
      }),
    );
  return (await read(page, asked)).map(judge);
}

/**
 * The scan's undecided contrast, measured: `unlisted` names each failure no listed finding excuses
 * ("selector: why ("text")"), and `gone` each listed finding no longer found as listed, so the list
 * never outlives what it excuses.
 */
export async function checkUndecidedContrast(
  page: Page,
  results: AxeIncomplete,
  known: ListedFindings = {},
): Promise<{ unlisted: string[]; gone: string[] }> {
  const failing = (await judgeUndecided(page, results)).filter((j) => j.why);
  const excused = (j: Judgement) => Object.hasOwn(known, j.selector) && excuses(known[j.selector], j);
  return {
    unlisted: failing
      .filter((j) => !excused(j))
      .map((j) => {
        const own = j.ratio === null ? ` [own surfaces ${j.ownRatio === null ? "unread" : `${j.ownRatio.toFixed(2)}:1`}]` : "";
        return `${j.selector}: ${j.why}${own} ("${j.text}")`;
      }),
    gone: Object.keys(known).filter((selector) => !failing.some((j) => j.selector === selector && excused(j))),
  };
}
