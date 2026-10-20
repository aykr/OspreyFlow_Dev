import type { FragmentLayer, LayerLifecycleContext } from "sigma/rendering";

// When `@sigma/node-image` finishes a texture (an icon loaded), it asks for `renderer.refresh()` with
// no arguments: Sigma then re-processes every node and every edge in one task. On the 50k/250k
// fixture that one task held the page for 8 s on a CI runner after it had reported ready (the perf
// gate's profile, 15 October 2026). A texture changes what nodes draw, never where they are, and no
// edge reads it — so the nodes are refreshed instead, a share per frame, without re-indexing, and
// the edges not at all. Every other refresh (with options) is Sigma's own, untouched.

/** The part of Sigma this needs; a test passes a fake. */
export interface Refreshable {
  refresh(opts?: {
    partialGraph?: { nodes?: string[]; edges?: string[] };
    skipIndexation?: boolean;
    schedule?: boolean;
  }): unknown;
  getGraph(): { nodes(): string[]; hasNode(node: string): boolean };
}

/** Nodes refreshed per frame: small enough that a frame stays short on a software renderer. */
export const NODES_PER_FRAME = 2000;

type Schedule = (step: () => void) => unknown;

/** A stand-in for `renderer` that turns a full refresh into one spread across frames. Calling it
 * again before the last one finished starts over with the graph as it is then. */
export function chunkedRefresher<R extends Refreshable>(
  renderer: R,
  nextFrame: Schedule = (step) => requestAnimationFrame(() => step()),
  perFrame: number = NODES_PER_FRAME,
): R {
  let run = 0;
  const spread = () => {
    const mine = ++run;
    const graph = renderer.getGraph();
    const nodes = graph.nodes();
    let at = 0;
    const step = () => {
      if (mine !== run) return; // a newer texture superseded this one
      const share = nodes.slice(at, at + perFrame).filter((node) => graph.hasNode(node));
      at += perFrame;
      try {
        if (share.length) {
          renderer.refresh({ partialGraph: { nodes: share }, skipIndexation: true, schedule: true });
        }
      } catch {
        // A node the renderer has not indexed yet (the graph changed under the spread): Sigma's
        // own full refresh, once, rather than a node drawn with a stale texture.
        run += 1;
        renderer.refresh({ schedule: true });
        return;
      }
      if (at < nodes.length) nextFrame(step);
    };
    nextFrame(step);
  };
  return new Proxy(renderer, {
    get(target, key, receiver) {
      if (key === "refresh") {
        return (opts?: Parameters<R["refresh"]>[0]) => (opts ? target.refresh(opts) : spread());
      }
      const value = Reflect.get(target, key, receiver);
      return typeof value === "function" ? value.bind(target) : value;
    },
  });
}

/** `@sigma/node-image`'s layer, with the refresh it asks for when a texture is ready spread as
 * above. Sigma 4 hands a layer its own refresh in the layer's lifecycle; `renderer` is read when a
 * texture is ready, not before, since the layer is built before its renderer exists. */
export function withChunkedTextureRefresh(layer: FragmentLayer, renderer: () => Refreshable | null): FragmentLayer {
  const lifecycle = layer.lifecycle;
  if (!lifecycle) return layer;
  let spreadFor: Refreshable | null = null;
  let spreading: Refreshable | null = null;
  const refresh = (fallback: () => void) => () => {
    const live = renderer();
    if (!live) return fallback();
    if (spreadFor !== live) {
      spreadFor = live;
      spreading = chunkedRefresher(live);
    }
    spreading!.refresh();
  };
  return {
    ...layer,
    lifecycle: (context: LayerLifecycleContext) =>
      lifecycle({
        ...context,
        renderer: { refresh: refresh(() => context.renderer.refresh()) },
        requestRefresh: refresh(() => context.requestRefresh()),
      }),
  };
}
