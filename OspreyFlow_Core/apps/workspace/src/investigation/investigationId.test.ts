// @vitest-environment jsdom
//
// `initialInvestigationId`'s own precedence — Stage 3a's own rehearsal finding, 23 September
// 2026: without a URL-param path, the Glass always created its own empty investigation on load,
// ignoring one already seeded via the API. This module's own docstring has the full reasoning;
// this proves the precedence directly rather than trusting the prose.
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  INVESTIGATION_ID_SESSION_KEY,
  initialInvestigationId,
  investigationIdFromSession,
  investigationIdFromUrl,
} from "./investigationId";

function setUrl(search: string): void {
  window.history.replaceState(null, "", search || "/");
}

describe("initialInvestigationId", () => {
  beforeEach(() => {
    sessionStorage.clear();
    setUrl("");
  });
  afterEach(() => {
    sessionStorage.clear();
    setUrl("");
  });

  it("prefers a ?investigation= URL param over sessionStorage", () => {
    sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, "stale-session-id");
    setUrl("?investigation=known-id");

    expect(initialInvestigationId()).toBe("known-id");
  });

  it("falls back to sessionStorage when no URL param is present", () => {
    sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, "session-id");

    expect(initialInvestigationId()).toBe("session-id");
  });

  it("returns null when neither is set, so the caller still creates one", () => {
    expect(initialInvestigationId()).toBeNull();
  });

  it("investigationIdFromUrl reads the exact param name the guide documents", () => {
    setUrl("?investigation=abc-123&other=x");

    expect(investigationIdFromUrl()).toBe("abc-123");
  });

  it("investigationIdFromSession reads the same key App.tsx writes on bootstrap", () => {
    sessionStorage.setItem(INVESTIGATION_ID_SESSION_KEY, "written-by-app");

    expect(investigationIdFromSession()).toBe("written-by-app");
  });
});
