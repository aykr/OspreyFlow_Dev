import { useId, useState } from "react";

import { Input } from "./Input";

export interface ComboboxOption {
  value: string;
  label: string;
}

export interface ComboboxProps {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  /** Fires on every keystroke, separately from `onChange` (which fires
   * only when an option is picked) — the hook a remote-search caller
   * (`search/GlobalSearch.tsx`) needs to actually issue the query as the
   * analyst types, not only once they select a result. Local-only
   * filtering (the common case) can ignore this and rely on `options`
   * already holding everything. */
  onQueryChange?: (query: string) => void;
  placeholder?: string;
  "aria-label"?: string;
}

/** Combines a text input (free typing) with a filtered listbox — used for
 * global search (`docs/02_GLASS_FRONTEND.md`'s workspace layout's search
 * box) and any other "type to narrow, then pick" control. */
export function Combobox({ options, value, onChange, onQueryChange, placeholder, ...aria }: ComboboxProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const listboxId = useId();
  const filtered = query
    ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
    : options;

  return (
    <div className="combobox">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-label={aria["aria-label"]}
        placeholder={placeholder}
        value={query || value}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          onQueryChange?.(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 100)}
      />
      {open && filtered.length > 0 && (
        <ul className="combobox__listbox" id={listboxId} role="listbox">
          {filtered.map((option) => (
            <li
              key={option.value}
              role="option"
              aria-selected={option.value === value}
              className="combobox__option"
              onMouseDown={() => {
                onChange(option.value);
                setQuery("");
                setOpen(false);
              }}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
