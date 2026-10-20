import { zoomBandForRatio, type ZoomBand } from "./zoomBands";

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

/** Whether a change of band changes how a link is drawn: in the overview band links take its size
 * clamp and the strength filter, and in the link-detail band their captions; between the two middle
 * bands a link looks the same and only the nodes change (`nodeAttributes.ts`). */
export function bandChangeTouchesLinks(from: ZoomBand, to: ZoomBand): boolean {
  const drawnDifferently = (band: ZoomBand) => band === "overview" || band === "link-detail";
  return drawnDifferently(from) || drawnDifferently(to);
}

/** The part of the renderer a band change needs; a test passes a fake. */
export interface BandRedrawable {
  refresh(opts: {
    partialGraph: { nodes: string[]; edges?: string[] };
    skipIndexation: boolean;
  }): unknown;
  getGraph(): { nodes(): string[]; edges(): string[] };
}

/** A camera listener that draws the canvas again when the zoom crosses into another band. The
 * renderer reruns its reducers only when asked, and a wheel zoom does not ask, so without this a
 * node's band-chosen size and its icon (shown from the neighbourhood band in, ADR-115 Amendment 1)
 * stayed as they were until something else redrew the canvas. Only what the band changes is
 * worked out again — the nodes, and the links only where they look different (`bandChangeTouchesLinks`)
 * — and nothing is indexed again, since a band changes what is drawn, never where: a whole refresh
 * held a 50k/250k graph for two seconds on a real GPU (ADR-118). */
export function redrawOnBandChange(sigma: BandRedrawable, startRatio: number): (state: { ratio: number }) => void {
  let band = zoomBandForRatio(startRatio);
  return ({ ratio }) => {
    const now = zoomBandForRatio(ratio);
    if (now === band) return;
    const links = bandChangeTouchesLinks(band, now);
    band = now;
    const graph = sigma.getGraph();
    sigma.refresh({
      partialGraph: links ? { nodes: graph.nodes(), edges: graph.edges() } : { nodes: graph.nodes() },
      skipIndexation: true,
    });
  };
}
