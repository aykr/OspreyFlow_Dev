// *Save as a view* (ADR-144 decision 4): name what is selected and save it as a view of this case,
// private to you until you share it. The view keeps the selection, where its nodes sit and the
// timeline's window; it holds no data, so what is saved is a lens, not a copy. Under the GOV.UK
// brand it is a GOV.UK form (decision 7). Enter saves; Escape cancels.
import { useEffect, useRef, useState } from "react";

import { currentBrand } from "../brand/brand";
import "./views.css";

export interface SaveViewFormProps {
  /** How many nodes the view will hold, said on the form. */
  count: number;
  defaultName: string;
  /** Saves under `name`; answers `null` when saved, or the refusal in words. */
  onSave: (name: string) => Promise<string | null>;
  onCancel: () => void;
}

export function SaveViewForm({ count, defaultName, onSave, onCancel }: SaveViewFormProps) {
  const [name, setName] = useState(defaultName);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const govuk = currentBrand() === "govuk";

  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    if (!name.trim()) {
      setProblem("Give the view a name.");
      return;
    }
    setBusy(true);
    const refused = await onSave(name.trim());
    setBusy(false);
    if (refused) setProblem(refused);
  }

  const hint = `${count} node${count === 1 ? "" : "s"}, where they sit and the timeline's window. Only you see it until you share it.`;

  return (
    <form
      role="dialog"
      aria-labelledby="save-view-title"
      className={govuk ? "save-view save-view--govuk" : "save-view panel"}
      onSubmit={(e) => void submit(e)}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          e.stopPropagation();
          onCancel();
        }
      }}
    >
      <h2 id="save-view-title" className={govuk ? "govuk-heading-s" : "label"} style={{ margin: 0 }}>
        Save as a view
      </h2>
      <div className={govuk ? `govuk-form-group${problem ? " govuk-form-group--error" : ""}` : "save-view__field"}>
        <label htmlFor="save-view-name" className={govuk ? "govuk-label" : "label"}>
          View name
        </label>
        <div id="save-view-hint" className={govuk ? "govuk-hint" : "caption"}>
          {hint}
        </div>
        {problem && (
          <p id="save-view-problem" role="alert" className={govuk ? "govuk-error-message" : "case-views__problem"}>
            {govuk && <span className="govuk-visually-hidden">Error: </span>}
            {problem}
          </p>
        )}
        <input
          ref={input}
          id="save-view-name"
          className={govuk ? `govuk-input${problem ? " govuk-input--error" : ""}` : "input"}
          value={name}
          maxLength={200}
          aria-describedby={problem ? "save-view-hint save-view-problem" : "save-view-hint"}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className={govuk ? "govuk-button-group" : "save-view__row"}>
        <button type="submit" className={govuk ? "govuk-button" : "btn btn--primary"} disabled={busy}>
          Save view
        </button>
        <button type="button" className={govuk ? "govuk-button govuk-button--secondary" : "btn"} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
