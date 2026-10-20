// The box the working set's nodes sit in, for fitting the camera to it. Sigma 3 shipped this as
// `graphExtent` in `sigma/utils`; Sigma 4 does not.

export interface Extent {
  x: [number, number];
  y: [number, number];
}

/** The smallest and largest `x` and `y` of the graph's nodes; a node with no position counts at 0. */
export function graphExtent(graph: {
  forEachNode(callback: (node: string, attributes: { x?: number; y?: number }) => void): void;
}): Extent {
  let xMin = Infinity;
  let xMax = -Infinity;
  let yMin = Infinity;
  let yMax = -Infinity;
  graph.forEachNode((_node, attributes) => {
    const x = attributes.x ?? 0;
    const y = attributes.y ?? 0;
    if (x < xMin) xMin = x;
    if (x > xMax) xMax = x;
    if (y < yMin) yMin = y;
    if (y > yMax) yMax = y;
  });
  return { x: [xMin, xMax], y: [yMin, yMax] };
}
