import { Button } from "./design/primitives/Button";

export type AppName = "glass" | "ingest";

export interface AppSwitcherProps {
  app: AppName;
  onChange: (app: AppName) => void;
}

/** The two applications that share this page: the Glass (graph, map, watches) and the Ingest
 * Studio. A two-part switch at the far left of the top bar, the open one filled in brass
 * (ADR-065), so which application is open is never a guess. */
export function AppSwitcher({ app, onChange }: AppSwitcherProps) {
  return (
    <div className="app-switcher" role="group" aria-label="Application">
      <Button aria-pressed={app === "glass"} onClick={() => onChange("glass")}>
        Glass
      </Button>
      <Button aria-pressed={app === "ingest"} onClick={() => onChange("ingest")}>
        Ingest Studio
      </Button>
    </div>
  );
}
