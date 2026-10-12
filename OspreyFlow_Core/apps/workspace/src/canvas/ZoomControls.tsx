// The canvas's zoom group (ADR-097 step 2, design review item 10; ADR-115 E4, the reference): zoom
// out, the zoom as a percentage in mono, zoom in, and fit everything in view, which F on the canvas
// also does. It sits under the legend at the canvas's top right.
export interface ZoomControlsProps {
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  /** The camera's zoom, 100 at its starting scale; absent while unknown. */
  percent?: number;
}

export function ZoomControls({ onZoomIn, onZoomOut, onFit, percent }: ZoomControlsProps) {
  return (
    <div role="group" aria-label="Zoom" className="canvas-zoom">
      <button type="button" className="canvas-zoom__button" aria-label="Zoom out" title="Zoom out" onClick={onZoomOut}>
        −
      </button>
      <span className="canvas-zoom__readout" aria-label={percent === undefined ? "Zoom" : `Zoom ${percent}%`}>
        <span className="value">{percent === undefined ? "—" : `${percent}%`}</span>
      </span>
      <button type="button" className="canvas-zoom__button" aria-label="Zoom in" title="Zoom in" onClick={onZoomIn}>
        +
      </button>
      <button
        type="button"
        className="canvas-zoom__button"
        aria-label="Fit to view"
        aria-keyshortcuts="F"
        title="Fit to view (F)"
        onClick={onFit}
      >
        <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M1 5V1h4M9 1h4v4M13 9v4H9M5 13H1V9" />
        </svg>
      </button>
    </div>
  );
}
