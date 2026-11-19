import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

const loginWithGoogle = vi.fn(async () => undefined);

vi.mock("../components/AuthProvider", () => ({
  useAuth: () => ({
    loginWithGoogle,
  }),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    loginWithGoogle.mockClear();
    sessionStorage.clear();
  });

  it("shows the brand icon and a Google-only sign-in control on a dark stage", () => {
    const { container } = render(<LoginPage />);
    expect(screen.getByRole("img", { name: "Finding Alpha" })).toHaveAttribute(
      "src",
      "/icon.png",
    );
    expect(screen.queryByText(/findingalpha/i)).toBeNull();
    expect(screen.queryByText(/sign in with/i)).toBeNull();
    const button = screen.getByRole("button", { name: "Sign in with Google" });
    expect(button.querySelector("svg")).not.toBeNull();
    expect(container.querySelector(".admin-login")).not.toBeNull();
    expect(container.querySelector(".admin-login-card")).toBeNull();
  });

  it("starts Google sign-in when the logo button is pressed", async () => {
    const user = userEvent.setup();
    render(<LoginPage />);
    await user.click(screen.getByRole("button", { name: "Sign in with Google" }));
    expect(loginWithGoogle).toHaveBeenCalledTimes(1);
  });
});
