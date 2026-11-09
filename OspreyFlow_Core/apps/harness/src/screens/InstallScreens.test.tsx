// @vitest-environment jsdom
//
// The guided install page's own screens (ADR-114 Amendment 3, decision 6; stage B2c). Each answers
// screen saves exactly the body the server's `PUT /api/install/answers` (or `PUT /api/config`)
// takes; Review offers Install for Lite and Save answers with the stage sentence for Small; and
// Installing shows the streamed lines and the outcome in words.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { InstallState } from "../api/types";

const client = vi.hoisted(() => ({
  getInstallDoctor: vi.fn(),
  streamInstall: vi.fn(),
}));
vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  ...client,
}));

import { CloudScreen } from "./CloudScreen";
import { DemoPacksScreen } from "./DemoPacksScreen";
import { DomainScreen } from "./DomainScreen";
import { FoldersScreen } from "./FoldersScreen";
import { InstallingScreen } from "./InstallingScreen";
import { ModeScreen } from "./ModeScreen";
import { ReviewScreen } from "./ReviewScreen";

const SMALL_SAYS = "A small server is built from a terminal on this computer, from the answers you save here: ospreyflow install --mode small --cloud aws (or azure) --config .install/install.yaml";

function state(over: Partial<InstallState> = {}): InstallState {
  return {
    mode: "lite",
    answers: { mode: "lite" },
    packs: [
      { id: "hmp", title: "HMP", shows: "A prison's people.", delivery: "generated", licence: "Own work" },
      { id: "paysim", title: "PaySim", shows: "Payments.", delivery: "download", licence: "CC BY-SA 4.0" },
    ],
    modes: {
      lite: { available: true },
      small: { available: false, says: SMALL_SAYS },
      enterprise: { available: false, says: "An enterprise install is built from a terminal on this computer, from the answers you save here: ospreyflow install --mode enterprise --cloud aws (or azure) --config .install/install.yaml" },
    },
    home: "/home/ada",
    ...over,
  };
}

beforeEach(() => {
  client.getInstallDoctor.mockReset().mockResolvedValue({ lines: ["Docker is installed."], returncode: 0 });
  client.streamInstall.mockReset();
});
afterEach(cleanup);

describe("ModeScreen", () => {
  it("offers the three modes with one sentence each and saves the chosen one", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    render(<ModeScreen state={state()} onSaveAnswers={onSaveAnswers} />);
    expect((screen.getByRole("radio", { name: /Lite/ }) as HTMLInputElement).checked).toBe(true);
    expect(screen.getByText(/16 GB memory/)).toBeTruthy();
    expect(screen.getByText(/DNS name/)).toBeTruthy();
    expect(screen.getByText(/GPU nodes/)).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: /Small/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({ mode: "small" });
  });

  it("drops the cloud answers when Lite is chosen, which Lite refuses", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    const small = state({ mode: "small", answers: { mode: "small", cloud: { provider: "aws", region: "r", domain: "d" } } });
    render(<ModeScreen state={small} onSaveAnswers={onSaveAnswers} />);
    fireEvent.click(screen.getByRole("radio", { name: /Lite/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({ mode: "lite" });
  });

  it("says in words why a save was refused", async () => {
    const refusal = Object.assign(new Error("x"), { body: JSON.stringify({ error: "mode is one of lite" }) });
    const onSaveAnswers = vi.fn().mockRejectedValue(refusal);
    render(<ModeScreen state={state()} onSaveAnswers={onSaveAnswers} />);
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("mode is one of lite"));
  });
});

const STARTERS: NonNullable<InstallState["starters"]> = [
  {
    name: "ospreyflow-crime", theme: "ospreyflow", domain: "crime", label: "The base OspreyFlow look — Crime",
    demo_packs: ["prison-intelligence", "hmp"], case_domains: ["niem"], demo_accounts: true, service_name: null,
  },
  {
    name: "govuk-aml", theme: "govuk", domain: "aml", label: "The GOV.UK Design System — AML",
    demo_packs: ["operation-ledger"], case_domains: ["fibo"], demo_accounts: true,
    service_name: "Investigate money laundering",
  },
  {
    name: "ospreyflow-blank", theme: "ospreyflow", domain: "blank", label: "The base OspreyFlow look — Blank",
    demo_packs: [], case_domains: [], demo_accounts: false, service_name: null,
  },
];

describe("ModeScreen's starter (ADR-138)", () => {
  it("offers no starter first, then each starter, and saves the chosen one with the mode", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    render(<ModeScreen state={state({ starters: STARTERS })} onSaveAnswers={onSaveAnswers} />);
    const select = screen.getByRole("combobox", { name: "Starter (optional)" }) as HTMLSelectElement;
    expect(select.value).toBe("");
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["", ...STARTERS.map((s) => s.name)]);
    fireEvent.change(select, { target: { value: "ospreyflow-crime" } });
    expect(screen.getByText(/Demo packs: prison-intelligence, hmp/)).toBeTruthy();
    expect(screen.queryByRole("textbox", { name: "Service name" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({ mode: "lite", starter: "ospreyflow-crime" });
  });

  it("asks a GOV.UK starter for the service, offering a name for the whole service", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    render(<ModeScreen state={state({ starters: STARTERS })} onSaveAnswers={onSaveAnswers} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Starter (optional)" }), { target: { value: "govuk-aml" } });
    const name = screen.getByRole("textbox", { name: "Service name" }) as HTMLInputElement;
    expect(name.value).toBe("Investigate money laundering");
    expect(screen.getByText(/name the service, not one case/)).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "Organisation" }), { target: { value: "Test Department" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({
      mode: "lite",
      starter: "govuk-aml",
      appearance: { service_name: "Investigate money laundering", organisation: "Test Department", phase: "beta" },
    });
  });

  it("says blank makes no demo case and no demo accounts", () => {
    render(<ModeScreen state={state({ starters: STARTERS })} onSaveAnswers={vi.fn()} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Starter (optional)" }), { target: { value: "ospreyflow-blank" } });
    expect(screen.getByText(/No demo case and no demo accounts/)).toBeTruthy();
  });

  it("keeps the demo packs chosen for the same starter, and drops them when the starter changes", async () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    const chosen = state({ starters: STARTERS, answers: { mode: "lite", starter: "ospreyflow-crime", demo_packs: ["hmp"] } });
    render(<ModeScreen state={chosen} onSaveAnswers={onSaveAnswers} />);
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    expect(onSaveAnswers).toHaveBeenLastCalledWith({ mode: "lite", starter: "ospreyflow-crime", demo_packs: ["hmp"] });
    await waitFor(() => expect((screen.getByRole("button", { name: "Save mode" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.change(screen.getByRole("combobox", { name: "Starter (optional)" }), { target: { value: "ospreyflow-blank" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mode" }));
    expect(onSaveAnswers).toHaveBeenLastCalledWith({ mode: "lite", starter: "ospreyflow-blank" });
  });

  it("shows no starter choice on a page served without starters", () => {
    render(<ModeScreen state={state()} onSaveAnswers={vi.fn()} />);
    expect(screen.queryByRole("combobox", { name: "Starter (optional)" })).toBeNull();
  });
});

describe("DemoPacksScreen with a starter (ADR-138)", () => {
  it("ticks the starter's packs and keeps the starter and its look when it saves", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    const withStarter = state({
      starters: STARTERS,
      answers: { mode: "lite", starter: "govuk-aml", appearance: { service_name: "S", phase: "beta" } },
      packs: [
        { id: "hmp", title: "HMP", shows: "x", delivery: "generated", licence: "Own work" },
        { id: "operation-ledger", title: "Ledger", shows: "y", delivery: "generated", licence: "Own work" },
      ],
    });
    render(<DemoPacksScreen state={withStarter} onSaveAnswers={onSaveAnswers} />);
    expect((screen.getByRole("checkbox", { name: "Ledger" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("checkbox", { name: "Ledger" }));
    fireEvent.click(screen.getByRole("button", { name: "Save demo packs" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({
      mode: "lite", starter: "govuk-aml", appearance: { service_name: "S", phase: "beta" }, demo_packs: [],
    });
  });
});

describe("FoldersScreen", () => {
  it("saves the ingest, basemap and backups folders as the storage settings", async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<FoldersScreen config={{ components: { storage: { data: "/d" } } }} onSave={onSave} />);
    fireEvent.change(screen.getByLabelText("Ingest folder"), { target: { value: "/srv/in" } });
    fireEvent.change(screen.getByLabelText("Basemap folder"), { target: { value: "/srv/map" } });
    // ADR-114 Amendment 37 decision 1: setup asks where backups go, the guided page included.
    fireEvent.change(screen.getByLabelText("Backups folder"), { target: { value: "/srv/bk" } });
    fireEvent.click(screen.getByRole("button", { name: "Save folders" }));
    expect(onSave).toHaveBeenCalledWith({
      components: { storage: { data: "/d", ingest: "/srv/in", tiles: "/srv/map", backups: "/srv/bk" } },
    });
  });

  it("suggests folders under the person's home in place of the container paths the schema ships", () => {
    render(
      <FoldersScreen
        config={{ components: { storage: { ingest: "/var/lib/osprey/ingest" } } }}
        onSave={vi.fn()}
        home="/u/ada"
      />,
    );
    expect((screen.getByLabelText("Ingest folder") as HTMLInputElement).value).toBe("/u/ada/OspreyFlow/ingest");
    expect((screen.getByLabelText("Basemap folder") as HTMLInputElement).value).toBe("/u/ada/OspreyFlow/basemap");
    // The schema's backups placeholder is a folder nobody chose: `~/OspreyFlow/backups` in its place.
    expect((screen.getByLabelText("Backups folder") as HTMLInputElement).value).toBe("/u/ada/OspreyFlow/backups");
  });

  it("says the backups folder is outside the checkout, one subfolder per deployment, and holds the data", () => {
    render(<FoldersScreen config={{ components: { storage: { backups: "/srv/bk" } } }} onSave={vi.fn()} home="/u/ada" />);
    const field = screen.getByLabelText("Backups folder") as HTMLInputElement;
    expect(field.value).toBe("/srv/bk");
    const help = document.getElementById(field.getAttribute("aria-describedby") ?? "")?.textContent ?? "";
    expect(help).toMatch(/outside the OspreyFlow folder/);
    expect(help).toMatch(/subfolder/);
    expect(help).toMatch(/synced/);
  });

  it("keeps a folder the person's own configuration already names", () => {
    render(<FoldersScreen config={{ components: { storage: { ingest: "/srv/in" } } }} onSave={vi.fn()} home="/u/ada" />);
    expect((screen.getByLabelText("Ingest folder") as HTMLInputElement).value).toBe("/srv/in");
  });
});

describe("DemoPacksScreen", () => {
  it("lists each pack with what it shows and its licence, and saves the ticked ones", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    render(<DemoPacksScreen state={state()} onSaveAnswers={onSaveAnswers} />);
    expect(screen.getByText(/A prison's people\./)).toBeTruthy();
    expect(screen.getByText(/CC BY-SA 4.0/)).toBeTruthy();
    expect(screen.queryByLabelText("PaySim file")).toBeNull();
    fireEvent.click(screen.getByRole("checkbox", { name: /HMP/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save demo packs" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({ mode: "lite", demo_packs: ["hmp"] });
  });

  it("asks where the PaySim download is, and says how it is checked, once PaySim is ticked", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    render(<DemoPacksScreen state={state()} onSaveAnswers={onSaveAnswers} />);
    fireEvent.click(screen.getByRole("checkbox", { name: /PaySim/ }));
    expect(screen.getByText(/checked by its size and SHA-256/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("PaySim file"), { target: { value: "~/Downloads/ps.csv" } });
    fireEvent.click(screen.getByRole("button", { name: "Save demo packs" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({
      mode: "lite",
      demo_packs: ["paysim"],
      paysim_file: "~/Downloads/ps.csv",
    });
  });
});

describe("CloudScreen and DomainScreen", () => {
  it("saves the provider, region and size under cloud", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    render(<CloudScreen state={state({ mode: "small", answers: { mode: "small" } })} onSaveAnswers={onSaveAnswers} />);
    fireEvent.click(screen.getByRole("radio", { name: /Azure/ }));
    fireEvent.change(screen.getByLabelText("Region"), { target: { value: "uksouth" } });
    fireEvent.change(screen.getByLabelText("Size"), { target: { value: "large" } });
    fireEvent.click(screen.getByRole("button", { name: "Save cloud and region" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({
      mode: "small",
      cloud: { provider: "azure", region: "uksouth", size: "large" },
    });
  });

  it("saves the domain beside what the cloud screen already saved, and says each app gets its own address", () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    const small = state({
      mode: "small",
      answers: { mode: "small", cloud: { provider: "aws", region: "eu-west-2", size: "small" } },
    });
    render(<DomainScreen state={small} onSaveAnswers={onSaveAnswers} />);
    expect(screen.getByText(/its own address under it/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Domain name"), { target: { value: "osprey.example.org" } });
    fireEvent.click(screen.getByRole("button", { name: "Save domain" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({
      mode: "small",
      cloud: { provider: "aws", region: "eu-west-2", size: "small", domain: "osprey.example.org" },
    });
  });
});

describe("ReviewScreen", () => {
  it("shows the answers in words, the doctor's lines and an Install button for Lite", async () => {
    const onInstall = vi.fn();
    const answers = { mode: "lite" as const, demo_packs: ["hmp"] };
    render(
      <ReviewScreen
        state={state({ answers })}
        config={{ components: { storage: { ingest: "/in", tiles: "/tiles", backups: "/bk" } } }}
        onInstall={onInstall}
        onSaveAnswers={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByText("Docker is installed.")).toBeTruthy());
    expect(client.getInstallDoctor).toHaveBeenCalled();
    expect(screen.getByText(/Mode: Lite/)).toBeTruthy();
    expect(screen.getByText(/Demo packs: HMP/)).toBeTruthy();
    expect(screen.getByText("Backups folder: /bk")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save answers" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Install" }));
    expect(onInstall).toHaveBeenCalled();
  });

  it("says a backups folder never chosen goes to ~/OspreyFlow/backups, not the placeholder", async () => {
    render(
      <ReviewScreen
        state={state({ answers: { mode: "lite" as const } })}
        config={{ components: { storage: { backups: "/var/lib/osprey/backups" } } }}
        onInstall={vi.fn()}
        onSaveAnswers={vi.fn()}
      />,
    );
    await waitFor(() => expect(screen.getByText("Docker is installed.")).toBeTruthy());
    expect(screen.getByText("Backups folder: not chosen (backups go to ~/OspreyFlow/backups)")).toBeTruthy();
  });

  it("offers Save answers and the B6 sentence for Small, and no Install", async () => {
    const onSaveAnswers = vi.fn().mockResolvedValue(undefined);
    const small = state({ mode: "small", answers: { mode: "small" } });
    render(<ReviewScreen state={small} config={{}} onInstall={vi.fn()} onSaveAnswers={onSaveAnswers} />);
    await waitFor(() => expect(client.getInstallDoctor).toHaveBeenCalled());
    expect(screen.getByText(SMALL_SAYS)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Install" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save answers" }));
    expect(onSaveAnswers).toHaveBeenCalledWith({ mode: "small" });
  });

  it("says a failing doctor's problem in words", async () => {
    client.getInstallDoctor.mockResolvedValue({ lines: ["Git is not installed."], returncode: 1 });
    render(<ReviewScreen state={state()} config={{}} onInstall={vi.fn()} onSaveAnswers={vi.fn()} />);
    await waitFor(() => expect(screen.getByText("Git is not installed.")).toBeTruthy());
    expect(screen.getByText(/did not pass/)).toBeTruthy();
  });
});

describe("InstallingScreen", () => {
  it("shows each streamed line in a live region, then the outcome and that the page closes", async () => {
    client.streamInstall.mockImplementation((onLine: (l: string) => void, onComplete: (c: number) => void) => {
      onLine("building the images");
      onLine("the stack is up");
      onComplete(0);
      return new AbortController();
    });
    render(<InstallingScreen />);
    const log = screen.getByRole("log", { name: "Install output" });
    expect(log.getAttribute("aria-live")).toBe("polite");
    await waitFor(() => expect(log.textContent).toContain("the stack is up"));
    expect(log.textContent).toContain("building the images");
    expect(screen.getByText(/OspreyFlow is installed/)).toBeTruthy();
    expect(screen.getByText("This page closes now.")).toBeTruthy();
  });

  it("says a failed install failed, with its code", async () => {
    client.streamInstall.mockImplementation((_l: unknown, onComplete: (c: number) => void) => {
      onComplete(3);
      return new AbortController();
    });
    render(<InstallingScreen />);
    await waitFor(() => expect(screen.getByText(/The install failed \(exit 3\)/)).toBeTruthy());
    expect(screen.getByText("This page closes now.")).toBeTruthy();
  });

  it("says what went wrong when the stream cannot be read", async () => {
    client.streamInstall.mockImplementation((_l: unknown, _c: unknown, onError: (m: string) => void) => {
      onError("The install could not be started.");
      return new AbortController();
    });
    render(<InstallingScreen />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("could not be started"));
  });
});
