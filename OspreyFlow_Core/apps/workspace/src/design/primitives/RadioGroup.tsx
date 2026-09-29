export interface RadioOption {
  value: string;
  label: string;
}

export interface RadioGroupProps {
  name: string;
  options: RadioOption[];
  value: string;
  onChange: (value: string) => void;
  "aria-label": string;
}

export function RadioGroup({ name, options, value, onChange, ...aria }: RadioGroupProps) {
  return (
    <div className="radio-group" role="radiogroup" aria-label={aria["aria-label"]}>
      {options.map((option) => (
        <label className="radio-group__option" key={option.value}>
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
          />
          {option.label}
        </label>
      ))}
    </div>
  );
}
