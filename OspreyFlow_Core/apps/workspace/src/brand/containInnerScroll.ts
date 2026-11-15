// Inner scrollers never move the page under GOV.UK (the owner's ruling, 15 November 2026, keeping ADR-132's frame).
// Under that brand the footer stands below the workspace and the page scrolls to reach it (`BrandFrame.tsx`). A wheel
// that starts inside a box that scrolls (a drawer's body, where Explore and History are drawn; Ask & Chat's page; the
// empty canvas's start overlay; the Studio's pane; a list) is the box's: once no box on its path can move further that
// way, it stops there and never moves the page, which once took the top bar half off the top of the window. Boxes
// still hand off to the box around them as before, and a wheel over a part of the page that does not scroll (the top
// bar, the canvas's chrome) still scrolls the page to the footer.
//
// A script, not `overscroll-behavior`: Chromium stops a scroll at a box with `overscroll-behavior: contain` even on an
// axis the box cannot scroll, so the property on every box would stop a sideways table swallowing a vertical wheel
// and a short list keeping it from the box around it (measured, 15 November 2026). `keyboard/frame-scroll.spec.ts`
// holds it.

/** Whether `el` scrolls on the wheel's axis at all, and whether it can move further in the wheel's direction. */
function scrollsThatWay(el: Element, deltaX: number, deltaY: number): { scrolls: boolean; further: boolean } {
  const cs = getComputedStyle(el);
  const vertical = Math.abs(deltaY) >= Math.abs(deltaX);
  const overflow = vertical ? cs.overflowY : cs.overflowX;
  const size = vertical ? el.scrollHeight - el.clientHeight : el.scrollWidth - el.clientWidth;
  if (!/(auto|scroll)/.test(overflow) || size <= 1) return { scrolls: false, further: false };
  const at = vertical ? el.scrollTop : el.scrollLeft;
  const delta = vertical ? deltaY : deltaX;
  return { scrolls: true, further: delta > 0 ? at < size - 1 : at > 0 };
}

/** The wheel's own decision, exported for its unit test: whether the page must not move. */
export function holdsThePage(path: readonly Element[], deltaX: number, deltaY: number): boolean {
  let inside = false;
  for (const el of path) {
    const { scrolls, further } = scrollsThatWay(el, deltaX, deltaY);
    if (!scrolls) continue;
    if (further) return false; // a box on the path takes it: the browser scrolls that box, as ever
    inside = true;
  }
  return inside; // inside a box at its end: held; outside every box: the page scrolls, as on any GOV.UK page
}

/** Installs the rule on the document; returns its removal. */
export function containInnerScroll(): () => void {
  const onWheel = (event: WheelEvent) => {
    if (event.ctrlKey) return; // a pinch or a zoom is the browser's
    const path: Element[] = [];
    for (let el = event.target instanceof Element ? event.target : null; el && el !== document.body; el = el.parentElement) {
      path.push(el);
    }
    if (holdsThePage(path, event.deltaX, event.deltaY)) event.preventDefault();
  };
  document.addEventListener("wheel", onWheel, { passive: false });
  return () => document.removeEventListener("wheel", onWheel);
}
