// @vitest-environment jsdom
//
// The launcher opens the Glass with `?from=launcher` (and `&view=ingest` for the Ingest Studio
// tile). Seen on the owner's deployment: a person who had just signed in at the launcher was asked
// to sign in again, and the Glass and the Studio tiles opened the identical page. These tests fix
// what the Glass does with that hand-off. It never grants anything: the Glass still signs in and
// the Conduit still checks every request; this only decides whether to start that sign-in without
// a click, and which tab to land on.
import { beforeEach, describe, expect, test } from "vitest";

import { clearHandoff, HANDOFF_MAX_AGE_MS, readHandoff } from "./launcherHandoff";

const NOW = 1_000_000;

beforeEach(() => {
  sessionStorage.clear();
});

describe("reading the launcher's hand-off", () => {
  test("switching case signs back in without a click and returns to the tab it was on", () => {
    // Seen: choosing a case reloads the page, the sign-in is held in memory, and the person met the
    // sign-in screen and had to press its button.
    expect(readHandoff("?investigation=c1&from=case", sessionStorage, NOW)).toEqual({
      autoSignIn: true,
      view: null,
    });
    expect(readHandoff("?investigation=c1&from=case&view=ingest", sessionStorage, NOW)).toEqual({
      autoSignIn: true,
      view: "ingest",
    });
  });

  test("a case branched to ask the model opens on its questions (ADR-098 decision 4)", () => {
    expect(readHandoff("?investigation=b1&from=case&view=questions", sessionStorage, NOW)).toEqual({
      autoSignIn: true,
      view: "questions",
    });
    expect(readHandoff("?investigation=b1&from=case&view=question", sessionStorage, NOW).view).toBeNull();
  });

  test("only the exact value `case` counts as a case switch", () => {
    expect(readHandoff("?from=Case", sessionStorage, NOW).autoSignIn).toBe(false);
    expect(readHandoff("?from=cases", sessionStorage, NOW).autoSignIn).toBe(false);
  });

  test("a plain load is not a hand-off and starts nothing", () => {
    expect(readHandoff("", sessionStorage, NOW)).toEqual({ autoSignIn: false, view: null });
  });

  test("arriving from the launcher starts the sign-in", () => {
    expect(readHandoff("?from=launcher", sessionStorage, NOW)).toEqual({
      autoSignIn: true,
      view: null,
    });
  });

  test("only the exact value `launcher` counts", () => {
    for (const search of ["?from=elsewhere", "?from=", "?from=Launcher", "?view=ingest"]) {
      expect(readHandoff(search, sessionStorage, NOW).autoSignIn).toBe(false);
    }
  });

  test("the Ingest Studio tile lands on the Ingest tab, and the choice survives the sign-in trip", () => {
    expect(readHandoff("?from=launcher&view=ingest", sessionStorage, NOW)).toEqual({
      autoSignIn: true,
      view: "ingest",
    });
    // The identity provider sends the browser back to the Glass's root: no query at all.
    expect(readHandoff("", sessionStorage, NOW + 5_000)).toEqual({
      autoSignIn: false,
      view: "ingest",
    });
  });

  test("a choice left behind by an abandoned sign-in expires rather than surprising a later visit", () => {
    readHandoff("?from=launcher&view=ingest", sessionStorage, NOW);
    expect(readHandoff("", sessionStorage, NOW + HANDOFF_MAX_AGE_MS + 1).view).toBeNull();
  });

  test("choosing the Glass tile afterwards replaces an earlier Ingest choice", () => {
    readHandoff("?from=launcher&view=ingest", sessionStorage, NOW);
    readHandoff("?from=launcher", sessionStorage, NOW + 1_000);
    expect(readHandoff("", sessionStorage, NOW + 2_000).view).toBeNull();
  });

  test("only the Ingest tab can be asked for; anything else is ignored", () => {
    for (const view of ["dossier", "graph", "../x", "INGEST", ""]) {
      const search = `?from=launcher&view=${encodeURIComponent(view)}`;
      expect(readHandoff(search, sessionStorage, NOW).view).toBeNull();
    }
  });

  test("clearing removes the choice", () => {
    readHandoff("?from=launcher&view=ingest", sessionStorage, NOW);
    clearHandoff(sessionStorage);
    expect(readHandoff("", sessionStorage, NOW + 1_000).view).toBeNull();
  });

  test("a stored value that is not ours is ignored, not trusted", () => {
    sessionStorage.setItem("ospreyflow.launcherHandoff", "{not json");
    expect(readHandoff("", sessionStorage, NOW)).toEqual({ autoSignIn: false, view: null });
    sessionStorage.setItem(
      "ospreyflow.launcherHandoff",
      JSON.stringify({ view: "dossier", at: NOW }),
    );
    expect(readHandoff("", sessionStorage, NOW).view).toBeNull();
  });

  test("storage that refuses to work still lets the sign-in start and the tab be chosen", () => {
    const broken = {
      getItem: () => {
        throw new Error("blocked");
      },
      setItem: () => {
        throw new Error("blocked");
      },
      removeItem: () => {
        throw new Error("blocked");
      },
    } as unknown as Storage;
    expect(readHandoff("?from=launcher&view=ingest", broken, NOW)).toEqual({
      autoSignIn: true,
      view: "ingest",
    });
    expect(() => clearHandoff(broken)).not.toThrow();
  });
});
