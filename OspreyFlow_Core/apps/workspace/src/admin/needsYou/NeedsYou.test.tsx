// @vitest-environment jsdom
// The top bar's *Needs you · n* (ADR-145 decision 11, A2; L2.7). What it may list is the Conduit's
// (`test_needs_you.py`, each case red by a plant at the route); these prove the control counts only
// what the reader may decide and lists only what the Conduit served, gives every entry its tip, opens where to act, and says a failed read.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NeedsYou } from "./NeedsYou";
import {
  NEEDS_YOU_WORDS,
  needsYouCount,
  proposedIn,
  type NeedsYou as Needs,
} from "./needsYouApi";

afterEach(() => cleanup());

const API = { apiBaseUrl: "http://x", bearerToken: "t" };
const NEEDS: Needs = {
  promotions_overdue: [
    { promotion_id: "pr-1", load_id: "load-7", dataset_id: "ds-a", raised_at: "2026-11-04T09:00:00Z",
      words: "Promotion load-7 into Prison records has waited 3 days for review." },
  ],
  proposals: [
    { dataset_id: "ds-a", dataset_name: "Prison records", to_decide: 2 },
  ],
}; // prettier-ignore

async function open(
  needs: Needs | Error,
  props: Partial<Parameters<typeof NeedsYou>[0]> = {},
) {
  const read = vi.fn(async () => {
    if (needs instanceof Error) throw needs;
    return needs;
  });
  const view = render(<NeedsYou {...API} read={read} {...props} />);
  return { read, view };
}

describe("Needs you", () => {
  it("counts the overdue promotions and the proposals to decide, and lists only what the Conduit served", async () => {
    await open(NEEDS);
    const button = await screen.findByRole("button", { name: /Needs you · 3/ });
    expect(needsYouCount(NEEDS)).toBe(3);
    fireEvent.click(button);
    const panel = screen.getByRole("group", { name: "Needs you" });
    expect(panel.querySelectorAll("li")).toHaveLength(2);
  });

  it("gives every entry its tip, read with it, saying what it is and what follows", async () => {
    await open(NEEDS, {
      onOpenModel: () => undefined,
      onOpenOperations: () => undefined,
    });
    fireEvent.click(await screen.findByRole("button", { name: /Needs you/ }));
    const proposals = screen.getByRole("button", {
      name: NEEDS_YOU_WORDS.proposals(2, "Prison records"),
    });
    const promotion = screen.getByRole("button", {
      name: NEEDS.promotions_overdue[0]!.words,
    });
    expect(proposals.getAttribute("aria-describedby")).toBeTruthy();
    expect(
      document.getElementById(proposals.getAttribute("aria-describedby")!)
        ?.textContent,
    ).toBe(NEEDS_YOU_WORDS.proposalsTip);
    expect(
      document.getElementById(promotion.getAttribute("aria-describedby")!)
        ?.textContent,
    ).toBe(NEEDS_YOU_WORDS.promotionTip);
  });

  it("opens the dataset's Model tab and Admin's Operations, and closes", async () => {
    const onOpenModel = vi.fn();
    const onOpenOperations = vi.fn();
    await open(NEEDS, { onOpenModel, onOpenOperations });
    fireEvent.click(await screen.findByRole("button", { name: /Needs you/ }));
    fireEvent.click(
      screen.getByRole("button", {
        name: NEEDS_YOU_WORDS.proposals(2, "Prison records"),
      }),
    );
    expect(onOpenModel).toHaveBeenCalledWith("ds-a");
    expect(screen.queryByRole("group", { name: "Needs you" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Needs you/ }));
    fireEvent.click(
      screen.getByRole("button", { name: NEEDS.promotions_overdue[0]!.words }),
    );
    expect(onOpenOperations).toHaveBeenCalledOnce();
  });

  it("says an entry it cannot open without making it a button", async () => {
    await open(NEEDS);
    fireEvent.click(await screen.findByRole("button", { name: /Needs you/ }));
    expect(
      screen.queryByRole("button", {
        name: NEEDS.promotions_overdue[0]!.words,
      }),
    ).toBeNull();
    expect(screen.getByText(NEEDS.promotions_overdue[0]!.words)).toBeTruthy();
  });

  it("is not drawn when nothing waits, and says a failed read rather than nothing", async () => {
    const { read } = await open({ promotions_overdue: [], proposals: [] });
    await waitFor(() => expect(read).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /Needs you/ })).toBeNull();
    cleanup();
    await open(new Error("503"));
    fireEvent.click(
      await screen.findByRole("button", { name: /Needs you · \?/ }),
    );
    expect(screen.getByRole("alert").textContent).toBe(NEEDS_YOU_WORDS.unread);
  });

  it("lists the reader's own scheduled loads' notices with their tip, and counts every one (ADR-110 Amendment 19)", async () => {
    const notices: Needs = {
      promotions_overdue: [],
      proposals: [],
      schedule_notices: [
        { notice_id: "nt-2", recipe_id: "r-1", raised_at: "2026-11-10T08:00:00Z",
          words: "The scheduled run of Daily export was refused: the file was not there." },
        { notice_id: "nt-1", recipe_id: "r-1", raised_at: "2026-11-09T08:00:00Z",
          words: "The scheduled run of Daily export failed: the database did not answer." },
      ],
      schedule_notices_total: 2,
    }; // prettier-ignore
    await open(notices);
    fireEvent.click(await screen.findByRole("button", { name: /Needs you · 2/ }));
    const first = screen.getByText(/was refused: the file was not there/);
    expect(first.tagName).toBe("SPAN"); // said, focusable, not a button: there is nowhere to open
    expect(first.getAttribute("tabindex")).toBe("0");
    expect(document.getElementById(first.getAttribute("aria-describedby")!)?.textContent).toBe(
      NEEDS_YOU_WORDS.noticeTip,
    );
    expect(screen.getByText(/the database did not answer/)).toBeTruthy();
    expect(screen.queryByText(/more notice/)).toBeNull();
  });

  it("says how many notices are not listed, never cutting them silently (rule 2)", async () => {
    const many: Needs = {
      promotions_overdue: [],
      proposals: [],
      schedule_notices: [
        { notice_id: "nt-1", recipe_id: "r-1", raised_at: "2026-11-10T08:00:00Z", words: "A run failed." },
      ],
      schedule_notices_total: 23,
    }; // prettier-ignore
    expect(needsYouCount(many)).toBe(23);
    await open(many);
    fireEvent.click(await screen.findByRole("button", { name: /Needs you · 23/ }));
    expect(screen.getByText(NEEDS_YOU_WORDS.moreNotices(22))).toBeTruthy();
  });

  it("reads a Conduit from before the amendment as no notices, not a failed read", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ promotions_overdue: [], proposals: [] })));
    const { readNeedsYou } = await import("./needsYouApi");
    const read = await readNeedsYou("http://x", "t", fetcher as unknown as typeof fetch);
    expect(read.schedule_notices).toEqual([]);
    expect(needsYouCount(read)).toBe(0);
  });

  it("gives the Model tab the count of its own dataset alone", () => {
    expect(proposedIn(NEEDS, "ds-a")).toBe(2);
    expect(proposedIn(NEEDS, "ds-other")).toBe(0);
    expect(proposedIn(NEEDS, null)).toBe(0);
  });

  it("says why the Studio did not open, and drops a count a later read could not confirm", async () => {
    let answer: Needs | Error = NEEDS;
    const read = vi.fn(async () => {
      if (answer instanceof Error) throw answer;
      return answer;
    });
    const onOpenModel = vi.fn(async () => {
      throw new Error("None of your cases loads into that dataset now, so the Studio cannot open on it.");
    });
    render(<NeedsYou {...API} read={read} onOpenModel={onOpenModel} every={30} />);
    fireEvent.click(await screen.findByRole("button", { name: /Needs you · 3/ }));
    fireEvent.click(screen.getByRole("button", { name: NEEDS_YOU_WORDS.proposals(2, "Prison records") }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/None of your cases loads into that dataset/);
    answer = new Error("503");
    await screen.findByRole("button", { name: /Needs you · \?/ });
  });
});
