import type { ButtonHTMLAttributes, ReactNode } from "react";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  pressed?: boolean;
  children: ReactNode;
}

export function IconButton({ label, pressed, className, children, ...rest }: IconButtonProps) {
  return (
    <button
      className={["icon-btn", className].filter(Boolean).join(" ")}
      aria-label={label}
      aria-pressed={pressed}
      title={label}
      {...rest}
    >
      {children}
    </button>
  );
}
