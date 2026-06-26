import { useEffect, type ReactNode } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAuth, roleHomePath } from "@/hooks/useAuth";
import type { CurrentUser } from "@/lib/api";

type Role = CurrentUser["role"];

/**
 * Route guard. Blocks rendering of a protected page until the auth state is
 * resolved (i.e. /auth/me has returned), then:
 *   - sends unauthenticated visitors to /login, and
 *   - sends authenticated users whose role is not in `allow` to THEIR own role
 *     dashboard (roleHomePath) instead of showing a dead-end error panel.
 *
 * While loading (or during the redirect tick) a neutral splash is shown so no
 * protected content ever flashes for the wrong user.
 */
export function RequireRole({
  allow,
  children,
}: {
  allow: Role[];
  children: ReactNode;
}) {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  const allowed = !!user && allow.includes(user.role);

  useEffect(() => {
    if (loading) return; // wait for /auth/me
    if (!user) {
      void navigate({ to: "/login" });
      return;
    }
    if (!allow.includes(user.role)) {
      void navigate({ to: roleHomePath(user.role) });
    }
  }, [user, loading, allow, navigate]);

  if (loading || !user || !allowed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background" dir="rtl">
        <p className="text-muted-foreground">جارٍ التحقق من الصلاحيات...</p>
      </div>
    );
  }

  return <>{children}</>;
}
