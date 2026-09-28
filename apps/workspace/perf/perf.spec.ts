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
  const start = Date.now();
  await page.goto("/perf/harness.html");
  await page.waitForFunction(() => window.__PERF__?.readyAt != null, undefined, {
    timeout: 60_000,
  });
  const elapsedMs = Date.now() - start;

  // §5: "< 2.5s to first interactive frame" on real hardware. CI's
  // software-rendered proxy budget is deliberately much looser — this
  // catches a real regression (a change that makes first render 10x
  // slower), not a hardware-class difference.
  expect(elapsedMs).toBeLessThan(30_000);
});

test("a sustained pan/zoom sweep holds a CI-appropriate minimum frame rate", async ({ page }) => {
  await page.goto("/perf/harness.html");
  await page.waitForFunction(() => window.__PERF__?.readyAt != null, undefined, {
    timeout: 60_000,
  });

  const canvas = page.locator("canvas.sigma-nodes");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("canvas not found");
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  const frameTimesMs = await page.evaluate(async ({ cx, cy }) => {
    const samples: number[] = [];
    let last = performance.now();
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
    return samples;
  }, { cx, cy });

  const meaningfulSamples = frameTimesMs.filter((t) => t > 0);
  const averageFrameMs =
    meaningfulSamples.reduce((sum, t) => sum + t, 0) / Math.max(1, meaningfulSamples.length);

  // 60fps real-hardware target = 16.67ms/frame. CI's software-rendered
  // proxy is calibrated against an observed baseline on this fixture
  // (~730ms/frame under SwiftShader for a 50k/250k sweep), not that
  // number — see module docstring. Generous headroom above the baseline:
  // this is a regression gate (catch a change that makes it far worse),
  // not a tight budget that would make this test flaky on ordinary CI
  // variance.
  expect(averageFrameMs).toBeLessThan(3000);
});

test("the fixture itself is the documented 50k/250k shape", () => {
  expect(FIXTURE_NODE_COUNT).toBe(50_000);
  expect(FIXTURE_EDGE_COUNT).toBe(250_000);
});
