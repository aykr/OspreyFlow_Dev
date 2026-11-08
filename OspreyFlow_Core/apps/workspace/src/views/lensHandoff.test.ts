import { describe, expect, it } from "vitest";

import { rememberCaseView, takeCaseView, withoutCaseView } from "./lensHandoff";

function storage(): Storage {
  const held = new Map<string, string>();
  return {
    getItem: (k: string) => held.get(k) ?? null,
    setItem: (k: string, v: string) => void held.set(k, v),
    removeItem: (k: string) => void held.delete(k),
    clear: () => held.clear(),
    key: () => null,
    get length() {
      return held.size;
    },
  };
}

describe("lensHandoff", () => {
  it("takes the view noted for this case once, then forgets it", () => {
    const s = storage();
    rememberCaseView("c2", "v-hmp", s);
    expect(takeCaseView("c2", "", s)).toBe("v-hmp");
    expect(takeCaseView("c2", "", s)).toBeNull();
  });

  it("never takes a view noted for another case", () => {
    const s = storage();
    rememberCaseView("c2", "v-hmp", s);
    expect(takeCaseView("c1", "", s)).toBeNull();
  });

  it("takes the view in the address, which survives no sign-in round trip on its own", () => {
    expect(takeCaseView("c1", "?investigation=c1&case_view=v%201", storage())).toBe("v 1");
  });

  it("gives the address back without case_view, everything else kept", () => {
    expect(withoutCaseView("http://glass/?investigation=c1&from=case&case_view=v1")).toBe(
      "http://glass/?investigation=c1&from=case",
    );
  });
});
