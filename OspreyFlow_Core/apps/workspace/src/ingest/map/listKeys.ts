// The keys of the Map's element lists (links and entities): ArrowDown and ArrowUp move focus to the
// next and previous button, Home and End to the first and last, and focus stays at an end of the
// list rather than leaving it. Tab, Enter and Space are the buttons' own.
import type { KeyboardEvent } from "react";

export function moveFocusInList(event: KeyboardEvent<HTMLElement>): void {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
  const buttons = Array.from(event.currentTarget.querySelectorAll("button"));
  const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
  if (at === -1) return;
  event.preventDefault();
  const target =
    event.key === "Home"
      ? 0
      : event.key === "End"
        ? buttons.length - 1
        : Math.min(Math.max(at + (event.key === "ArrowDown" ? 1 : -1), 0), buttons.length - 1);
  buttons[target]?.focus();
}
