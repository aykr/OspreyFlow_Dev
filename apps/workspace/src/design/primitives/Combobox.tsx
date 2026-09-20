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
 * box) and any other "type to narrow, then pick" control.
 *
 * **Keyboard selection, added when the query-builder's own `pin-node-from-search` keyboard action
 * (`keyboard/query-builder.spec.ts`) went looking for one and found the listbox only ever wired
 * to `onMouseDown`** — every existing caller (`GlobalSearch.tsx`) inherited the same gap, since
 * nothing before this stage had a keyboard-only test exercising a selection rather than only the
 * open/typing half. Fixed here, once, in the shared primitive, the same "the second surface makes
 * the first primitive's gap visible" pattern `actionRegistry.ts`'s own module docstring already
 * names for the coverage-gate fix alongside it — not worked around per-caller. `ArrowDown`/
 * `ArrowUp` move a highlighted option (`aria-activedescendant`, WAI-ARIA combobox pattern);
 * `Enter` selects whichever option is highlighted, defaulting to the first when none has been
 * moved to yet, so a user who types a narrowing query and immediately presses Enter reaches the
 * same result a mouse click on the top option would. */
export function Combobox({ options, value, onChange, onQueryChange, placeholder, ...aria }: ComboboxProps) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const listboxId = useId();
  // A caller that passes `onQueryChange` is driving `options` itself (a
  // remote search, `search/GlobalSearch.tsx`'s own case) — `options`
  // already *is* the filtered set for the current query, generally
  // against fields (identifiers, ids) the visible `label` never contains
  // (an entity's opaque node id, not its search query). Re-filtering by
  // whether `label` contains the typed text on top of that would silently
  // discard every real match whose label happens not to contain what was
  // typed — found live: `GlobalSearch`'s "EntityType: <ulid>" labels never
  // contain the query text, so every server search rendered zero results.
  // Only a caller with no `onQueryChange` (a local, already-fully-loaded
  // option list) wants this component's own substring filtering.
  const filtered = !onQueryChange && query
    ? options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase()))
    : options;

  function select(option: ComboboxOption): void {
    onChange(option.value);
    setQuery("");
    setOpen(false);
    setHighlighted(0);
  }

  function optionId(index: number): string {
    return `${listboxId}-option-${index}`;
  }

  return (
    <div className="combobox">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open && filtered[highlighted] ? optionId(highlighted) : undefined}
        aria-label={aria["aria-label"]}
        placeholder={placeholder}
        value={query || value}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          setHighlighted(0);
          onQueryChange?.(e.target.value);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 100)}
        onKeyDown={(e) => {
          if (!open || filtered.length === 0) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHighlighted((i) => Math.min(i + 1, filtered.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHighlighted((i) => Math.max(i - 1, 0));
          } else if (e.key === "Enter") {
            e.preventDefault();
            const option = filtered[Math.min(highlighted, filtered.length - 1)];
            if (option) select(option);
          } else if (e.key === "Escape") {
            setOpen(false);
          }
        }}
      />
      {open && filtered.length > 0 && (
        <ul className="combobox__listbox" id={listboxId} role="listbox">
          {filtered.map((option, index) => (
            <li
              key={option.value}
              id={optionId(index)}
              role="option"
              aria-selected={index === highlighted}
              className="combobox__option"
              onMouseDown={() => select(option)}
            >
              {option.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
