import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CurrentUser } from "@/lib/api";

// --- Mocks ---------------------------------------------------------------
const getSession = vi.fn();
const setSession = vi.fn();
const signInWithPassword = vi.fn();
const signOut = vi.fn();
const onAuthStateChange = vi.fn((_cb?: unknown) => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}));
vi.mock("@/lib/supabaseClient", () => ({
  supabaseAuditcore: {
    auth: {
      getSession: () => getSession(),
      setSession: (...a: unknown[]) => setSession(...a),
      signInWithPassword: (...a: unknown[]) => signInWithPassword(...a),
      signOut: () => signOut(),
      onAuthStateChange: (cb: unknown) => onAuthStateChange(cb),
    },
  },
}));

const apiLogin = vi.fn();
const apiMe = vi.fn();
const apiLogout = vi.fn();
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      login: (...a: unknown[]) => apiLogin(...a),
      me: () => apiMe(),
      logout: () => apiLogout(),
    },
  };
});

const loadProfileFromSupabase = vi.fn();
vi.mock("@/lib/authPreview", async () => {
  const actual = await vi.importActual<typeof import("@/lib/authPreview")>("@/lib/authPreview");
  return {
    ...actual,
    loadProfileFromSupabase: () => loadProfileFromSupabase(),
  };
});

import { AuthProvider, useAuth } from "./useAuth";

const USER: CurrentUser = {
  id: "u1",
  email: "owner@auditcore.local",
  full_name: "المالك",
  role: "owner",
  company_id: "c1",
  branch_id: null,
  is_active: true,
};

// Tiny consumer to exercise the hook.
function Harness() {
  const { user, loading, login, logout } = useAuth();
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="user">{user ? user.role : "none"}</span>
      <button onClick={() => void login("e", "p").catch(() => {})}>do-login</button>
      <button onClick={() => void logout()}>do-logout</button>
    </div>
  );
}

function renderAuth() {
  return render(
    <AuthProvider>
      <Harness />
    </AuthProvider>,
  );
}

describe("useAuth", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSession.mockResolvedValue({ data: { session: null } }); // no session at boot
    setSession.mockResolvedValue({ data: {}, error: null });
    signOut.mockResolvedValue({ error: null });
    apiLogout.mockResolvedValue({ revoked: true });
  });

  it("starts unauthenticated after the initial session check", async () => {
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    expect(screen.getByTestId("user").textContent).toBe("none");
  });

  it("login success sets the user from /auth/me", async () => {
    apiLogin.mockResolvedValue({ access_token: "a", refresh_token: "r" });
    apiMe.mockResolvedValue(USER);
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    await userEvent.click(screen.getByText("do-login"));
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("owner"));
    expect(setSession).toHaveBeenCalledWith({ access_token: "a", refresh_token: "r" });
  });

  it("falls back to Supabase profile when /auth/me is unreachable", async () => {
    apiLogin.mockResolvedValue({ access_token: "a", refresh_token: "r" });
    apiMe.mockRejectedValue(new Error("backend down"));
    loadProfileFromSupabase.mockResolvedValue({ ...USER, role: "manager" });
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    await userEvent.click(screen.getByText("do-login"));
    await waitFor(() => expect(screen.getByTestId("user").textContent).toBe("manager"));
    expect(loadProfileFromSupabase).toHaveBeenCalled();
  });

  it("login failure (bad credentials) leaves the user unauthenticated", async () => {
    // Proxy returns a 401 ApiError → surfaced as-is, no fallback.
    const { ApiError } = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    apiLogin.mockRejectedValue(new ApiError({ status: 401, path: "/auth/login", detail: "غير صحيحة" }));
    renderAuth();
    await waitFor(() => expect(screen.getByTestId("loading").textContent).toBe("false"));
    await userEvent.click(screen.getByText("do-login"));
    await waitFor(() => expect(apiLogin).toHaveBeenCalled());
    expect(screen.getByTestId("user").textContent).toBe("none");
    expect(signInWithPassword).not.toHaveBeenCalled(); // no fallback on real 401
  });

  it("logs the user out after the idle timeout fires", async () => {
    // Fake timers from the start so the idle timer is created on the fake clock.
    vi.useFakeTimers();
    try {
      apiLogin.mockResolvedValue({ access_token: "a", refresh_token: "r" });
      apiMe.mockResolvedValue(USER);
      renderAuth();

      // Flush the async login + initial session check by interleaving pending
      // timers with microtask drains (no real-timer waitFor under fake timers).
      const flush = async () => {
        for (let i = 0; i < 10; i++) {
          await act(async () => {
            await Promise.resolve();
            vi.advanceTimersByTime(0);
          });
        }
      };

      await flush();
      fireEvent.click(screen.getByText("do-login"));
      await flush();
      expect(screen.getByTestId("user").textContent).toBe("owner");

      // Jump past the 15-minute idle window → triggers logout().
      await act(async () => {
        vi.advanceTimersByTime(15 * 60 * 1000 + 1000);
      });
      await flush();

      expect(apiLogout).toHaveBeenCalled();
      expect(screen.getByTestId("user").textContent).toBe("none");
    } finally {
      vi.useRealTimers();
    }
  });
});
