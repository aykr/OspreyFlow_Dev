import type { MatchMode, SearchOptions } from "./searchOptions";
import { DEFAULT_SEARCH_OPTIONS } from "./searchOptions";

export interface SearchFiltersProps {
  options: SearchOptions;
  entityTypes: readonly string[];
  onChange: (options: SearchOptions) => void;
}

const MODES: { value: MatchMode; label: string }[] = [
  { value: "starts_with", label: "Starts with" },
  { value: "contains", label: "Contains" },
  { value: "exact", label: "Exact" },
];

/** The panel behind the search box's Filters button (ADR-061). It only edits the options; the box
 * decides what to ask with them. */
export function SearchFilters({ options, entityTypes, onChange }: SearchFiltersProps) {
  const set = (patch: Partial<SearchOptions>) => onChange({ ...options, ...patch });
  return (
    <div
      className="search-filters"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--sp-6)",
        padding: "var(--sp-8)",
        border: "1px solid var(--border)",
        background: "var(--surface-raised, var(--surface))",
      }}
    >
      <label>
        <input
          type="checkbox"
          checked={options.ignoreCase}
          onChange={(e) => set({ ignoreCase: e.target.checked })}
        />{" "}
        Ignore case
      </label>
      <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
        <legend>Match</legend>
        {MODES.map((mode) => (
          <label key={mode.value} style={{ marginRight: "var(--sp-8)" }}>
            <input
              type="radio"
              name="search-match-mode"
              checked={options.mode === mode.value}
              onChange={() => set({ mode: mode.value })}
            />{" "}
            {mode.label}
          </label>
        ))}
      </fieldset>
      {entityTypes.length > 0 && (
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <legend>Entity types</legend>
          {entityTypes.map((type) => (
            <label key={type} style={{ display: "block" }}>
              <input
                type="checkbox"
                checked={options.types.includes(type)}
                onChange={(e) =>
                  set({
                    types: e.target.checked
                      ? [...options.types, type]
                      : options.types.filter((t) => t !== type),
                  })
                }
              />{" "}
              {type}
            </label>
          ))}
          <small>None ticked searches every type.</small>
        </fieldset>
      )}
      <label>
        <input
          type="checkbox"
          checked={options.onScreenOnly}
          onChange={(e) => set({ onScreenOnly: e.target.checked })}
        />{" "}
        Only nodes on screen
      </label>
      <button type="button" className="radial-menu__item" onClick={() => onChange(DEFAULT_SEARCH_OPTIONS)}>
        Reset filters
      </button>
    </div>
  );
}
