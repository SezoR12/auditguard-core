import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import type { CurrentUser } from "@/lib/api";

// --- Mocks ---------------------------------------------------------------
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

let authState: { user: CurrentUser | null; loading: boolean };
vi.mock("@/hooks/useAuth", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/useAuth")>("@/hooks/useAuth");
  return {
    ...actual,
    useAuth: () => authState,
  };
});

import { RequireRole } from "./RequireRole";

function makeUser(role: CurrentUser["role"]): CurrentUser {
  return {
    id: "u1",
    email: "x@y.local",
    full_name: "Test",
    role,
    company_id: "c1",
    branch_id: null,
    is_active: true,
  };
}

describe("RequireRole", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    authState = { user: null, loading: true };
  });

  it("shows the loading splash while auth is resolving (no nav, no children)", () => {
    authState = { user: null, loading: true };
    render(
      <RequireRole allow={["owner"]}>
        <div>secret</div>
      </RequireRole>,
    );
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(screen.getByText(/جارٍ التحقق/)).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });

  it("redirects an unauthenticated user to /login", async () => {
    authState = { user: null, loading: false };
    render(
      <RequireRole allow={["owner"]}>
        <div>secret</div>
      </RequireRole>,
    );
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/login" }));
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
  });

  it("redirects a wrong-role user to their own role dashboard", async () => {
    authState = { user: makeUser("auditor"), loading: false };
    render(
      <RequireRole allow={["owner", "gm"]}>
        <div>owner-only</div>
      </RequireRole>,
    );
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith({ to: "/auditor" }));
    expect(screen.queryByText("owner-only")).not.toBeInTheDocument();
  });

  it("renders children for an allowed role and does not navigate", async () => {
    authState = { user: makeUser("owner"), loading: false };
    render(
      <RequireRole allow={["owner", "gm"]}>
        <div>owner-only</div>
      </RequireRole>,
    );
    expect(screen.getByText("owner-only")).toBeInTheDocument();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
