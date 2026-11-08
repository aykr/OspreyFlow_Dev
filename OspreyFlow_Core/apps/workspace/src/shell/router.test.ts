// @vitest-environment jsdom
// ADR-146 decision 6: an alert's address. Parsed only as `/alerts/<id>`; Back returns to where the
// person was; the sign-in round trip keeps it.
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ADDRESS_NOTE_KEY, alertPath, navigate, noteAddress, parseAddress, takeNotedAddress, useAddress } from "./router";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  sessionStorage.clear();
});

describe("an alert's address", () => {
  it("reads /alerts/<id> and nothing else", () => {
    expect(parseAddress("/alerts/al-14")).toEqual({ kind: "alert", alertId: "al-14" });
    expect(parseAddress("/alerts/al%2F14/")).toEqual({ kind: "alert", alertId: "al/14" });
    expect(parseAddress("/rules")).toEqual({ kind: "rules" });
    for (const other of ["/", "/alerts", "/alerts/", "/alerts/a/b", "/rules/al-14", "/rulesx", "/alerts/%E0%A4%A"]) {
      expect(parseAddress(other)).toEqual({ kind: "none" });
    }
  });

  it("round-trips an id through its path, whatever it holds", () => {
    for (const id of ["al-14", "a b", "x/y", "ünï"]) expect(parseAddress(alertPath(id))).toEqual({ kind: "alert", alertId: id });
  });

  it("follows navigate, and Back returns to where the person was", async () => {
    const { result } = renderHook(() => useAddress());
    expect(result.current).toEqual({ kind: "none" });
    act(() => navigate(alertPath("al-14")));
    expect(result.current).toEqual({ kind: "alert", alertId: "al-14" });
    await act(async () => {
      const back = new Promise((resolve) => window.addEventListener("popstate", resolve, { once: true }));
      window.history.back();
      await back;
    });
    expect(result.current).toEqual({ kind: "none" });
  });

  it("is kept over the sign-in round trip, once", () => {
    noteAddress({ pathname: "/alerts/al-14" });
    expect(takeNotedAddress()).toBe("/alerts/al-14");
    expect(takeNotedAddress()).toBeNull();
  });

  it("notes nothing for a path that is no address, and takes back no other path", () => {
    noteAddress({ pathname: "/" });
    expect(sessionStorage.getItem(ADDRESS_NOTE_KEY)).toBeNull();
    sessionStorage.setItem(ADDRESS_NOTE_KEY, "https://elsewhere.example/alerts/x");
    expect(takeNotedAddress()).toBeNull();
  });
});
