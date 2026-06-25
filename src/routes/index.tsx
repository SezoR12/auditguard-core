import { createFileRoute, Navigate } from "@tanstack/react-router";
import { useAuth, roleHomePath } from "@/hooks/useAuth";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "AuditCore — منصة التدقيق الذكية" },
      { name: "description", content: "منصة AuditCore لإدارة التدقيق والمخاطر داخل المؤسسة" },
    ],
  }),
  component: Index,
});

function Index() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground">جارٍ التحميل...</p>
      </div>
    );
  }
  return <Navigate to={user ? roleHomePath(user.role) : "/login"} />;
}
