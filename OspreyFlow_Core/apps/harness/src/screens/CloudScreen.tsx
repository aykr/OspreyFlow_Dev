import { useState } from "react";

import { errorMessage } from "../api/client";
import type { InstallAnswers, InstallCloud, InstallState } from "../api/types";

const PROVIDERS: { value: NonNullable<InstallCloud["provider"]>; label: string }[] = [
  { value: "aws", label: "AWS" },
  { value: "azure", label: "Azure" },
];
const SIZES = ["small", "medium", "large"] as const;

export function CloudScreen({
  state,
  onSaveAnswers,
}: {
  state: InstallState;
  onSaveAnswers: (answers: InstallAnswers) => Promise<void>;
}) {
  const cloud = state.answers.cloud ?? {};
  const [provider, setProvider] = useState<NonNullable<InstallCloud["provider"]>>(cloud.provider ?? "aws");
  const [region, setRegion] = useState(cloud.region ?? "");
  const [size, setSize] = useState<NonNullable<InstallCloud["size"]>>(cloud.size ?? "medium");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSaveAnswers({ ...state.answers, cloud: { ...cloud, provider, region, size } });
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="cloud-heading">
      <h2 id="cloud-heading">Cloud and region</h2>
      <fieldset>
        <legend>Cloud</legend>
        {PROVIDERS.map(({ value, label }) => (
          <label key={value} style={{ display: "block" }}>
            <input
              type="radio"
              name="cloud-provider"
              value={value}
              checked={provider === value}
              onChange={() => setProvider(value)}
            />{" "}
            {label}
          </label>
        ))}
      </fieldset>
      <label htmlFor="cloud-region">Region</label>
      <input
        id="cloud-region"
        className="input"
        value={region}
        onChange={(event) => setRegion(event.target.value)}
        aria-describedby="cloud-region-help"
      />
      <p id="cloud-region-help" className="help">
        The cloud&rsquo;s own name for it, for example eu-west-2 or uksouth.
      </p>
      <label htmlFor="cloud-size">Size</label>
      <select
        id="cloud-size"
        className="select"
        value={size}
        onChange={(event) => setSize(event.target.value as (typeof SIZES)[number])}
      >
        {SIZES.map((value) => (
          <option key={value} value={value}>
            {value}
          </option>
        ))}
      </select>
      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save cloud and region
      </button>
    </section>
  );
}
