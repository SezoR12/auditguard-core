import { createFileRoute } from "@tanstack/react-router";
import { RoleDashboard } from "@/components/RoleDashboard";

export const Route = createFileRoute("/auditor")({
  head: () => ({ meta: [{ title: "لوحة المدقق — AuditCore" }] }),
  component: () => <RoleDashboard expectedRole="auditor" title="لوحة المدقق" />,
});
