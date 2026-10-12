import { useState } from "react";

import { errorMessage } from "../api/client";
import type { InstallAnswers, InstallMode, InstallState } from "../api/types";

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

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      // Cloud answers belong to Small and Enterprise; Lite refuses them, so they go when Lite is chosen.
      const { cloud, ...rest } = state.answers;
      await onSaveAnswers({ ...rest, mode: selected, ...(selected !== "lite" && cloud ? { cloud } : {}) });
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
      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save mode
      </button>
    </section>
  );
}
