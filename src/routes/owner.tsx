import { createFileRoute } from "@tanstack/react-router";
import { RoleDashboard } from "@/components/RoleDashboard";

export const Route = createFileRoute("/owner")({
  head: () => ({ meta: [{ title: "لوحة المالك — AuditCore" }] }),
  component: () => <RoleDashboard expectedRole="owner" title="لوحة المالك" />,
});
