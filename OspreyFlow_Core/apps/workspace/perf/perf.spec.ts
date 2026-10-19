// The performance budget — `spec/02_GLASS_FRONTEND.md` §5 — as a CI gate,
// against the 50k-node/250k-edge fixture (`fixture.ts`), per this
// checkpoint's own decision: GitHub Actions' hosted runners have no GPU, so
// Chromium here falls back to software WebGL (SwiftShader) — dramatically
// slower than the §5 table's real-hardware numbers. The thresholds below
// are a *regression* gate calibrated for that software path, not a
// restatement of §5's literal budget; the literal budget itself is
// verified once against real target hardware and recorded as this
// phase's exit evidence, not re-asserted here on every PR.
import { expect, test } from "@playwright/test";

import { FIXTURE_EDGE_COUNT, FIXTURE_NODE_COUNT } from "./fixture";

test("50k/250k fixture reaches a first interactive frame within the CI software-render budget", async ({
  page,
}) => {
  // Diagnostics, printed on every run and changing nothing measured: Chrome's long animation
  // frames (each frame over 50 ms, with what ran in it) and a CPU profile of the whole wait, to find
  // what keeps CI's page busy for ~40 s after it reports ready (15 October 2026).
  await page.addInitScript(() => {
    const frames: unknown[] = [];
    (window as unknown as { __LOAF__: unknown[] }).__LOAF__ = frames;
    try {
      new PerformanceObserver((list) => frames.push(...list.getEntries().map((e) => e.toJSON()))).observe({
        type: "long-animation-frame",
        buffered: true,
      });
    } catch {
      // A browser without the entry type: the summary says none were seen.
    }
  });
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Profiler.enable");
  await cdp.send("Profiler.setSamplingInterval", { interval: 1000 });
  await cdp.send("Profiler.start");

  const start = Date.now();
  await page.goto("/perf/harness.html");
  await page.waitForFunction(() => window.__PERF__?.readyAt != null, undefined, {
    timeout: 60_000,
  });
  const elapsedMs = Date.now() - start;
  const { profile } = await cdp.send("Profiler.stop");
  console.log(summariseProfile(profile));
  console.log(
    summariseFrames(
      await page.evaluate(() => (window as unknown as { __LOAF__: LongFrame[] }).__LOAF__),
      await page.evaluate(() => window.__PERF__!.readyAt!),
    ),
  );
  // Where the time went, printed on every run (15 October 2026: CI took ~50 s where it had taken
  // ~25 s, with the canvas's code unchanged): the page arriving, then the app's own `readyAt`.
  const timing = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    const scripts = performance.getEntriesByType("resource").filter((r) => r.name.includes(".ts"));
    return {
      responseEnd: Math.round(nav.responseEnd),
      domContentLoaded: Math.round(nav.domContentLoadedEventEnd),
      readyAt: Math.round(window.__PERF__!.readyAt!),
      modules: scripts.length,
      slowestModule: Math.round(Math.max(0, ...scripts.map((r) => r.duration))),
    };
  });
  console.log(`perf first frame: ${elapsedMs} ms in all; ${JSON.stringify(timing)}`);

  // §5: "< 2.5s to first interactive frame" on real hardware. CI's
  // software-rendered proxy budget is deliberately much looser — this
  // catches a real regression (a change that makes first render 10x
  // slower), not a hardware-class difference.
  expect(elapsedMs).toBeLessThan(30_000);
});

test("a sustained pan/zoom sweep holds a CI-appropriate minimum frame rate", async ({ page }) => {
  // `PERF_CPU_THROTTLE=2` runs the page at about the speed of a CI runner (CI measured 1.9 times
  // slower than the owner's machine, 20 October 2026), so a regression CI would catch can be shown
  // red locally before the gate is trusted (CLAUDE.md rule 15). Unset in CI.
  const throttle = Number(process.env.PERF_CPU_THROTTLE ?? "1");
  if (throttle > 1) {
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: throttle });
  }
  await page.goto("/perf/harness.html");
  await page.waitForFunction(() => window.__PERF__?.readyAt != null, undefined, {
    timeout: 60_000,
  });
  // Panning is measured once the first frame has been drawn: `readyAt` marks the canvas existing,
  // and the first frame's drawing runs for seconds after it, so a sweep started there measured the
  // tail of loading (two or three frames in its two seconds) rather than panning, and passed or
  // failed with the first frame (20 October 2026; on main, Sigma 3 passed by loading sooner though
  // settled it pans at 2.7 s a frame in software). Settled means the page answers within 100 ms,
  // then three seconds more for what follows the first frame (ADR-119's grouping by community).
  await expect
    .poll(
      async () => {
        const asked = Date.now();
        await page.evaluate(() => 1);
        return Date.now() - asked;
      },
      { timeout: 90_000, intervals: [0] },
    )
    .toBeLessThan(100);
  await page.waitForTimeout(3000);

  const canvas = page.locator("canvas.sigma-stage");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas not found");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  const sweep = await page.evaluate(async ({ cx, cy }) => {
    const samples: number[] = [];
    const started = performance.now();
    let last = started;
    const onFrame = () => {
      const now = performance.now();
      samples.push(now - last);
      last = now;
    };
    let raf = 0;
    const loop = () => {
      onFrame();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    // Simulate a pan+zoom sweep over ~2s: dispatch synthetic wheel/mouse
    // events directly (no real OS input available inside `page.evaluate`).
    const el = document.elementFromPoint(cx, cy);
    const deadline = performance.now() + 2000;
    let angle = 0;
    while (performance.now() < deadline) {
      angle += 0.2;
      el?.dispatchEvent(
        new WheelEvent("wheel", {
          deltaY: Math.sin(angle) * 50,
          clientX: cx + Math.cos(angle) * 50,
          clientY: cy + Math.sin(angle) * 50,
          bubbles: true,
        }),
      );
      await new Promise((resolve) => setTimeout(resolve, 16));
    }
    cancelAnimationFrame(raf);
    return { frames: samples.length, elapsedMs: performance.now() - started };
  }, { cx, cy });

  // The time the sweep took, over the frames it finished. The frame still being drawn when it ends
  // counts as time but not as a frame: averaging only finished frames let a page stalled for most
  // of the sweep report a fast average from its last two (two 15 ms frames in a two-second sweep),
  // and counting the unfinished one as a frame halved a stall (a planted three-second stall on
  // every camera move passed at 1,514 ms "per frame"; 20 October 2026).
  const averageFrameMs = sweep.elapsedMs / Math.max(1, sweep.frames);

  // 60fps real-hardware target = 16.67ms/frame. CI's software-rendered
  // proxy is calibrated against an observed baseline on this fixture
  // (~730ms/frame under SwiftShader for a 50k/250k sweep), not that
  // number — see module docstring. Generous headroom above the baseline:
  // this is a regression gate (catch a change that makes it far worse),
  // not a tight budget that would make this test flaky on ordinary CI
  // variance.
  console.log(
    `perf sweep: ${averageFrameMs.toFixed(1)} ms per frame over ${sweep.frames} frames in ${sweep.elapsedMs.toFixed(0)} ms`,
  );
  expect(averageFrameMs).toBeLessThan(3000);
});

test("the fixture itself is the documented 50k/250k shape", () => {
  expect(FIXTURE_NODE_COUNT).toBe(50_000);
  expect(FIXTURE_EDGE_COUNT).toBe(250_000);
});

interface LongFrame {
  startTime: number;
  duration: number;
  blockingDuration?: number;
  renderStart?: number;
  styleAndLayoutStart?: number;
  scripts?: { duration: number; sourceFunctionName?: string; sourceURL?: string; invoker?: string }[];
}

interface ProfileNode {
  id: number;
  callFrame: { functionName: string; url: string; lineNumber: number };
}

/** Self time per function, the twelve heaviest, and the share that was no JavaScript at all. */
function summariseProfile(profile: { nodes: ProfileNode[]; samples?: number[]; timeDeltas?: number[] }): string {
  const byId = new Map(profile.nodes.map((n) => [n.id, n]));
  const self = new Map<string, number>();
  const samples = profile.samples ?? [];
  const deltas = profile.timeDeltas ?? [];
  let total = 0;
  samples.forEach((id, i) => {
    const node = byId.get(id);
    const frame = node?.callFrame;
    const file = frame?.url.split("/").pop()?.split("?")[0] ?? "";
    const key = frame ? `${frame.functionName || "(anonymous)"} ${file}:${frame.lineNumber + 1}` : "?";
    const us = deltas[i + 1] ?? 0;
    self.set(key, (self.get(key) ?? 0) + us);
    total += us;
  });
  const top = [...self.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
  return (
    `perf profile: ${Math.round(total / 1000)} ms sampled; heaviest by self time:\n` +
    top.map(([k, us]) => `  ${Math.round(us / 1000)} ms  ${k}`).join("\n")
  );
}

/** The long frames after the page said it was ready: how many, how long, and what ran in them. */
function summariseFrames(frames: LongFrame[] | undefined, readyAt: number): string {
  const all = frames ?? [];
  const after = all.filter((f) => f.startTime + f.duration > readyAt);
  const sum = (xs: number[]) => Math.round(xs.reduce((a, b) => a + b, 0));
  const scriptMs = sum(after.flatMap((f) => (f.scripts ?? []).map((s) => s.duration)));
  const renderMs = sum(after.map((f) => (f.renderStart ? f.startTime + f.duration - f.renderStart : 0)));
  const worst = [...after].sort((a, b) => b.duration - a.duration).slice(0, 5);
  return (
    `perf long frames: ${all.length} in all, ${after.length} after readyAt ${Math.round(readyAt)} ms, ` +
    `${sum(after.map((f) => f.duration))} ms long; script ${scriptMs} ms, rendering ${renderMs} ms\n` +
    worst
      .map((f) => {
        const s = [...(f.scripts ?? [])].sort((a, b) => b.duration - a.duration)[0];
        const what = s ? `${s.sourceFunctionName || s.invoker || "?"} ${(s.sourceURL ?? "").split("/").pop()}` : "no script";
        return `  at ${Math.round(f.startTime)} ms: ${Math.round(f.duration)} ms (${what})`;
      })
      .join("\n")
  );
}
