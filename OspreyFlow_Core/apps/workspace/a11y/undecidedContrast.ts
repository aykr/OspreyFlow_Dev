// WCAG 1.4.3 where axe-core cannot decide it (rules-b's T3, 10 November 2026). axe leaves
// `color-contrast` *incomplete*, never violated, when it cannot find the text's background: inside a
// fixed, transformed overlay (L2.11a's dialog plant stayed green), for 1:1 text it reads as
// deliberate hiding (platform-b's P6), over another element. Every axe scan in the workspace and the
// install harness calls `checkUndecidedContrast` after its violations (`a11y/*.spec.ts`,
// `../harness/a11y/*.spec.ts`, which import this file by path).
//
// This half reads, in the page, what the judgement needs: each node's computed styles up to `<html>`,
// a painted `::before`/`::after` laid over it, and what `elementsFromPoint` finds under and over its
// text. `src/color/textContrast.ts` judges it, in Node, unit-tested at every boundary. It fails
// closed: an element painted under or over the text that is not the node or an ancestor (map tiles
// under a chip, a picture), a filter or blend, a colour it cannot read, a node in a frame or shadow
// root are offenders, never passes. Its limits: a foreign element with `pointer-events: none` is left
// out by `elementsFromPoint` (only the node and its ancestors are lifted for the probe), and the probe
// samples three points on the text, not every pixel.
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
    const painted = (e: Element) => {
      const s = getComputedStyle(e);
      return REPLACED.has(e.tagName.toUpperCase()) || !transparent(s.backgroundColor) || s.backgroundImage !== "none";
    };
    const opaque = (e: Element) => {
      const bg = getComputedStyle(e).backgroundColor;
      return /^rgb\(/.test(bg) || /^color\(srgb [^/]*\)$/.test(bg);
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
      const chain = [];
      for (let at: Element | null = el; at; at = at.parentElement) {
        const s = getComputedStyle(at);
        let paintedPseudo: string | null = null;
        for (const pseudo of ["::before", "::after"]) {
          const p = getComputedStyle(at, pseudo);
          const shows = p.content !== "none" && p.content !== "normal";
          const paints = !transparent(p.backgroundColor) || p.backgroundImage !== "none";
          // Laid over the box (absolute or fixed), so it may lie under the text; an inline one sits
          // beside it, as a bullet does. axe's own `pseudoContent` reason fails it either way.
          if (shows && paints && /absolute|fixed/.test(p.position)) paintedPseudo = pseudo;
        }
        chain.push({
          name: name(at), backgroundColor: s.backgroundColor, backgroundImage: s.backgroundImage,
          opacity: s.opacity, filter: s.filter, backdropFilter: s.backdropFilter,
          mixBlendMode: s.mixBlendMode, paintedPseudo,
        });
      }
      if (axeReason === "pseudoContent" && !chain.some((l) => l.paintedPseudo)) {
        chain[0].paintedPseudo = "::before or ::after (axe: pseudoContent)";
      }
      // Under and over the text: from the top of the stack at points on it, every element until an
      // ancestor with an opaque background; anything painted that is neither the node, inside it,
      // nor an ancestor is a surface the walk up the tree cannot see.
      const range = document.createRange();
      range.selectNodeContents(el);
      let rects = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
      if (!rects.length) rects = [el.getBoundingClientRect()];
      const inView = (r: DOMRect) => r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth;
      if (!rects.every(inView)) {
        el.scrollIntoView({ block: "center", inline: "center" });
        rects = [...range.getClientRects()].filter((r) => r.width > 0 && r.height > 0);
        if (!rects.length) rects = [el.getBoundingClientRect()];
      }
      let overlappedBy: string | null = null;
      const points = [rects[0], rects[Math.floor(rects.length / 2)], rects[rects.length - 1]].map(
        (r) => [r.left + r.width / 2, r.top + r.height / 2] as const,
      );
      // `elementsFromPoint` leaves out an element with `pointer-events: none` (the map's chip is one),
      // which would hide whether a foreign element lies over the text or under it: the node and its
      // ancestors take pointer events for the probe, and their own inline values are put back.
      const lifted: [HTMLElement, string, string][] = [];
      for (let at: HTMLElement | null = el; at; at = at.parentElement) {
        lifted.push([at, at.style.getPropertyValue("pointer-events"), at.style.getPropertyPriority("pointer-events")]);
        at.style.setProperty("pointer-events", "auto", "important");
      }
      try {
        for (const [x, y] of points) {
          if (overlappedBy) break;
          for (const e of document.elementsFromPoint(x, y)) {
            if (e === el || e.contains(el)) {
              // The node or an ancestor: an opaque one hides whatever lies beneath it.
              if (opaque(e)) break;
              continue;
            }
            if (el.contains(e)) continue;
            if (painted(e)) {
              overlappedBy = name(e);
              break;
            }
          }
        }
      } finally {
        for (const [at, value, priority] of lifted) {
          if (value) at.style.setProperty("pointer-events", value, priority);
          else at.style.removeProperty("pointer-events");
        }
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
          return { selector: JSON.stringify(node.target), unreadable: "a node in a frame or a shadow root", axeReason };
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
    unlisted: failing.filter((j) => !excused(j)).map((j) => `${j.selector}: ${j.why} ("${j.text}")`),
    gone: Object.keys(known).filter((selector) => !failing.some((j) => j.selector === selector && excused(j))),
  };
}
