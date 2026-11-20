/** A clock a test moves by hand. Milliseconds since the epoch, as `Date.now()`. */
export interface TestClock {
  (): number;
  advance(seconds: number): void;
}

export function testClock(start: number = Date.UTC(2026, 10, 19, 9, 0, 0)): TestClock {
  let now = start;
  const clock = (() => now) as TestClock;
  clock.advance = (seconds: number) => {
    now += seconds * 1000;
  };
  return clock;
}
