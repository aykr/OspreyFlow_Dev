import type { ComponentPropsWithRef } from "react";

// `ref` is an ordinary prop in React 19, passed through to the `<input>` (the Rules form puts the
// keyboard on its name field once a template fills it).
export function Input({ className, ...rest }: ComponentPropsWithRef<"input">) {
  return <input className={["input", className].filter(Boolean).join(" ")} {...rest} />;
}
