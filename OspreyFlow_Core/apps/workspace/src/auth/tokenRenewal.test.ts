// Build order step 18b (rehearsal defect D1, 3 November 2026): the access token lasts five minutes
// and the Glass never renewed it ahead of expiry, so the first call after it ended a full-page
// redirect that lost the presenter's screen (11 reloads in an hour). The owner's ruling: renew
// silently in the background before expiry, keep short tokens. ADR-050 Amendment 1.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ACTIVITY_EVENTS, createTokenRenewal, watchActivity } from "./tokenRenewal";

const NOW = 1_800_000_000_000;

function person(token: string, expiresInSeconds: number) {
  return { access_token: token, expires_at: Math.floor(NOW / 1000) + expiresInSeconds, profile: { sub: "analyst-1" } };
}

/** A token as the identity provider answers it now, whatever the fake clock says. */
function fresh(token: string, expiresInSeconds: number) {
  return { access_token: token, expires_at: Math.floor(Date.now() / 1000) + expiresInSeconds, profile: { sub: "analyst-1" } };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => vi.useRealTimers());

describe("createTokenRenewal", () => {
  it("renews a token a minute before it expires, with no other call, when the person has done something", async () => {
    const renew = vi.fn(async () => person("renewed", 300) as never);
    const onRenewed = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed, onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    await vi.advanceTimersByTimeAsync(10_000);
    renewal.noteActivity();

    await vi.advanceTimersByTimeAsync(229_000);
    expect(renew).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(renew).toHaveBeenCalledTimes(1);
    expect(onRenewed).toHaveBeenCalledWith(expect.objectContaining({ access_token: "renewed" }));
    renewal.dispose();
  });

  it("keeps renewing while the person keeps working: each renewed token schedules the next", async () => {
    let n = 0;
    const renew = vi.fn(async () => person(`renewed-${++n}`, 300 + 240 * n) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    renewal.noteActivity();
    await vi.advanceTimersByTimeAsync(240_000);
    renewal.noteActivity();
    await vi.advanceTimersByTimeAsync(240_000);
    expect(renew).toHaveBeenCalledTimes(2);
    renewal.dispose();
  });

  it("a short token is renewed half-way through its life rather than at once", async () => {
    const renew = vi.fn(async () => null);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 60).expires_at);
    renewal.noteActivity();
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
    renewal.noteActivity();

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

// ADR-050 Amendment 2 (build order step 28 (b)): each renewal is a sign-in round at the identity
// provider, which counts as activity there, so renewing an unattended window kept its session alive
// to the 10-hour maximum. A renewal now waits for the person to have done something since the last
// renewal or sign-in; otherwise the token lapses and the session prompt takes over at the idle limit.
describe("renewal only after the person has done something", () => {
  it("an idle window does not renew: the token lapses and nothing is asked", async () => {
    const renew = vi.fn(async () => fresh("renewed", 300) as never);
    const onEnded = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded });
    renewal.schedule(person("first", 300).expires_at);
    await vi.advanceTimersByTimeAsync(3_600_000);
    expect(renew).not.toHaveBeenCalled();
    expect(onEnded).not.toHaveBeenCalled();
    renewal.dispose();
  });

  it("activity after the token has lapsed renews at once", async () => {
    const renew = vi.fn(async () => fresh("renewed", 300) as never);
    const onRenewed = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed, onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    await vi.advanceTimersByTimeAsync(1_800_000);
    expect(renew).not.toHaveBeenCalled();
    renewal.noteActivity();
    await vi.advanceTimersByTimeAsync(0);
    expect(renew).toHaveBeenCalledTimes(1);
    expect(onRenewed).toHaveBeenCalledWith(expect.objectContaining({ access_token: "renewed" }));
    renewal.noteActivity(); // more activity joins nothing: the renewal is done, the next is timed
    await vi.advanceTimersByTimeAsync(0);
    expect(renew).toHaveBeenCalledTimes(1);
    renewal.dispose();
  });

  it("activity is counted from the last renewal: one renewal does not lead to another by itself", async () => {
    const renew = vi.fn(async () => fresh("renewed", 300) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    renewal.noteActivity();
    await vi.advanceTimersByTimeAsync(240_000);
    expect(renew).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3_600_000);
    expect(renew).toHaveBeenCalledTimes(1);
    renewal.dispose();
  });

  it("activity before a sign-in does not count after it", async () => {
    const renew = vi.fn(async () => fresh("renewed", 300) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.noteActivity();
    renewal.schedule(person("signed-in", 300).expires_at); // a sign-in schedules afresh
    await vi.advanceTimersByTimeAsync(600_000);
    expect(renew).not.toHaveBeenCalled();
    renewal.dispose();
  });

  it("a call refused while nobody has done anything is not renewed; after activity it is", async () => {
    const renew = vi.fn(async () => fresh("renewed", 300) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    renewal.schedule(person("first", 300).expires_at);
    expect(await renewal.renewIfActive()).toEqual({ kind: "idle" });
    expect(renew).not.toHaveBeenCalled();
    renewal.noteActivity(); // the person is back: the lapsed token is renewed at once
    expect(await renewal.renewIfActive()).toEqual({ kind: "renewed", token: "renewed" });
    expect(renew).toHaveBeenCalledTimes(1);
    renewal.dispose();
  });

  it("asking outright (Try again) renews whatever the activity", async () => {
    const renew = vi.fn(async () => fresh("renewed", 300) as never);
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded: vi.fn() });
    expect(await renewal.renewNow()).toEqual({ kind: "renewed", token: "renewed" });
    renewal.dispose();
  });

  it("an ended session is asked once: activity after it starts no renewal of its own", async () => {
    const renew = vi.fn(async () => null);
    const onEnded = vi.fn();
    const renewal = createTokenRenewal({ renew, onRenewed: vi.fn(), onEnded });
    renewal.schedule(person("first", 300).expires_at);
    await vi.advanceTimersByTimeAsync(300_000);
    renewal.noteActivity();
    await vi.advanceTimersByTimeAsync(0);
    expect(onEnded).toHaveBeenCalledTimes(1);
    renewal.noteActivity();
    await vi.advanceTimersByTimeAsync(600_000);
    expect(renew).toHaveBeenCalledTimes(1);
    expect(onEnded).toHaveBeenCalledTimes(1);
  });
});

describe("watchActivity", () => {
  it("counts a key press, a pointer press and a wheel turn, and not a pointer merely moving", () => {
    const seen = vi.fn();
    const window = new EventTarget(); // what the page's window is to the watch: something events reach
    const stop = watchActivity(window, seen);
    window.dispatchEvent(new Event("keydown"));
    window.dispatchEvent(new Event("pointerdown"));
    window.dispatchEvent(new Event("wheel"));
    window.dispatchEvent(new Event("pointermove"));
    window.dispatchEvent(new Event("mousemove"));
    expect(seen).toHaveBeenCalledTimes(3);
    expect([...ACTIVITY_EVENTS]).toEqual(["keydown", "pointerdown", "wheel"]);
    stop();
    window.dispatchEvent(new Event("keydown"));
    expect(seen).toHaveBeenCalledTimes(3);
  });

  it("listens passively, in the capture phase, so no handler that stops an event hides it", () => {
    const window = new EventTarget();
    const add = vi.spyOn(window, "addEventListener");
    const stop = watchActivity(window, vi.fn());
    for (const call of add.mock.calls) {
      expect(call[2]).toEqual({ capture: true, passive: true });
    }
    expect(add).toHaveBeenCalledTimes(ACTIVITY_EVENTS.length);
    stop();
    add.mockRestore();
  });
});
