// Build order step 18b (rehearsal defect D1, 3 November 2026): the access token lasts five minutes
// and the Glass never renewed it ahead of expiry, so the first call after it ended a full-page
// redirect that lost the presenter's screen (11 reloads in an hour). The owner's ruling: renew
// silently in the background before expiry, keep short tokens. ADR-050 Amendment 1.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createTokenRenewal } from "./tokenRenewal";

const NOW = 1_800_000_000_000;

function person(token: string, expiresInSeconds: number) {
  return { access_token: token, expires_at: Math.floor(NOW / 1000) + expiresInSeconds, profile: { sub: "analyst-1" } };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe("createTokenRenewal", () => {
  it("renews a token a minute before it expires, with no other call", async () => {
    const renew = vi.fn(async () => person("renewed", 300) as never);
    const onRenewed = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed, onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);

    await vi.advanceTimersByTimeAsync(239_000);
    expect(renew).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(renew).toHaveBeenCalledTimes(1);
    expect(onRenewed).toHaveBeenCalledWith(expect.objectContaining({ access_token: "renewed" }));
    renewal.dispose();
  });

  it("keeps renewing: each renewed token schedules the next", async () => {
    let n = 0;
    const renew = vi.fn(async () => person(`renewed-${++n}`, 300 + 240 * n) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    await vi.advanceTimersByTimeAsync(240_000);
    await vi.advanceTimersByTimeAsync(240_000);
    expect(renew).toHaveBeenCalledTimes(2);
    renewal.dispose();
  });

  it("a short token is renewed half-way through its life rather than at once", async () => {
    const renew = vi.fn(async () => null);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 60).expires_at);
    await vi.advanceTimersByTimeAsync(29_000);
    expect(renew).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(renew).toHaveBeenCalledTimes(1);
    renewal.dispose();
  });

  it("two triggers at once make one renewal, and both are given its outcome", async () => {
    let finish!: (value: unknown) => void;
    const renew = vi.fn(() => new Promise((resolve) => (finish = resolve)) as never);
    const onRenewed = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed, onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);

    await vi.advanceTimersByTimeAsync(240_000); // the timer's renewal starts and waits
    const a = renewal.renewNow(); // a refused call
    const b = renewal.renewNow(); // and another
    finish(person("renewed", 300));
    expect(await a).toEqual({ kind: "renewed", token: "renewed" });
    expect(await b).toEqual({ kind: "renewed", token: "renewed" });
    expect(renew).toHaveBeenCalledTimes(1);
    expect(onRenewed).toHaveBeenCalledTimes(1);
    renewal.dispose();
  });

  it("an identity-provider session that has ended is said as ended, and nothing is scheduled", async () => {
    const renew = vi.fn(async () => null);
    const onEnded = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded });
    expect(await renewal.renewNow()).toEqual({ kind: "ended" });
    expect(onEnded).toHaveBeenCalledWith("ended");
    await vi.advanceTimersByTimeAsync(600_000);
    expect(renew).toHaveBeenCalledTimes(1);
  });

  it("an identity provider that cannot be reached is not said as an ended session (ADR-044)", async () => {
    const renew = vi.fn(async () => {
      throw new Error("IFrame timed out without a response");
    });
    const onEnded = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded });
    expect(await renewal.renewNow()).toEqual({ kind: "unreachable" });
    expect(onEnded).toHaveBeenCalledWith("unreachable");
  });

  it("after one renewal has finished, a later trigger makes a new one", async () => {
    const renew = vi.fn(async () => person("renewed", 300) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    await renewal.renewNow();
    await renewal.renewNow();
    expect(renew).toHaveBeenCalledTimes(2);
    renewal.dispose();
  });

  it("dispose stops the timer", async () => {
    const renew = vi.fn(async () => null);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    renewal.dispose();
    await vi.advanceTimersByTimeAsync(600_000);
    expect(renew).not.toHaveBeenCalled();
  });
});
