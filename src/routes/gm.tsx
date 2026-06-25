import { createFileRoute } from "@tanstack/react-router";
import { RoleDashboard } from "@/components/RoleDashboard";

export const Route = createFileRoute("/gm")({
  head: () => ({ meta: [{ title: "لوحة المدير العام — AuditCore" }] }),
  component: () => <RoleDashboard expectedRole="gm" title="لوحة المدير العام" />,
});
