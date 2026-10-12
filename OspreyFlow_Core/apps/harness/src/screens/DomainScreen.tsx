import { useState } from "react";

import { errorMessage } from "../api/client";
import type { InstallAnswers, InstallState } from "../api/types";

export function DomainScreen({
  state,
  onSaveAnswers,
}: {
  state: InstallState;
  onSaveAnswers: (answers: InstallAnswers) => Promise<void>;
}) {
  const cloud = state.answers.cloud ?? {};
  const [domain, setDomain] = useState(cloud.domain ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSaveAnswers({
        ...state.answers,
        cloud: { ...cloud, provider: cloud.provider ?? "aws", domain },
      });
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section aria-labelledby="domain-heading">
      <h2 id="domain-heading">Domain</h2>
      <label htmlFor="domain-name">Domain name</label>
      <input
        id="domain-name"
        className="input"
        value={domain}
        onChange={(event) => setDomain(event.target.value)}
        aria-describedby="domain-name-help"
      />
      <p id="domain-name-help" className="help">
        A name you control. Each app gets its own address under it: the workspace at the name
        itself, the dashboards at bi. and the sign-in at id.
      </p>
      {error && <p role="alert">{error}</p>}
      <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
        Save domain
      </button>
    </section>
  );
}
