import { zoomBandForRatio } from "./zoomBands";

/** Draws the canvas again once a camera move has finished. The renderer leaves links out while the
 * camera is moving (`hideEdgesOnMove`), and the move's last frame is drawn before it counts as
 * finished, so without this the links stay missing until something else makes the canvas redraw,
 * which was a click on the empty canvas. Seen 3 October 2026 on the Fixture Corp hub. */
export function redrawWhenCameraStops(sigma: { refresh: () => void }, move: Promise<void>): void {
  void move.then(() => {
    // One frame later, so the move has been counted as finished by the time it is drawn.
    requestAnimationFrame(() => sigma.refresh());
  });
}

/** A camera listener that draws the canvas again when the zoom crosses into another band. The
 * renderer reruns its reducers only when asked, and a wheel zoom does not ask, so without this a
 * node's band-chosen size and its icon (shown from the neighbourhood band in, ADR-115 Amendment 1)
 * stayed as they were until something else redrew the canvas. */
export function redrawOnBandChange(
  sigma: { refresh: () => void },
  startRatio: number,
): (state: { ratio: number }) => void {
  let band = zoomBandForRatio(startRatio);
  return ({ ratio }) => {
    const now = zoomBandForRatio(ratio);
    if (now === band) return;
    band = now;
    sigma.refresh();
  };
}
