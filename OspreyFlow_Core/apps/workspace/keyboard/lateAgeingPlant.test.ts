// @vitest-environment node
// What CO3e's proof plant (`./lateAgeingPlant.ts`) does to a keypress. CO3f keeps the plant as its proof, and
// one of its remedies stops the page's second `operations/ageing` read: the plant must then let ArrowUp
// return, not wait for ever for a read that never comes.
//
// The page here is a stand-in with the four calls the plant makes. A response is seen only by a wait that was
// listening when it was delivered, as with Playwright's `waitForResponse`. What the plant does to the real
// page is `admin.spec.ts`'s overdue-days case under `OSPREY_PLANT_LATE_AGEING=1`.
//
// Which test fails if the invariant is broken (rules 12 and 15):
//  - a page that reads once hangs every ArrowUp: "lets ArrowUp return when the page reads ageing once";
//  - the second read lands before the keypress, so the plant shows nothing: "holds a second read ...".
import type { Page, Route } from "@playwright/test";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { plantLateAgeing } from "./lateAgeingPlant";

const URL_READ = "http://keyboard-test.invalid/v1/admin/operations/ageing";

interface Answer {
  url: () => string;
  finished: () => Promise<null>;
}

async function planted() {
  let handler!: (route: Route) => Promise<void>;
  let waits: { wanted: (r: Answer) => boolean; done: (r: Answer) => void }[] =
    [];
  const log: string[] = [];
  const page = {
    route: async (_url: string, given: typeof handler) =>
      void (handler = given),
    keyboard: { press: async (key: string) => void log.push(`press ${key}`) },
    waitForResponse: (wanted: (r: Answer) => boolean) =>
      new Promise<Answer>((done) => waits.push({ wanted, done })),
    evaluate: async () => undefined,
  } as unknown as Page;
  await plantLateAgeing(page);
  let reads = 0;
  /** The page asks for ageing; the answer is delivered when the plant lets the request go on. */
  const read = () => {
    const number = ++reads;
    void handler({
      fallback: async () => {
        log.push(`answer ${number}`);
        const answer = { url: () => URL_READ, finished: async () => null };
        const seeing = waits.filter((wait) => wait.wanted(answer));
        waits = waits.filter((wait) => !seeing.includes(wait));
        seeing.forEach((wait) => wait.done(answer));
      },
    } as unknown as Route);
  };
  /** Presses `key`; `returned` says whether the press has come back yet. */
  const press = (key: string) => {
    const state = { returned: false };
    void page.keyboard.press(key).then(() => (state.returned = true));
    return state;
  };
  return { read, press, log };
}

describe("the late-ageing plant", () => {
  beforeEach(() => void vi.useFakeTimers());
  afterEach(() => void vi.useRealTimers());

  it("lets ArrowUp return when the page reads ageing once", async () => {
    const { read, press, log } = await planted();
    read();
    const arrow = press("ArrowUp");
    await vi.advanceTimersByTimeAsync(10_000); // well inside a case's 60 s
    expect(arrow.returned).toBe(true);
    expect(log).toEqual(["answer 1", "press ArrowUp"]);
  });

  it("holds a second read asked after ArrowUp, and lands it before the press returns", async () => {
    const { read, press, log } = await planted();
    read();
    const arrow = press("ArrowUp");
    await vi.advanceTimersByTimeAsync(500);
    expect(arrow.returned).toBe(false);
    read();
    await vi.advanceTimersByTimeAsync(10);
    expect(arrow.returned).toBe(true);
    expect(log).toEqual(["answer 1", "press ArrowUp", "answer 2"]);
  });

  it("holds a second read asked before ArrowUp until the key is pressed", async () => {
    const { read, press, log } = await planted();
    read();
    read();
    await vi.advanceTimersByTimeAsync(500);
    expect(log).toEqual(["answer 1"]);
    const arrow = press("ArrowUp");
    await vi.advanceTimersByTimeAsync(10);
    expect(arrow.returned).toBe(true);
    expect(log).toEqual(["answer 1", "press ArrowUp", "answer 2"]);
  });

  it("lets a held second read go by itself, for a case that waits for it before pressing", async () => {
    const { read, press, log } = await planted();
    read();
    read();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(log).toEqual(["answer 1", "answer 2"]);
    const arrow = press("ArrowUp");
    await vi.advanceTimersByTimeAsync(10);
    expect(arrow.returned).toBe(true);
  });
});
