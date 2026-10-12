// Start's decision (ADR-114 Amendment 5 point 9), out of `App.tsx` so the keyboard walkthrough drives
// the same wiring the Glass runs: Start itself, the place chosen on it, or `null` for the workspace.
import type { ReactElement, ReactNode } from "react";

import { CasePicker } from "../investigation/CasePicker";
import { startFor, startPlaces, type Rights, type StartPlace } from "../rights/visibility";
import { AdminWithoutCase } from "./AdminWithoutCase";
import { StartPage } from "./StartPage";

export type StartChoice = StartPlace | "start" | null;

export interface StartScreenInput {
  rights: Rights;
  /** The rights have been asked for and answered (or refused): Start waits, so a single place is
   * not missed and a tile does not appear late. */
  rightsSettled: boolean;
  investigationId: string | null;
  /** `null` with a case open is the workspace itself. */
  startChoice: StartChoice;
  setStartChoice: (choice: StartChoice) => void;
  account: ReactNode;
  apiBaseUrl: string;
  bearerToken: string;
  lastCaseId: string | null;
  isAdministrator: boolean;
  openCase: (id: string, view?: "ingest") => void;
  /** The case list over the open case, with a way back to it. */
  browseCases: () => void;
  /** The Studio on the open case. */
  openStudio: () => void;
}

export function startScreen(input: StartScreenInput): ReactElement | null {
  const { rights, investigationId, startChoice, setStartChoice } = input;
  if (investigationId && startChoice === null) return null;
  if (!input.rightsSettled) {
    return <div style={{ padding: "var(--sp-24)", color: "var(--text-secondary)" }}>Loading…</div>;
  }
  const places = startPlaces(rights);
  const where = investigationId ? startChoice : startFor(places, startChoice);
  if (where === "start") {
    return (
      <StartPage
        places={places}
        account={input.account}
        onChoose={(place) => {
          if (!investigationId) return setStartChoice(place);
          // A case is open behind Start: the Glass offers the cases with a way back to it, and the
          // Studio opens on it; the Admin area needs no case either way.
          setStartChoice(place === "admin" ? "admin" : null);
          if (place === "glass") input.browseCases();
          if (place === "ingest") input.openStudio();
        }}
      />
    );
  }
  if (where === "admin" && rights) {
    return (
      <AdminWithoutCase
        apiBaseUrl={input.apiBaseUrl}
        bearerToken={input.bearerToken}
        rights={rights}
        account={input.account}
        onStart={() => setStartChoice("start")}
      />
    );
  }
  if (investigationId) return null;
  return (
    <CasePicker
      apiBaseUrl={input.apiBaseUrl}
      bearerToken={input.bearerToken}
      lastCaseId={input.lastCaseId}
      isAdministrator={input.isAdministrator}
      title={where === "ingest" ? "Choose the case to load into" : "Choose a case"}
      onStart={places.length > 1 ? () => setStartChoice("start") : undefined}
      onOpen={(id) => input.openCase(id, where === "ingest" ? "ingest" : undefined)}
    />
  );
}
