// @vitest-environment jsdom
// Studio › Releases (ADR-140 Amendment 9 decision 4). What would fail if each part were wrong: an
// export offered to someone without its rights; a pipeline left out unsaid; an import offered before
// a clean check, or after a refused one; a refusal shown as a status code; the import's words saying
// a model went live; a folder's own name kept in the paths sent.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { bundleFromFolder, releaseName } from "./releasesApi";
import { RELEASE_WORDS, ReleasesTab } from "./ReleasesTab";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const ALL = new Set([
  "edit_target_model",
  "publish_pipelines",
  "edit_pipelines",
]);

function open(rights: ReadonlySet<string> = ALL) {
  render(
    <ReleasesTab
      apiBaseUrl="http://api"
      bearerToken="t"
      datasetId="pid"
      datasetName="Prison Intelligence"
      rights={rights}
    />,
  );
}

function answers(...bodies: { status: number; body: unknown }[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const next = bodies.shift() ?? { status: 500, body: {} };
      return new Response(JSON.stringify(next.body), { status: next.status });
    }),
  );
  return calls;
}

function folder(...files: [string, string][]) {
  return files.map(([path, text]) => {
    const file = new File([text], path.split("/").pop() ?? path);
    Object.defineProperty(file, "webkitRelativePath", { value: path });
    return file;
  });
}

describe("Export", () => {
  it("sends the release's name and version and lists the files, saying what was left out", async () => {
    const calls = answers({
      status: 200,
      body: { files: { "release.yaml": "a", "model.yaml": "b" }, left_out: 2 },
    });
    open();
    expect(
      (screen.getByLabelText("Release name") as HTMLInputElement).value,
    ).toBe("prison-intelligence");
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    await screen.findByText(/The release has 2 files\./);
    expect(
      screen.getByText(
        /2 published pipeline\(s\) are marked above what you may view/,
      ),
    ).toBeTruthy();
    expect(calls[0]!.url).toBe(
      "http://api/v1/datasets/pid/release?name=prison-intelligence&version=1",
    );
    expect(
      screen.getByRole("button", { name: "Download model.yaml" }),
    ).toBeTruthy();
  });

  it("is not offered without its rights, and says which", () => {
    open(new Set(["edit_target_model", "edit_pipelines"]));
    expect(
      (screen.getByRole("button", { name: "Export" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(screen.getByText(RELEASE_WORDS.noExport)).toBeTruthy();
  });

  it("shows a refusal in its own words", async () => {
    answers({
      status: 422,
      body: {
        error: "release_refused",
        problems: ["the dataset has no live domain model"],
      },
    });
    open();
    fireEvent.click(screen.getByRole("button", { name: "Export" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "the dataset has no live domain model",
    );
  });
});

describe("Import", () => {
  const CHECKED = {
    dry_run: true,
    items: [{ role: "pipeline", name: "Visits", action: "new_draft" }],
    refused: [],
    notes: [],
  };

  it("is offered only after a clean check, then writes drafts and says nothing is live", async () => {
    const calls = answers(
      { status: 200, body: CHECKED },
      { status: 200, body: { ...CHECKED, dry_run: false } },
    );
    open();
    const importButton = () =>
      screen.getByRole("button", {
        name: "Import as drafts",
      }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText("Choose the release's folder"), {
      target: {
        files: folder(
          ["bundle/release.yaml", "r"],
          ["bundle/pipelines/v.yaml", "p"],
        ),
      },
    });
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Check the release",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    expect(importButton().disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Check the release" }));
    await screen.findByText("Would write Visits as a new draft.");
    expect(calls[0]!.url).toContain("dry_run=true");
    expect(JSON.parse(String(calls[0]!.init?.body)).files).toEqual({
      "release.yaml": "r",
      "pipelines/v.yaml": "p",
    });
    fireEvent.click(importButton());
    await screen.findByText(RELEASE_WORDS.drafts);
    expect(calls[1]!.url).toContain("dry_run=false");
    expect(screen.queryByText(/is live|made live/)).toBeNull();
  });

  it("is never offered after a refused check, and says nothing was written", async () => {
    answers({
      status: 422,
      body: { dry_run: true, items: [], refused: ["model.yaml is changed"] },
    });
    open();
    fireEvent.change(screen.getByLabelText("Choose the release's folder"), {
      target: { files: folder(["b/release.yaml", "r"]) },
    });
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Check the release",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Check the release" }));
    await screen.findByText("model.yaml is changed");
    expect(screen.getByText("Nothing was written, because:")).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "Import as drafts",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  // CARRIES row 90: an import never silently replaces an in-progress draft of the model.
  async function chooseAndCheck() {
    fireEvent.change(screen.getByLabelText("Choose the release's folder"), {
      target: { files: folder(["b/release.yaml", "r"]) },
    });
    await waitFor(() =>
      expect(
        (
          screen.getByRole("button", {
            name: "Check the release",
          }) as HTMLButtonElement
        ).disabled,
      ).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: "Check the release" }));
  }
  const importOffered = () =>
    !(
      screen.getByRole("button", {
        name: "Import as drafts",
      }) as HTMLButtonElement
    ).disabled;

  it("shows another person's draft refused, naming them, with nothing to confirm", async () => {
    const words =
      "the domain model has an in-progress draft (version 3) by analyst-7, opened 10 November 2026 at 00:00 UTC: an import never replaces another person's draft. Ask analyst-7 to make it live or discard it in Studio › Model, then import again";
    answers({
      status: 422,
      body: {
        dry_run: true,
        items: [],
        refused: [words],
        replaces_own_draft: false,
      },
    });
    open();
    await chooseAndCheck();
    await screen.findByText(words);
    expect(screen.queryByLabelText(RELEASE_WORDS.replaceOwn)).toBeNull();
    expect(importOffered()).toBe(false);
  });

  it("asks the importer to confirm replacing their own draft, then checks and imports with it", async () => {
    const own =
      "the domain model has your own in-progress draft (version 3), opened 10 November 2026 at 00:00 UTC: importing replaces it";
    const confirmed = {
      dry_run: true,
      items: [
        {
          role: "domain_model",
          name: "the domain model",
          action: "replaces_draft",
        },
      ],
      refused: [],
      replaces_own_draft: true,
    };
    const calls = answers(
      {
        status: 422,
        body: {
          dry_run: true,
          items: [],
          refused: [own],
          replaces_own_draft: true,
        },
      },
      { status: 200, body: confirmed },
      { status: 200, body: { ...confirmed, dry_run: false } },
    );
    open();
    await chooseAndCheck();
    await screen.findByText(own);
    expect(importOffered()).toBe(false);
    expect(calls[0]!.url).toContain("replace_own_draft=false");
    fireEvent.click(screen.getByLabelText(RELEASE_WORDS.replaceOwn));
    await screen.findByText(
      "Would write the domain model as the draft, in place of the one open now.",
    );
    expect(calls[1]!.url).toContain("dry_run=true");
    expect(calls[1]!.url).toContain("replace_own_draft=true");
    expect(importOffered()).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Import as drafts" }));
    await screen.findByText(RELEASE_WORDS.drafts);
    expect(calls[2]!.url).toContain("dry_run=false");
    expect(calls[2]!.url).toContain("replace_own_draft=true");
  });

  it("shows a refusal at the write as a refused check, and a new check goes on from it", async () => {
    const meanwhile =
      "the domain model has an in-progress draft (version 3) by analyst-7, opened 12 November 2026 at 10:00 UTC: an import never replaces another person's draft";
    answers(
      { status: 200, body: CHECKED },
      { status: 422, body: { dry_run: false, items: [], refused: [meanwhile], replaces_own_draft: false } },
      { status: 200, body: CHECKED },
    );
    open();
    await chooseAndCheck();
    await screen.findByText("Would write Visits as a new draft.");
    fireEvent.click(screen.getByRole("button", { name: "Import as drafts" }));
    await screen.findByText(meanwhile);
    expect(screen.getByText("Nothing was written, because:")).toBeTruthy();
    expect(screen.queryByText(RELEASE_WORDS.drafts)).toBeNull();
    expect(importOffered()).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Check the release" }));
    await screen.findByText("Would write Visits as a new draft.");
    expect(importOffered()).toBe(true);
  });

  it("never sends a confirmation the importer did not give", async () => {
    const calls = answers(
      { status: 200, body: CHECKED },
      { status: 200, body: { ...CHECKED, dry_run: false } },
    );
    open();
    await chooseAndCheck();
    await screen.findByText("Would write Visits as a new draft.");
    expect(screen.queryByLabelText(RELEASE_WORDS.replaceOwn)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Import as drafts" }));
    await screen.findByText(RELEASE_WORDS.drafts);
    expect(calls[1]!.url).toContain("replace_own_draft=false");
  });

  it("is not offered without its rights", () => {
    open(new Set(["edit_target_model", "publish_pipelines"]));
    expect(
      (screen.getByLabelText("Choose the release's folder") as HTMLInputElement)
        .disabled,
    ).toBe(true);
    expect(screen.getByText(RELEASE_WORDS.noImport)).toBeTruthy();
  });
});

describe("the helpers", () => {
  it("names a release as Kubernetes takes one", () => {
    expect(releaseName("Prison Intelligence — 2026")).toBe(
      "prison-intelligence-2026",
    );
    expect(releaseName("—")).toBe("release");
  });

  it("drops the chosen folder's own name from each path", async () => {
    expect(
      await bundleFromFolder(
        folder(["out/release.yaml", "x"], ["out/lists/rows/ab.csv", "y"]),
      ),
    ).toEqual({
      "release.yaml": "x",
      "lists/rows/ab.csv": "y",
    });
  });
});
