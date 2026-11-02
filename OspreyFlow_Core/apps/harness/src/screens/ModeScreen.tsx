import { useState } from "react";

import { errorMessage } from "../api/client";
import type { InstallAnswers, InstallAppearance, InstallMode, InstallState } from "../api/types";

const PHASES: { value: NonNullable<InstallAppearance["phase"]>; label: string }[] = [
  { value: "alpha", label: "Alpha" },
  { value: "beta", label: "Beta" },
  { value: "live", label: "Live" },
  { value: "none", label: "None (no phase banner)" },
];

// One sentence each, from ADR-114 decision 4's prerequisites.
const MODES: { value: InstallMode; label: string; needs: string }[] = [
  {
    value: "lite",
    label: "Lite — one computer",
    needs:
      "Needs Docker, 16 GB memory (32 GB is comfortable), 60 GB free disk, Git and the internet " +
      "for the first install.",
  },
  {
    value: "small",
    label: "Small — one virtual machine in the cloud",
    needs:
      "Needs an AWS or Azure account with the permissions listed for it, OpenTofu, the cloud's " +
      "command line signed in, and a DNS name you control.",
  },
  {
    value: "enterprise",
    label: "Enterprise — a cluster in the cloud",
    needs:
      "Needs everything Small needs, plus EKS or AKS quota including GPU nodes for the models, " +
      "and Helm.",
  },
];

export function ModeScreen({
  state,
  onSaveAnswers,
}: {
  state: InstallState;
  onSaveAnswers: (answers: InstallAnswers) => Promise<void>;
}) {
  const [selected, setSelected] = useState<InstallMode>(state.mode);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // ADR-138 decision 1: a starter (a theme and a domain) pre-fills the answers the later screens ask.
  const starters = state.starters ?? [];
  const [starterName, setStarterName] = useState(state.answers.starter ?? "");
  const starter = starters.find((s) => s.name === starterName);
  const govuk = starter?.theme === "govuk";
  const [serviceName, setServiceName] = useState(state.answers.appearance?.service_name ?? "");
  const [organisation, setOrganisation] = useState(state.answers.appearance?.organisation ?? "");
  const [phase, setPhase] = useState<NonNullable<InstallAppearance["phase"]>>(
    state.answers.appearance?.phase ?? "beta",
  );

  function chooseStarter(name: string) {
    setStarterName(name);
    const next = starters.find((s) => s.name === name);
    // The service name offered first names the whole service, never one case; still yours to change.
    if (next?.theme === "govuk" && !serviceName && next.service_name) setServiceName(next.service_name);
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      // Cloud answers belong to Small and Enterprise; Lite refuses them, so they go when Lite is chosen.
      // A starter's own answers are replaced whole: a different starter keeps none of the last one's.
      const { cloud, demo_packs } = state.answers;
      const rest: InstallAnswers = { ...state.answers };
      for (const key of ["cloud", "starter", "appearance", "demo_packs", "demo_accounts"] as const) delete rest[key];
      const changedStarter = (state.answers.starter ?? "") !== starterName;
      const appearance: InstallAppearance | undefined = govuk
        ? {
            service_name: serviceName.trim(),
            ...(organisation.trim() ? { organisation: organisation.trim() } : {}),
            phase,
          }
        : undefined;
      await onSaveAnswers({
        ...rest,
        mode: selected,
        ...(selected !== "lite" && cloud ? { cloud } : {}),
        ...(starterName ? { starter: starterName } : {}),
        ...(appearance ? { appearance } : {}),
        // Packs chosen on Demo packs stay, unless the starter changed (its own then apply).
        ...(demo_packs && !changedStarter ? { demo_packs } : {}),
      });
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="mode-heading">
      <h2 id="mode-heading">Mode</h2>
      <fieldset>
        <legend>Choose how to install</legend>
        {MODES.map(({ value, label, needs }) => (
          <div key={value}>
            <label style={{ display: "block" }}>
              <input
                type="radio"
                name="mode"
                value={value}
                checked={selected === value}
                onChange={() => setSelected(value)}
                aria-describedby={`mode-${value}-needs`}
              />{" "}
              {label}
            </label>
            <p id={`mode-${value}-needs`} className="help">
              {needs}
            </p>
          </div>
        ))}
      </fieldset>
      {starters.length > 0 && (
        <>
          <label htmlFor="starter">Starter (optional)</label>
          <select
            id="starter"
            className="input"
            value={starterName}
            onChange={(event) => chooseStarter(event.target.value)}
            aria-describedby="starter-help"
          >
            <option value="">No starter: choose each answer yourself</option>
            {starters.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name} — {s.label}
              </option>
            ))}
          </select>
          <p id="starter-help" className="help">
            A theme and a domain. It only fills in answers the later screens ask, and each can still be
            changed.
            {starter &&
              (starter.demo_packs.length
                ? ` Demo packs: ${starter.demo_packs.join(", ")}.`
                : " No demo case and no demo accounts.")}
          </p>
          {govuk && (
            <fieldset>
              <legend>The GOV.UK service</legend>
              <label htmlFor="service-name">Service name</label>
              <input
                id="service-name"
                className="input"
                value={serviceName}
                onChange={(event) => setServiceName(event.target.value)}
                aria-describedby="service-name-help"
              />
              <p id="service-name-help" className="help">
                Shown in the GOV.UK header on every case, so name the service, not one case.
              </p>
              <label htmlFor="organisation">Organisation</label>
              <input
                id="organisation"
                className="input"
                value={organisation}
                onChange={(event) => setOrganisation(event.target.value)}
              />
              <label htmlFor="phase">Phase</label>
              <select
                id="phase"
                className="input"
                value={phase}
                onChange={(event) => setPhase(event.target.value as NonNullable<InstallAppearance["phase"]>)}
              >
                {PHASES.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </fieldset>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save mode
      </button>
    </section>
  );
}
