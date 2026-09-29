import { useEffect, useState } from "react";

import { ApiError, postConsequences } from "../api/client";
import type { Consequences, OspreyConfig, Profile } from "../api/types";

const PROFILES: { value: Profile; label: string }[] = [
  { value: "local-lite", label: "local-lite — one laptop" },
  { value: "small", label: "small — a few machines" },
  { value: "cluster", label: "cluster — ten or more machines" },
];

export function ProfileScreen({
  config,
  onSave,
}: {
  config: OspreyConfig;
  onSave: (patch: Partial<OspreyConfig>) => Promise<void>;
}) {
  const [selected, setSelected] = useState<Profile>(config.profile ?? "local-lite");
  const [consequences, setConsequences] = useState<Consequences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setSelected(config.profile ?? "local-lite");
  }, [config.profile]);

  useEffect(() => {
    // §2.1: "consequences are shown, not described... updating as later screens change" — a live
    // preview against the draft selection, before Save is ever pressed.
    let cancelled = false;
    postConsequences({ ...config, profile: selected })
      .then((result) => {
        if (!cancelled) setConsequences(result);
      })
      .catch(() => {
        if (!cancelled) setConsequences(null);
      });
    return () => {
      cancelled = true;
    };
  }, [config, selected]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ profile: selected });
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.body : String(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="profile-heading">
      <h2 id="profile-heading">Profile</h2>
      <fieldset>
        <legend>Choose a profile</legend>
        {PROFILES.map(({ value, label }) => (
          <label key={value} style={{ display: "block" }}>
            <input
              type="radio"
              name="profile"
              value={value}
              checked={selected === value}
              onChange={() => setSelected(value)}
            />{" "}
            {label}
          </label>
        ))}
      </fieldset>

      {consequences && (
        <dl aria-label="Consequences of this choice">
          <dt>Machines</dt>
          <dd>{consequences.machines}</dd>
          <dt>Orchestrator</dt>
          <dd>{consequences.orchestrator}</dd>
          <dt>Memory floor</dt>
          <dd>{consequences.memory_gb_floor} GB</dd>
        </dl>
      )}

      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save profile
      </button>
    </section>
  );
}
