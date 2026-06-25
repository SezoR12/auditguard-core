import { createFileRoute } from "@tanstack/react-router";
import { RoleDashboard } from "@/components/RoleDashboard";

export const Route = createFileRoute("/manager")({
  head: () => ({ meta: [{ title: "لوحة المدير — AuditCore" }] }),
  component: () => <RoleDashboard expectedRole="manager" title="لوحة المدير" />,
});
