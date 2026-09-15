import type { ReactNode } from "react";
import { useState } from "react";

export interface TooltipProps {
  text: string;
  children: ReactNode;
}

export function Tooltip({ text, children }: TooltipProps) {
  const [visible, setVisible] = useState(false);
  return (
    <span
      style={{ position: "relative", display: "inline-block" }}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
    >
      {children}
      {visible && (
        <span
          className="tooltip"
          role="tooltip"
          style={{ position: "absolute", bottom: "100%", left: "50%", transform: "translateX(-50%)" }}
        >
          {text}
        </span>
      )}
    </span>
  );
}
