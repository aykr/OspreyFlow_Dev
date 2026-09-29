import type { ButtonHTMLAttributes } from "react";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary";
}

export function Button({ variant = "default", className, ...rest }: ButtonProps) {
  const classes = ["btn", variant === "primary" ? "btn--primary" : "", className]
    .filter(Boolean)
    .join(" ");
  return <button className={classes} {...rest} />;
}
