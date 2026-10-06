import { useEffect, useState } from "react";

import { applyTheme, currentTheme, onThemeChange, storeTheme, type Theme } from "./theme";

/** The light / dark switch (ADR-070, ADR-073): an item of the account menu (ADR-097 step 3), and a
 * button of its own in the bar only where there is no account menu (the local development bypass). One worded button, drawn like its neighbours. Its words name the
 * theme a press switches to: Light while the page is dark, Dark once it is light. The choice is kept in this browser only. A real
 * button, so a keyboard reaches it with Tab and presses it with Enter or Space. */
export function ThemeToggle({ className = "btn" }: { className?: string } = {}) {
  const [theme, setTheme] = useState<Theme>(currentTheme());
  useEffect(() => onThemeChange(setTheme), []);
  const next: Theme = theme === "light" ? "dark" : "light";
  const label = `Switch to the ${next} theme`;
  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      title={label}
      onClick={() => {
        storeTheme(next);
        applyTheme(next);
      }}
    >
      <span aria-hidden="true">{next === "light" ? "☀" : "☾"}</span> {next === "light" ? "Light" : "Dark"}
    </button>
  );
}
