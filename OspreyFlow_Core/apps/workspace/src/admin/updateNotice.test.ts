// ADR-114 decision 13, Amendment 8 point 2: Admin → System says the version and the last update
// check in words, and how to act on it — on the host, since the Glass runs nothing.
import { describe, expect, it } from "vitest";

import type { UpdateNotice } from "../../../../packages/schemas/generated";
import { updateWords } from "./updateNotice";

const checked = (over: Partial<UpdateNotice>): UpdateNotice => ({
  current: "v0.4.1",
  checked_at: "2026-10-13T08:00:00Z",
  latest: "v0.4.1",
  update_available: false,
  notes: null,
  url: null,
  problem: null,
  ...over,
});

describe("updateWords", () => {
  it("offers a newer release with the command to run on the host", () => {
    const words = updateWords("v0.4.1", checked({ latest: "v0.5.0", update_available: true, notes: "- Find connections" }));
    expect(words.tone).toBe("available");
    expect(words.headline).toBe("v0.5.0 is available.");
    expect(words.detail).toBe("Checked 13 October 2026 at 08:00 UTC. On the machine OspreyFlow runs on: ospreyflow update");
  });

  it("says up to date, with when", () => {
    expect(updateWords("v0.4.1", checked({})).headline).toBe("Up to date: v0.4.1 is the newest release.");
  });

  it("tells a deployment built from its checkout how it moves, never to update", () => {
    const words = updateWords("dev-abc1234", checked({ current: "dev-abc1234", latest: "v0.5.0" }));
    expect(words.tone).toBe("plain");
    expect(words.headline).toBe("This deployment builds from its checkout; it moves with git pull and ospreyflow start --build.");
    expect(words.detail).toContain("The newest release is v0.5.0.");
  });

  it("says why a check could not answer, and offers nothing", () => {
    const words = updateWords("v0.4.1", checked({ latest: null, problem: "GitHub's limit on unauthenticated requests was reached; try again in an hour." }));
    expect(words.tone).toBe("problem");
    expect(words.headline).toBe("The last update check could not answer.");
    expect(words.detail).toContain("limit on unauthenticated requests");
  });

  it("says when there has been no check, and how to make one", () => {
    expect(updateWords("v0.4.1", null)).toEqual({
      tone: "plain",
      headline: "Not checked for updates yet.",
      detail: "On the machine OspreyFlow runs on: ospreyflow update --check",
    });
  });
});
