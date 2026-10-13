import { useEffect, useState } from "react";

import { IconButton } from "../design/primitives/IconButton";
import { applyTheme, currentTheme, onThemeChange, storeTheme, type Theme } from "./theme";

/** The light / dark switch (ADR-070, ADR-073): an icon of its own in every top bar (ADR-115
 * Amendment 1, which moved it out of the account menu), and a worded button where there is no bar. One worded button, drawn like its neighbours. Its words name the
 * theme a press switches to: Light while the page is dark, Dark once it is light. The choice is kept in this browser only. A real
 * button, so a keyboard reaches it with Tab and presses it with Enter or Space. */
export function ThemeToggle({
  className = "btn",
  variant = "worded",
}: { className?: string; variant?: "worded" | "icon" } = {}) {
  const [theme, setTheme] = useState<Theme>(currentTheme());
  useEffect(() => onThemeChange(setTheme), []);
  const next: Theme = theme === "light" ? "dark" : "light";
  const label = `Switch to the ${next} theme`;
  const press = () => {
    storeTheme(next);
    applyTheme(next);
  };
  // ADR-115 Amendment 1: in the top bar, an icon of its own; its name and tooltip say the theme.
  if (variant === "icon") {
    return (
      <IconButton label={label} type="button" onClick={press}>
        <span aria-hidden="true">{next === "light" ? "☀" : "☾"}</span>
      </IconButton>
    );
  }
  return (
    <button
      type="button"
      className={className}
      aria-label={label}
      title={label}
      onClick={press}
    >
      <span aria-hidden="true">{next === "light" ? "☀" : "☾"}</span> {next === "light" ? "Light" : "Dark"}
    </button>
  );
}
