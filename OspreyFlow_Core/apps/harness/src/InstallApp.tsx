// The guided install page's shell (`06_DECISIONS.md` ADR-114 Amendment 3, decision 6): the
// Set-up console's own screens, with the install's own — Mode first, then the chosen mode's list.
// It works on a draft `osprey.yaml` through the same `PUT /api/config`, and on the install answers
// through `PUT /api/install/answers`; `harness/install_page.py` serves both.
import { useEffect, useState } from "react";

import { errorMessage, getConfig, getInstallState, putConfig, putInstallAnswers } from "./api/client";
import type { InstallAnswers, InstallMode, InstallState, OspreyConfig, Profile } from "./api/types";
import { CloudScreen } from "./screens/CloudScreen";
import { ComponentsScreen } from "./screens/ComponentsScreen";
import { DemoPacksScreen } from "./screens/DemoPacksScreen";
import { DomainScreen } from "./screens/DomainScreen";
import { FoldersScreen } from "./screens/FoldersScreen";
import { GeospatialScreen } from "./screens/GeospatialScreen";
import { GovernanceScreen } from "./screens/GovernanceScreen";
import { InstallingScreen } from "./screens/InstallingScreen";
import { ModeScreen } from "./screens/ModeScreen";
import { ModelsScreen } from "./screens/ModelsScreen";
import { ProfileScreen } from "./screens/ProfileScreen";
import { ReviewScreen } from "./screens/ReviewScreen";
import { type InstallScreenName, installNav, useDecidedScreens } from "./store";
import { SummaryRail } from "./SummaryRail";

// Each mode's own profile (`ospreyflow.answers.PROFILES`), written to the draft when the mode is
// saved. Enterprise's is not written: a cluster profile is refused until it names its hosts, which
// stage B7 collects, so its answers are kept and the draft is left as it is.
const PROFILE_FOR: Partial<Record<InstallMode, Profile>> = { lite: "local-lite", small: "small" };

export function InstallApp() {
  const [config, setConfig] = useState<OspreyConfig | null>(null);
  const [state, setState] = useState<InstallState | null>(null);
  const [screen, setScreen] = useState<InstallScreenName>("Mode");
  const [installing, setInstalling] = useState(false);
  const { decided, markDecided } = useDecidedScreens<InstallScreenName>();

  useEffect(() => {
    getConfig().then(setConfig);
    getInstallState().then(setState);
  }, []);

  async function handleSave(patch: Partial<OspreyConfig>) {
    setConfig(await putConfig(patch));
    markDecided(screen);
  }

  async function handleSaveAnswers(answers: InstallAnswers) {
    const profile = PROFILE_FOR[answers.mode];
    const modeChanged = state !== null && answers.mode !== state.mode;
    setState(await putInstallAnswers(answers));
    if (modeChanged && profile) {
      try {
        setConfig(await putConfig({ profile }));
      } catch (exc) {
        // The answers are saved; the draft keeps its profile, which the Profile screen can still change.
        throw new Error(`Your mode is saved, but its profile could not be set: ${errorMessage(exc)}`);
      }
    }
    markDecided(screen);
  }

  if (!config || !state) return <p>Loading…</p>;

  if (installing) {
    return (
      <div className="harness-app">
        <SummaryRail decided={decided} screens={installNav(state.mode)} />
        <main>
          <InstallingScreen />
        </main>
      </div>
    );
  }

  const nav = installNav(state.mode);
  const current = nav.includes(screen) ? screen : "Mode";

  return (
    <div className="harness-app">
      <SummaryRail decided={decided} screens={nav} ingestRoot={config.components?.storage?.ingest} />
      <main>
        <nav aria-label="Install screens">
          {nav.map((name) => (
            <button
              key={name}
              type="button"
              className="btn"
              aria-pressed={current === name}
              onClick={() => setScreen(name)}
            >
              {name}
            </button>
          ))}
        </nav>
        {current === "Mode" && <ModeScreen state={state} onSaveAnswers={handleSaveAnswers} />}
        {current === "Folders" && <FoldersScreen config={config} onSave={handleSave} home={state.home} />}
        {current === "Profile" && <ProfileScreen config={config} onSave={handleSave} />}
        {current === "Cloud and region" && <CloudScreen state={state} onSaveAnswers={handleSaveAnswers} />}
        {current === "Domain" && <DomainScreen state={state} onSaveAnswers={handleSaveAnswers} />}
        {current === "Components" && <ComponentsScreen config={config} onSave={handleSave} />}
        {current === "Map" && <GeospatialScreen />}
        {current === "Models" && <ModelsScreen config={config} onSave={handleSave} />}
        {current === "Governance" && <GovernanceScreen config={config} onSave={handleSave} />}
        {current === "Demo packs" && <DemoPacksScreen state={state} onSaveAnswers={handleSaveAnswers} />}
        {current === "Review" && (
          <ReviewScreen
            state={state}
            config={config}
            onInstall={() => setInstalling(true)}
            onSaveAnswers={handleSaveAnswers}
          />
        )}
      </main>
    </div>
  );
}
