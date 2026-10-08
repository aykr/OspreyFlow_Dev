// Which of the unit's datasets a case reads (ADR-099), as a list of boxes to tick, in the order
// they were ticked. Shared by a new case's form and a case's own "Data this case reads".
import { Checkbox } from "../design/primitives/Checkbox";
import { datasetLabel, type Dataset } from "./cases";

export interface DatasetChoiceProps {
  datasets: readonly Dataset[];
  chosen: readonly string[];
  onChange: (chosen: string[]) => void;
  legend: string;
  disabled?: boolean;
}

export function DatasetChoice({ datasets, chosen, onChange, legend, disabled }: DatasetChoiceProps) {
  return (
    <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--sp-4)" }}>
      <legend className="label" style={{ marginBottom: "var(--sp-4)" }}>
        {legend}
      </legend>
      {datasets.length === 0 && (
        <span className="label">Your unit holds no datasets yet.</span>
      )}
      {datasets.map((dataset) => (
        <label key={dataset.id} style={{ display: "flex", gap: "var(--sp-8)", alignItems: "center" }}>
          <Checkbox
            checked={chosen.includes(dataset.id)}
            disabled={disabled}
            onChange={(event) =>
              onChange(
                event.target.checked
                  ? [...chosen, dataset.id]
                  : chosen.filter((id) => id !== dataset.id),
              )
            }
          />
          {datasetLabel(dataset.id, dataset.name)}
        </label>
      ))}
    </fieldset>
  );
}
