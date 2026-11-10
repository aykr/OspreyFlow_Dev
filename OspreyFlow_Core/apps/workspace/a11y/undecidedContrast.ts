// WCAG 1.4.3 where axe-core cannot decide it (rules-b's T3, 10 November 2026). axe leaves
// `color-contrast` *incomplete*, never violated, when it cannot find the text's background: inside a
// fixed, transformed overlay (L2.11a's dialog plant stayed green), for 1:1 text it reads as
// deliberate hiding (platform-b's P6), over another element. Every axe scan in the workspace and the
// install harness calls `checkUndecidedContrast` after its violations (`a11y/*.spec.ts`,
// `../harness/a11y/*.spec.ts`, which import this file by path).
//
// This half reads, in the page, what the judgement needs: each node's computed styles up to `<html>`,
// which of those elements lie under each probed point of its own words, a painted `::before`/`::after`
// laid over it, the SVG shapes under an SVG label's words, the browser's own canvas colour, and what
// `elementsFromPoint` finds at each point, with every element taking pointer events and none inert for
// the probe. `src/color/textContrast.ts` judges it, in Node, unit-tested at every boundary. It fails
// closed: an element painted under or over the words that is neither the node nor an ancestor (map
// tiles under a chip, an overlay, a drawn line, a descendant's background, a shadow reaching them), a
// filter or blend, a colour it cannot read, a node in a frame or shadow root are offenders, never
// passes. Text axe calls partly covered is measured when the probe finds nothing foreign at its points
// (rules-b's T3 report, decision 3). Its limit: points every 8px along the words (three rows where axe
// says partly covered; wider apart past 600 points), so a cover narrower than that between two of them
// passes.
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
    // SVG's drawn parts: its shapes paint, its root's empty box does not (a board's link layer).
    const SHAPES = new Set(["LINE", "PATH", "RECT", "CIRCLE", "ELLIPSE", "POLYLINE", "POLYGON", "TEXT", "TSPAN", "IMAGE", "USE"]);
    const SVG_TEXT = new Set(["TEXT", "TSPAN", "TEXTPATH"]);
    const name = (e: Element) =>
      `${e.tagName.toLowerCase()}${e.classList.length ? `.${e.classList[0]}` : ""}`;
    const transparent = (css: string) => /^rgba\(0, 0, 0, 0\)$|^transparent$/.test(css);
    const within = (x: number, y: number, r: { left: number; right: number; top: number; bottom: number }) =>
      x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
    const bordered = (s: CSSStyleDeclaration) =>
      ["top", "right", "bottom", "left"].some(
        (side) => s.getPropertyValue(`border-${side}-style`) !== "none" && parseFloat(s.getPropertyValue(`border-${side}-width`)) > 0,
      );
    // A `::before`/`::after` that paints: a background, a border, or words of its own (`content: "…"`).
    const pseudoPaints = (e: Element, pseudo: string) => {
      const p = getComputedStyle(e, pseudo);
      if (p.content === "none" || p.content === "normal") return false;
      const words = /^["'].*\S.*["']$/.test(p.content);
      return words || !transparent(p.backgroundColor) || p.backgroundImage !== "none" || bordered(p);
    };
    // A colour as an `rgba()` string with `alpha` folded in, read through the browser's own parser;
    // a fill it cannot turn into a colour (`url(#…)`, `none`) comes back as written, for the judgement
    // to refuse.
    const probeColour = document.createElement("i");
    probeColour.style.display = "none";
    document.documentElement.append(probeColour);
    const withAlpha = (css: string, alpha: number): string => {
      probeColour.style.color = "";
      probeColour.style.color = css;
      if (!probeColour.style.color) return css;
      const got = getComputedStyle(probeColour).color;
      if (alpha >= 1) return got;
      const m = got.match(/^rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)$/);
      return m ? `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${(m[4] === undefined ? 1 : +m[4]) * alpha})` : `${got} with opacity ${alpha}`;
    };
    // The canvas the browser draws under everything, by the page's own colour scheme.
    const canvas = document.createElement("i");
    canvas.style.cssText = "display:none; background-color: Canvas";
    document.documentElement.append(canvas);
    const pageColour = getComputedStyle(canvas).backgroundColor;
    canvas.remove();
    // Every element with an outer box-shadow, and each shadow's offset, blur and spread; the box each
    // reaches is taken per node, after any scroll (`reachOf`).
    const shadowed: { e: Element; parts: [number, number, number, number][] }[] = [];
    for (const e of document.querySelectorAll("*")) {
      const shadow = getComputedStyle(e).boxShadow;
      if (shadow === "none") continue;
      const parts: [number, number, number, number][] = [];
      for (const one of shadow.split(/,(?![^(]*\))/)) {
        if (/inset/.test(one)) continue;
        const lengths = (one.replace(/(rgba?|color|oklab|oklch)\([^)]*\)/g, "").match(/-?[\d.]+px/g) ?? []).map(parseFloat);
        const [dx = 0, dy = 0, blur = 0, spread = 0] = lengths;
        parts.push([dx, dy, blur, spread]);
      }
      if (parts.length) shadowed.push({ e, parts });
    }
    // The box a shadow reaches: the element's box moved by its offset, grown (or shrunk) by its spread,
    // then grown by its blur radius.
    const reachOf = (r: DOMRect, [dx, dy, blur, spread]: [number, number, number, number]) => {
      const grow = spread + blur;
      return { left: r.left + dx - grow, right: r.right + dx + grow, top: r.top + dy - grow, bottom: r.bottom + dy + grow };
    };
    // A foreign element that changes what is seen at the point (x, y): a replaced element or an SVG
    // shape, a background, a filter or blend, a shadow, a painted pseudo-element, a border under the
    // point, or words of its own there.
    const painted = (e: Element, x: number, y: number) => {
      const s = getComputedStyle(e);
      const tag = e.tagName.toUpperCase();
      if (s.filter !== "none" || s.backdropFilter !== "none" || s.mixBlendMode !== "normal") return true;
      if (/inset/.test(s.boxShadow)) return true;
      if (!transparent(s.backgroundColor) || s.backgroundImage !== "none") return true;
      if (pseudoPaints(e, "::before") || pseudoPaints(e, "::after")) return true;
      const r = e.getBoundingClientRect();
      const w = (side: string) => (s.getPropertyValue(`border-${side}-style`) === "none" ? 0 : parseFloat(s.getPropertyValue(`border-${side}-width`)) || 0);
      if (x < r.left + w("left") || x > r.right - w("right") || y < r.top + w("top") || y > r.bottom - w("bottom")) return true;
      if (tag !== "SVG" && (REPLACED.has(tag) || SHAPES.has(tag))) return true;
      return [...e.childNodes].some((n) => {
        if (n.nodeType !== Node.TEXT_NODE || (n.textContent ?? "").trim() === "") return false;
        const words = document.createRange();
        words.selectNodeContents(n);
        return [...words.getClientRects()].some((t) => within(x, y, t));
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
    // An SVG shape under an SVG label's words that is a plain surface there: a rect, circle, ellipse,
    // polygon or path whose fill (a colour, not a pattern or gradient) covers the point and whose
    // stroke does not, with no filter, mask or blend from it up to the ancestor it shares with the
    // words. It is laid at that ancestor's place under the words, with every opacity on its own branch.
    // Anything else under the words is a cover. `chainOf` is the words' node, then its ancestors.
    const PLAIN = new Set(["RECT", "CIRCLE", "ELLIPSE", "POLYGON", "PATH"]);
    let chainOf: Element[] = [];
    const underShape = (e: Element, x: number, y: number): { fill: string; at: number } | null => {
      if (!PLAIN.has(e.tagName.toUpperCase()) || !(e instanceof SVGGeometryElement)) return null;
      const ctm = e.getScreenCTM();
      if (!ctm) return null;
      const pt = new DOMPoint(x, y).matrixTransform(ctm.inverse());
      const f = getComputedStyle(e);
      if (!e.isPointInFill(pt)) return null;
      if (f.stroke !== "none" && parseFloat(f.strokeWidth) > 0 && e.isPointInStroke(pt)) return null;
      const at = chainOf.findIndex((a) => a.contains(e));
      if (at < 1) return null;
      const shared = chainOf[at] as Element;
      let alpha = parseFloat(f.fillOpacity);
      for (let up: Element | null = e; up && up !== shared; up = up.parentElement) {
        const u = getComputedStyle(up);
        if (u.filter !== "none" || u.mask !== "none" || u.mixBlendMode !== "normal") return null;
        alpha *= parseFloat(u.opacity);
      }
      if (!/^(rgb|color|oklab|oklch)/.test(f.fill)) return null;
      return { fill: withAlpha(f.fill, alpha), at };
    };
    const blank = (unreadable: string, selector: string, axeReason: string | null) => ({
      selector, unreadable, text: "", color: "", fontSize: "", fontWeight: "", chain: [],
      overlappedBy: null, axeReason, page: pageColour,
    });
    const MAX_POINTS = 600;
    try {
    return nodes.map(({ selector, unreadable, axeReason }) => {
      if (unreadable || !selector) return blank(unreadable ?? "no selector", selector ?? "?", axeReason);
      let el: Element | null = null;
      try {
        el = document.querySelector(selector);
      } catch {
        // An invalid selector: unreadable below.
      }
      if (!el) return blank("not found to measure", selector, axeReason);
      const node = el;
      const svgText = node instanceof SVGElement && SVG_TEXT.has(node.tagName.toUpperCase());
      // The node's own words: its direct text nodes' boxes (a descendant's words are its own node),
      // or all its contents when it holds none directly.
      const ownText = [...node.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim() !== "");
      const boxes = () => {
        const found = (ownText.length ? ownText : [node]).flatMap((n) => {
          const r = document.createRange();
          r.selectNodeContents(n);
          return [...r.getClientRects()];
        }).filter((r) => r.width > 0 && r.height > 0);
        return found.length ? found : [node.getBoundingClientRect()];
      };
      let rects = boxes();
      const inView = (r: DOMRect) => r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight && r.right <= innerWidth;
      if (!rects.every(inView)) {
        node.scrollIntoView({ block: "center", inline: "center" });
        rects = boxes();
      }
      // Points along every box: every 8px across, at mid-height, or at a fifth, a half and four fifths
      // where axe saw part of the text covered. Past MAX_POINTS the words are unmeasurable, never
      // sampled more thinly.
      const partly = axeReason === "elmPartiallyObscured" || axeReason === "elmPartiallyObscuring";
      const rows = partly ? [0.2, 0.5, 0.8] : [0.5];
      const step = 8;
      const needed = rects.reduce((sum, r) => sum + (Math.floor(Math.max(0, r.width - 4) / step) + 1) * rows.length, 0);
      if (needed > MAX_POINTS) return blank(`more than ${MAX_POINTS} probe points (${needed})`, selector, axeReason);
      const points: [number, number][] = [];
      for (const r of rects) {
        const inset = Math.min(2, r.width / 4);
        const across = Math.max(1, Math.floor((r.width - 2 * inset) / step));
        for (const v of rows) {
          for (let k = 0; k <= across; k += 1) {
            points.push([r.left + inset + ((r.width - 2 * inset) * k) / across, r.top + r.height * v]);
          }
        }
      }
      const chain = [];
      for (let at: Element | null = node; at; at = at.parentElement) {
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
        // An SVG element's own box paints nothing; its shapes are read at each point below.
        const surface = !(at instanceof SVGElement) || at.tagName.toUpperCase() === "SVG";
        chain.push({
          name: name(at), backgroundColor: surface ? s.backgroundColor : "rgba(0, 0, 0, 0)",
          backgroundImage: surface ? s.backgroundImage : "none",
          opacity: s.opacity, filter: s.filter, backdropFilter: s.backdropFilter,
          mixBlendMode: s.mixBlendMode, paintedPseudo, covers: points.map(([x, y]) => within(x, y, box)),
        });
      }
      chainOf = [];
      for (let at: Element | null = node; at; at = at.parentElement) chainOf.push(at);
      if (axeReason === "pseudoContent" && !chain.some((l) => l.paintedPseudo) && chain[0]) {
        chain[0].paintedPseudo = "::before or ::after (axe: pseudoContent)";
      }
      // Under and over the text: at each point, from the top of the stack, every element until an
      // opaque ancestor; anything painted that is neither the node nor an ancestor is a surface the
      // walk up the tree cannot see, except an SVG shape under SVG words in the same drawing, whose
      // fill is laid under them there. `elementsFromPoint` leaves out whatever has `pointer-events:
      // none` or is inert, so for the probe every element takes pointer events (a style sheet) and
      // loses `inert`, both put back straight after.
      let overlappedBy: string | null = null;
      const under: { fill: string; at: number }[][] = points.map(() => []);
      const lift = document.createElement("style");
      lift.textContent = "*, *::before, *::after { pointer-events: auto !important; }";
      document.head.append(lift);
      const inert = [...document.querySelectorAll("[inert]")].map((e) => [e, e.getAttribute("inert") ?? ""] as const);
      for (const [e] of inert) e.removeAttribute("inert");
      try {
        points.forEach(([x, y], p) => {
          if (overlappedBy) return;
          let below = false;
          for (const e of document.elementsFromPoint(x, y)) {
            if (e === node) {
              below = true;
              if (opaque(e)) break;
              continue;
            }
            if (e.contains(node)) {
              if (opaque(e)) break;
              continue;
            }
            if (svgText && below && e instanceof SVGElement &&
                (e as SVGGraphicsElement).ownerSVGElement === (node as SVGGraphicsElement).ownerSVGElement) {
              const laid = underShape(e, x, y);
              if (laid) {
                under[p]?.push(laid);
                continue;
              }
              overlappedBy = name(e);
              return;
            }
            if (painted(e, x, y)) {
              overlappedBy = name(e);
              return;
            }
          }
          for (const { e, parts } of shadowed) {
            if (e === node || e.contains(node) || node.contains(e)) continue;
            const box = e.getBoundingClientRect();
            if (within(x, y, box)) continue;
            if (parts.some((part) => within(x, y, reachOf(box, part)))) {
              overlappedBy = `the shadow of ${name(e)}`;
              return;
            }
          }
        });
      } finally {
        lift.remove();
        for (const [e, value] of inert) e.setAttribute("inert", value);
      }
      const style = getComputedStyle(node);
      // The ink: an SVG label's `fill` (its opacity folded in), else what the text is painted with,
      // `-webkit-text-fill-color` where it is set apart from `color`.
      const ink = svgText
        ? withAlpha(style.fill, parseFloat(style.fillOpacity))
        : style.getPropertyValue("-webkit-text-fill-color") || style.color;
      return {
        selector, unreadable: null, axeReason, chain, overlappedBy, under, page: pageColour,
        text: (node.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 40),
        color: ink, fontSize: style.fontSize, fontWeight: style.fontWeight,
      };
    });
    } finally {
      probeColour.remove();
    }
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
