import { useEffect, useState } from "react";

import { applyTheme, currentTheme, onThemeChange, storeTheme, type Theme } from "./theme";

/** The light / dark switch in the top bar (ADR-070). One worded button, drawn like its neighbours: pressed (brass) means light. The choice
 * is kept in this browser only. A real button, so a keyboard reaches it with Tab and presses it
 * with Enter or Space. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(currentTheme());
  useEffect(() => onThemeChange(setTheme), []);
  const light = theme === "light";
  return (
    <button
      type="button"
      className="btn"
      aria-label="Light theme"
      aria-pressed={light}
      title={light ? "Switch to the dark theme" : "Switch to the light theme"}
      onClick={() => {
        const next: Theme = light ? "dark" : "light";
        storeTheme(next);
        applyTheme(next);
      }}
    >
      <span aria-hidden="true">☀</span> Light
    </button>
  );
}
