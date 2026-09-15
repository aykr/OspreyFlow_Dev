// Node shape + fill + provenance-stroke, baked into one generated SVG data
// URI per distinct (shape, fill, stroke) combination — `docs/
// 02_GLASS_FRONTEND.md` §4 ("Hue is entity type; shape is entity type
// too") and `docs/design/tokens.css`'s provenance-stroke contract
// (asserted solid, inferred dashed 4 2, unresolved dotted).
//
// **Why a generated SVG image rather than a custom WebGL shader.**
// `docs/06_DECISIONS.md` ADR-002 anticipated "one parameterised program,
// not nine" for the small, closed shape vocabulary — the intent holds,
// only the mechanism differs from a literal fragment shader. `sigma`'s own
// shipped programs are circle-only (`NodeCircleProgram`); the
// architecture's own named plugin, `@sigma/node-image`
// (`docs/02_GLASS_FRONTEND.md` §1's plugin list), renders an arbitrary
// image per node and is the officially supported extension point for
// exactly this. A custom multi-shape *and* dashed-stroke WebGL program
// would need real arc-length parametrisation per shape to dash correctly
// and untested GLSL with no reference implementation available offline —
// genuinely higher-risk than generating a small, cacheable set of SVGs
// (native `stroke-dasharray`, exact) and letting `@sigma/node-image`'s own
// texture atlas do the WebGL part. Interaction-state rings (hover/
// selected/on-path — always solid, `docs/design/tokens.css`) are a
// *separate*, live `@sigma/node-border` layer instead of baked into this
// image, since those change every frame and a cached image must not.
//
// The set of distinct SVGs this ever needs to generate is small and
// bounded — shapes × channels × three provenance strokes × a handful of
// dim states, not one per node — so `imageCache` below is keyed by content
// (shape+fill+stroke), not by node id, and stays tiny regardless of
// working-set size.

export type NodeShape =
  | "circle"
  | "square"
  | "diamond"
  | "hexagon"
  | "triangle"
  | "page"
  | "pin";

export type StrokeStyle = "solid" | "dashed" | "dotted";

export interface NodeVisualSpec {
  shape: NodeShape;
  fillHex: string;
  strokeHex: string;
  strokeStyle: StrokeStyle;
}

const VIEWBOX = 32;
const CENTER = VIEWBOX / 2;

/** Same on-canvas stroke width regardless of style, per `docs/design/
 * tokens.css`'s provenance rows: asserted "1px", inferred/unresolved
 * "1.5px" — both close enough to read as one visual weight class next to
 * the 2px selection/on-path rings `@sigma/node-border` draws separately. */
const STROKE_WIDTH = 1.5;

function shapePathOrPoints(shape: NodeShape): { tag: "path" | "polygon" | "circle"; d: string } {
  const r = CENTER - STROKE_WIDTH; // leave room for the stroke inside the viewBox
  switch (shape) {
    case "circle":
      return { tag: "circle", d: `${CENTER},${CENTER},${r}` };
    case "square": {
      const half = r * 0.82; // visually match the circle's area, not its bounding box
      return {
        tag: "polygon",
        d: [
          `${CENTER - half},${CENTER - half}`,
          `${CENTER + half},${CENTER - half}`,
          `${CENTER + half},${CENTER + half}`,
          `${CENTER - half},${CENTER + half}`,
        ].join(" "),
      };
    }
    case "diamond": {
      const d = r;
      return {
        tag: "polygon",
        d: [
          `${CENTER},${CENTER - d}`,
          `${CENTER + d},${CENTER}`,
          `${CENTER},${CENTER + d}`,
          `${CENTER - d},${CENTER}`,
        ].join(" "),
      };
    }
    case "triangle": {
      const points: string[] = [];
      for (let i = 0; i < 3; i++) {
        const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 3;
        points.push(`${CENTER + r * Math.cos(angle)},${CENTER + r * Math.sin(angle)}`);
      }
      return { tag: "polygon", d: points.join(" ") };
    }
    case "hexagon": {
      const points: string[] = [];
      for (let i = 0; i < 6; i++) {
        const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 6;
        points.push(`${CENTER + r * Math.cos(angle)},${CENTER + r * Math.sin(angle)}`);
      }
      return { tag: "polygon", d: points.join(" ") };
    }
    case "page": {
      // A sheet with a folded top-right corner — the conventional
      // "document" glyph.
      const left = CENTER - r * 0.72;
      const right = CENTER + r * 0.72;
      const top = CENTER - r;
      const bottom = CENTER + r;
      const fold = r * 0.4;
      return {
        tag: "polygon",
        d: [
          `${left},${top}`,
          `${right - fold},${top}`,
          `${right},${top + fold}`,
          `${right},${bottom}`,
          `${left},${bottom}`,
        ].join(" "),
      };
    }
    case "pin": {
      // A map-pin teardrop: a circle sitting on a downward point.
      const pinR = r * 0.62;
      const pinCenterY = CENTER - r * 0.28;
      const tipY = CENTER + r;
      const shoulderHalfWidth = pinR * 0.86;
      return {
        tag: "path",
        d: [
          `M ${CENTER - shoulderHalfWidth} ${pinCenterY + pinR * 0.5}`,
          `A ${pinR} ${pinR} 0 1 1 ${CENTER + shoulderHalfWidth} ${pinCenterY + pinR * 0.5}`,
          `L ${CENTER} ${tipY}`,
          "Z",
        ].join(" "),
      };
    }
  }
}

function strokeDasharray(style: StrokeStyle): string | null {
  switch (style) {
    case "solid":
      return null;
    case "dashed":
      return "4 2";
    case "dotted":
      return "1.5 2";
  }
}

export function renderNodeSvg(spec: NodeVisualSpec): string {
  const shape = shapePathOrPoints(spec.shape);
  const dash = strokeDasharray(spec.strokeStyle);
  const dashAttr = dash ? ` stroke-dasharray="${dash}"` : "";
  const element =
    shape.tag === "circle"
      ? (() => {
          const [cx, cy, r] = shape.d.split(",");
          return `<circle cx="${cx}" cy="${cy}" r="${r}"`;
        })()
      : shape.tag === "polygon"
        ? `<polygon points="${shape.d}"`
        : `<path d="${shape.d}"`;

  return (
    // `width`/`height` alongside `viewBox` — not redundant: a data-URI SVG
    // loaded via a plain `<img>` (no CSS/DOM sizing context) falls back to
    // an intrinsic-size guess (observed 150×150 in Chromium) when only
    // `viewBox` is present, and rasterises the 32×32 content into a
    // corner of that guessed box rather than scaling it to fill —
    // invisible once `@sigma/node-image` crops its atlas cell tightly
    // around the *reported* natural size. Explicit `width`/`height`
    // matching the viewBox removes the guess entirely. Found by tracing
    // the actual atlas pixel/UV pipeline, not anticipated in advance.
    `<svg xmlns="http://www.w3.org/2000/svg" width="${VIEWBOX}" height="${VIEWBOX}" viewBox="0 0 ${VIEWBOX} ${VIEWBOX}">` +
    `${element} fill="${spec.fillHex}" stroke="${spec.strokeHex}" ` +
    `stroke-width="${STROKE_WIDTH}"${dashAttr} stroke-linejoin="round"/></svg>`
  );
}

export function nodeSvgDataUri(spec: NodeVisualSpec): string {
  return `data:image/svg+xml;utf8,${encodeURIComponent(renderNodeSvg(spec))}`;
}

const imageCache = new Map<string, string>();

/** Content-keyed, not node-keyed — see the module docstring. */
export function cachedNodeSvgDataUri(spec: NodeVisualSpec): string {
  const key = `${spec.shape}|${spec.fillHex}|${spec.strokeHex}|${spec.strokeStyle}`;
  const cached = imageCache.get(key);
  if (cached) return cached;
  const uri = nodeSvgDataUri(spec);
  imageCache.set(key, uri);
  return uri;
}
