import { describe, expect, it } from "vitest";

import { singleFlight } from "./singleFlight";

// Select what is lit reads the server, then replaces the selection. A second press while the first
// is still being read must not start a second read: the two would race, and the later would record
// the first's result as the selection to go back to.
describe("singleFlight", () => {
  it("ignores a second call while the first is still running, and says it did", async () => {
    const run = singleFlight();
    let finish!: () => void;
    let started = 0;
    const first = run(
      () =>
        new Promise<void>((resolve) => {
          started += 1;
          finish = resolve;
        }),
    );
    const second = run(async () => {
      started += 1;
    });
    expect(await second).toBe(false);
    expect(started).toBe(1);
    finish();
    expect(await first).toBe(true);
  });

  it("runs again once the first has finished, including after it failed", async () => {
    const run = singleFlight();
    await expect(
      run(async () => {
        throw new Error("read failed");
      }),
    ).rejects.toThrow("read failed");
    let ran = false;
    expect(
      await run(async () => {
        ran = true;
      }),
    ).toBe(true);
    expect(ran).toBe(true);
  });
});
