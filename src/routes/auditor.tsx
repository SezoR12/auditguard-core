import { createFileRoute, Link } from "@tanstack/react-router";
import { RoleDashboard } from "@/components/RoleDashboard";

export const Route = createFileRoute("/auditor")({
  head: () => ({ meta: [{ title: "لوحة المدقق — AuditCore" }] }),
  component: () => (
    <RoleDashboard expectedRole="auditor" title="لوحة المدقق">
      <div className="text-right">
        <p className="text-sm text-muted-foreground">
          من هنا يمكنك رفع المستندات لتدقيقها ومتابعة حالتها.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            to="/auditor/upload"
            className="inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            رفع مستند جديد
          </Link>
          <Link
            to="/auditor/certify"
            className="inline-block rounded-md border border-input bg-background px-4 py-2 text-sm font-medium hover:bg-accent"
          >
            اعتماد المستندات
          </Link>
        </div>
      </div>
    </RoleDashboard>
  ),
});
