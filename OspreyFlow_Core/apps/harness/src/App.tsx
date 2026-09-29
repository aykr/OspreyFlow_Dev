import { useEffect, useState } from "react";

import { getConfig, putConfig } from "./api/client";
import type { OspreyConfig } from "./api/types";
import { ComponentsScreen } from "./screens/ComponentsScreen";
import { GeospatialScreen } from "./screens/GeospatialScreen";
import { GovernanceScreen } from "./screens/GovernanceScreen";
import { ModelsScreen } from "./screens/ModelsScreen";
import { PreflightScreen } from "./screens/PreflightScreen";
import { ProfileScreen } from "./screens/ProfileScreen";
import { SCREEN_NAMES, type ScreenName, useDecidedScreens } from "./store";
import { SummaryRail } from "./SummaryRail";

export function App() {
  const [config, setConfig] = useState<OspreyConfig | null>(null);
  const [screen, setScreen] = useState<ScreenName>("Profile");
  const { decided, markDecided } = useDecidedScreens();

  useEffect(() => {
    getConfig().then(setConfig);
  }, []);

  async function handleSave(patch: Partial<OspreyConfig>) {
    const next = await putConfig(patch);
    setConfig(next);
    markDecided(screen);
  }

  if (!config) return <p>Loading…</p>;

  return (
    <div className="harness-app">
      <SummaryRail decided={decided} ingestRoot={config.components?.storage?.ingest} />
      <main>
        <nav aria-label="Setup screens">
          {SCREEN_NAMES.map((name) => (
            <button
              key={name}
              type="button"
              className="btn"
              aria-pressed={screen === name}
              onClick={() => setScreen(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        {screen === "Profile" && <ProfileScreen config={config} onSave={handleSave} />}
        {screen === "Components" && <ComponentsScreen config={config} onSave={handleSave} />}
        {screen === "Models" && <ModelsScreen config={config} onSave={handleSave} />}
        {screen === "Governance" && <GovernanceScreen config={config} onSave={handleSave} />}
        {screen === "Geospatial" && <GeospatialScreen />}
        {screen === "Preflight" && <PreflightScreen />}
      </main>
    </div>
  );
}
