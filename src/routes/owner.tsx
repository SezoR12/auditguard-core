import { createFileRoute, Link } from "@tanstack/react-router";
import { RoleDashboard } from "@/components/RoleDashboard";

export const Route = createFileRoute("/owner")({
  head: () => ({ meta: [{ title: "لوحة المالك — AuditCore" }] }),
  component: () => (
    <RoleDashboard expectedRole="owner" title="لوحة المالك">
      <div className="text-right">
        <p className="text-sm text-muted-foreground">
          راقب أداء فريق التدقيق ومتابعة المهام والنقاط السلبية.
        </p>
        <Link
          to="/owner/performance"
          className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          أداء المدققين
        </Link>
      </div>
    </RoleDashboard>
  ),
});
