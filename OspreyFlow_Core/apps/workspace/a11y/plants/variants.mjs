// The contrast probe's guards, each removed in turn (the orchestrator's review of T3b at 9697ad3,
// item 1). Each variant is the probe with the edits named; every `from` must occur in
// `a11y/undecidedContrast.ts` exactly once, or the run stops naming it, so a variant never silently
// becomes the probe itself after the probe changes.
export const VARIANTS = {
  // `opaque()`'s opacity walk: none at all, then the element's own opacity only.
  "no-opacity-walk": [
    [`      for (let at: Element | null = e; at; at = at.parentElement) {
        if (getComputedStyle(at).opacity !== "1") return false;
      }
      return true;`, `      return true;`],
  ],
  "own-opacity-only": [
    [`      for (let at: Element | null = e; at; at = at.parentElement) {
        if (getComputedStyle(at).opacity !== "1") return false;
      }
      return true;`, `      return getComputedStyle(e).opacity === "1";`],
  ],
  // `hides()`'s background-clip test.
  "no-background-clip": [[`if (!opaque(e) || s.backgroundClip !== "border-box") return false;`, `if (!opaque(e)) return false;`]],
  // `hides()`'s walk from the cover up: each property in turn, then the walk cut to the cover alone.
  "no-filter": [[`if (u.filter !== "none" || u.backdropFilter !== "none" || u.mixBlendMode !== "normal") return false;`, `if (u.backdropFilter !== "none" || u.mixBlendMode !== "normal") return false;`]],
  "no-blend": [[`if (u.filter !== "none" || u.backdropFilter !== "none" || u.mixBlendMode !== "normal") return false;`, `if (u.filter !== "none" || u.backdropFilter !== "none") return false;`]],
  "no-mask": [[`if (u.maskImage !== "none" || u.getPropertyValue("-webkit-mask-image") !== "none" || u.clipPath !== "none") return false;`, `if (u.clipPath !== "none") return false;`]],
  "no-clip-path": [[`if (u.maskImage !== "none" || u.getPropertyValue("-webkit-mask-image") !== "none" || u.clipPath !== "none") return false;`, `if (u.maskImage !== "none" || u.getPropertyValue("-webkit-mask-image") !== "none") return false;`]],
  "no-mask-border": [[`if (border.some((v) => v !== "" && v !== "none")) return false;`, ``]],
  "cover-only-walk": [[`for (let up: Element | null = e; up; up = up.parentElement) {
        const u = getComputedStyle(up);`, `for (let up: Element | null = e; up; up = null) {
        const u = getComputedStyle(up);`]],
  // `opaque()`'s SVG exclusion (item 2, 7befa52).
  "no-svg-exclusion": [[`      if (e instanceof SVGElement && !outermostSvg(e)) return false;
`, ``]],
  // The exclusion as 7befa52 had it, by tag: a nested <svg> passes for the outermost.
  "svg-by-tag": [[`      if (e instanceof SVGElement && !outermostSvg(e)) return false;`, `      if (e instanceof SVGElement && e.tagName.toUpperCase() !== "SVG") return false;`]],
  // The pixel of slack round the cover's box, and the rounded-corner test.
  "no-slack": [[`const r = { left: box.left - 1, top: box.top - 1, right: box.right + 1, bottom: box.bottom + 1, width: box.width + 2, height: box.height + 2 };`, `const r = { left: box.left, top: box.top, right: box.right, bottom: box.bottom, width: box.width, height: box.height };`]],
  "no-corner-test": [[`      return corners.every(([corner, cx, cy, sx, sy]) => {`, `      return corners.length >= 0 || corners.every(([corner, cx, cy, sx, sy]) => {`]],
  // The clip check's narrowing: an ancestor that clips nothing, and one past an out-of-flow box.
  "no-overflow-narrowing": [[`if (c.overflowX === "visible" && c.overflowY === "visible") return false;`, ``]],
  "no-flow-narrowing": [[`if (/absolute|fixed/.test(getComputedStyle(below).position)) flowing = false;`, `void below;`]],
  "no-inline-narrowing": [[`if (!flowing || /^inline/.test(c.display) || c.display === "contents") return false;`, `if (!flowing) return false;`]],
};
