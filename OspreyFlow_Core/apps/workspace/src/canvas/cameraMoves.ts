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
