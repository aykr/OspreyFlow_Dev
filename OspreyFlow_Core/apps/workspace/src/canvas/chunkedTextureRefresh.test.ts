// The perf gate's profile (15 October 2026): a texture's full refresh held the page 8 s on CI.
import type { FragmentLayer, LayerLifecycleContext } from "sigma/rendering";
import { describe, expect, it, vi } from "vitest";

import { chunkedRefresher, withChunkedTextureRefresh, type Refreshable } from "./chunkedTextureRefresh";

function fakeRenderer(count: number) {
  const nodes = Array.from({ length: count }, (_, i) => `n${i}`);
  const present = new Set(nodes);
  const calls: Parameters<Refreshable["refresh"]>[0][] = [];
  const renderer = {
    refresh: (opts?: Parameters<Refreshable["refresh"]>[0]) => {
      calls.push(opts);
    },
    getGraph: () => ({ nodes: () => [...nodes], hasNode: (n: string) => present.has(n) }),
    zoomRatio: 3,
  };
  const frames: (() => void)[] = [];
  const runFrames = () => {
    while (frames.length) frames.shift()!();
  };
  return { renderer, calls, frames, runFrames, present };
}

describe("chunkedRefresher", () => {
  it("turns a full refresh into node-only refreshes, a share per frame, and none at once", () => {
    const { renderer, calls, frames, runFrames } = fakeRenderer(5000);
    const proxied = chunkedRefresher(renderer, (s) => frames.push(s), 2000);
    proxied.refresh();
    expect(calls).toEqual([]); // nothing in the task that asked
    runFrames();
    expect(calls.map((c) => c?.partialGraph?.nodes?.length)).toEqual([2000, 2000, 1000]);
    expect(calls.every((c) => c?.skipIndexation === true && !c?.partialGraph?.edges)).toBe(true);
    expect(new Set(calls.flatMap((c) => c?.partialGraph?.nodes ?? [])).size).toBe(5000);
  });

  it("passes a refresh with options straight to Sigma", () => {
    const { renderer, calls } = fakeRenderer(10);
    chunkedRefresher(renderer, () => undefined).refresh({ schedule: true });
    expect(calls).toEqual([{ schedule: true }]);
  });

  it("a newer texture supersedes the spread still running", () => {
    const { renderer, calls, frames, runFrames } = fakeRenderer(5000);
    const proxied = chunkedRefresher(renderer, (s) => frames.push(s), 2000);
    proxied.refresh();
    frames.shift()!(); // one share of the first spread
    proxied.refresh();
    runFrames();
    expect(calls.map((c) => c?.partialGraph?.nodes?.length)).toEqual([2000, 2000, 2000, 1000]);
  });

  it("skips a node removed meanwhile, and falls back to one full refresh if Sigma refuses", () => {
    const { renderer, calls, frames, runFrames, present } = fakeRenderer(3);
    present.delete("n1");
    const proxied = chunkedRefresher(renderer, (s) => frames.push(s), 10);
    proxied.refresh();
    runFrames();
    expect(calls[0]?.partialGraph?.nodes).toEqual(["n0", "n2"]);

    const refusing = { ...renderer, refresh: (o?: Parameters<Refreshable["refresh"]>[0]) => {
      calls.push(o);
      if (o?.partialGraph) throw new Error("Sigma: node can't be repaint");
    } };
    calls.length = 0;
    chunkedRefresher(refusing, (s) => frames.push(s), 10).refresh();
    runFrames();
    expect(calls.at(-1)).toEqual({ schedule: true });
  });

  it("leaves everything else on the renderer as it was", () => {
    const { renderer } = fakeRenderer(1);
    expect(chunkedRefresher(renderer, () => undefined).zoomRatio).toBe(3);
  });
});

describe("withChunkedTextureRefresh", () => {
  /** A layer that asks for a refresh the way `@sigma/node-image`'s does when a texture is ready:
   * through the lifecycle context Sigma hands it. */
  function askingLayer() {
    const asked: { ask?: () => void } = {};
    const layer = {
      name: "image",
      uniforms: [],
      attributes: [],
      glsl: "",
      lifecycle: (context: LayerLifecycleContext) => {
        asked.ask = () => context.requestRefresh();
        return {};
      },
    } as FragmentLayer;
    return { layer, asked };
  }
  // One animation frame is the next turn of the loop here, so the test does not wait on a display.
  vi.stubGlobal("requestAnimationFrame", (step: () => void) => setTimeout(step, 0));
  const nextFrame = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  it("spreads the refresh a finished texture asks for, instead of one full refresh", async () => {
    const { renderer, calls } = fakeRenderer(3);
    const { layer, asked } = askingLayer();
    let sigmaFull = 0;
    withChunkedTextureRefresh(layer, () => renderer).lifecycle!({
      requestRefresh: () => sigmaFull++,
      renderer: { refresh: () => sigmaFull++ },
    } as unknown as LayerLifecycleContext);
    asked.ask!();
    expect(sigmaFull).toBe(0);
    expect(calls).toEqual([]);
    await nextFrame();
    expect(calls).toEqual([{ partialGraph: { nodes: ["n0", "n1", "n2"] }, skipIndexation: true, schedule: true }]);
  });

  it("falls back to Sigma's own refresh while there is no renderer yet", () => {
    const { layer, asked } = askingLayer();
    let sigmaFull = 0;
    withChunkedTextureRefresh(layer, () => null).lifecycle!({
      requestRefresh: () => sigmaFull++,
      renderer: { refresh: () => sigmaFull++ },
    } as unknown as LayerLifecycleContext);
    asked.ask!();
    expect(sigmaFull).toBe(1);
  });
});
