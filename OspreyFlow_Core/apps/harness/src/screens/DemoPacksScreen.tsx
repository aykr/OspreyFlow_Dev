import { useState } from "react";

import { errorMessage } from "../api/client";
import type { InstallAnswers, InstallState } from "../api/types";

export function DemoPacksScreen({
  state,
  onSaveAnswers,
}: {
  state: InstallState;
  onSaveAnswers: (answers: InstallAnswers) => Promise<void>;
}) {
  // ADR-138: a starter's packs are ticked until the packs are chosen here.
  const starter = state.starters?.find((s) => s.name === state.answers.starter);
  const [chosen, setChosen] = useState<string[]>(state.answers.demo_packs ?? starter?.demo_packs ?? []);
  const [paysimFile, setPaysimFile] = useState(state.answers.paysim_file ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function toggle(id: string) {
    setChosen((now) => (now.includes(id) ? now.filter((p) => p !== id) : [...now, id]));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      // Offered order, not tick order, so the same choice is always the same answer.
      const packs = state.packs.map((p) => p.id).filter((id) => chosen.includes(id));
      // Every other answer is kept (the starter and the look among them); only the packs change.
      const rest: InstallAnswers = { ...state.answers };
      delete rest.demo_packs;
      delete rest.paysim_file;
      await onSaveAnswers({
        ...rest,
        // With a starter, an empty choice is said outright: left out, the starter's packs apply.
        ...(packs.length || rest.starter ? { demo_packs: packs } : {}),
        ...(packs.includes("paysim") && paysimFile ? { paysim_file: paysimFile } : {}),
      });
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="demo-packs-heading">
      <h2 id="demo-packs-heading">Demo packs</h2>
      <p>Each pack loads into its own case. You can add more later with ospreyflow demo add.</p>
      <fieldset>
        <legend>Packs to load</legend>
        {state.packs.map((pack) => (
          <div key={pack.id}>
            <label style={{ display: "block" }}>
              <input
                type="checkbox"
                checked={chosen.includes(pack.id)}
                onChange={() => toggle(pack.id)}
                aria-describedby={`pack-${pack.id}-about`}
              />{" "}
              {pack.title}
            </label>
            <p id={`pack-${pack.id}-about`} className="help">
              {pack.shows} Licence: {pack.licence}.
            </p>
          </div>
        ))}
      </fieldset>
      {chosen.includes("paysim") && (
        <>
          <label htmlFor="paysim-file">PaySim file</label>
          <input
            id="paysim-file"
            className="input"
            value={paysimFile}
            onChange={(event) => setPaysimFile(event.target.value)}
            aria-describedby="paysim-file-help"
          />
          <p id="paysim-file-help" className="help">
            The file you downloaded from PaySim&rsquo;s page. It is checked by its size and SHA-256
            before anything starts.
          </p>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save demo packs
      </button>
    </section>
  );
}
