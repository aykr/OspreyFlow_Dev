// @vitest-environment jsdom
// ADR-115 decision 2 (E1): the signed-out page shows the deployment's marking above everything, as
// every other surface does; where no deployment names one (the development server) there is no strip.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SignInScreen } from "./SignInScreen";

afterEach(cleanup);

describe("the signed-out page's marking", () => {
  it("is the deployment's", () => {
    render(<SignInScreen marking="OFFICIAL" onSignIn={() => undefined} />);
    expect(screen.getByRole("note", { name: "Protective marking" }).textContent).toBe("OFFICIAL");
  });

  it("is absent where none is known", () => {
    render(<SignInScreen onSignIn={() => undefined} />);
    expect(screen.queryByRole("note", { name: "Protective marking" })).toBeNull();
  });
});
