// Something read once and changed elsewhere (another window, another person) is read again when the
// analyst comes back to this window: build order step 18c (D9), the case's strength legend, which
// kept "Composition: standard" after the case's Author switched it to client parity elsewhere.
import { useEffect, useRef } from "react";

/** Calls `onReturn` whenever the window is focused again or its tab is shown again. */
export function useOnReturn(onReturn: () => void): void {
  const latest = useRef(onReturn);
  latest.current = onReturn;
  useEffect(() => {
    const focused = () => latest.current();
    const shown = () => {
      if (document.visibilityState === "visible") latest.current();
    };
    window.addEventListener("focus", focused);
    document.addEventListener("visibilitychange", shown);
    return () => {
      window.removeEventListener("focus", focused);
      document.removeEventListener("visibilitychange", shown);
    };
  }, []);
}
