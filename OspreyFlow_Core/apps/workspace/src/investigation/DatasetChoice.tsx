// Which one of the unit's datasets a case reads (ADR-099 Amendment 12: exactly one, a source or a
// composite), as a radio list. Shared by a new case's form and a case's own "Data this case reads".
// The Conduit never sends an analyst layer (ADR-143 decision 1), so none can be offered here.
import { RadioGroup } from "../design/primitives/RadioGroup";
import { type Dataset, datasetChoiceLabel } from "./cases";

export interface DatasetChoiceProps {
  datasets: readonly Dataset[];
  chosen: string | null;
  onChange: (chosen: string) => void;
  legend: string;
  /** The radio group's name, unique on the page (a new case's form and a case's setting differ). */
  name: string;
}

export function DatasetChoice({ datasets, chosen, onChange, legend, name }: DatasetChoiceProps) {
  return (
    <div style={{ display: "grid", gap: "var(--sp-4)" }}>
      <span className="label">{legend}</span>
      {datasets.length === 0 ? (
        <span className="label">Your unit holds no datasets yet.</span>
      ) : (
        <RadioGroup
          name={name}
          aria-label={legend}
          value={chosen ?? ""}
          onChange={onChange}
          // The name alone (with a composite's size): names are unique (ADR-099 Amendment 6), and
          // a raw id reads as noise to an analyst (owner, 9 October 2026).
          options={datasets.map((dataset) => ({ value: dataset.id, label: datasetChoiceLabel(dataset) }))}
        />
      )}
    </div>
  );
}
