import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { NotificationItem } from "@/lib/api";

// --- Mocks ---------------------------------------------------------------
const navigateMock = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigateMock,
}));

const notifications = vi.fn();
const markNotificationRead = vi.fn();
const markAllNotificationsRead = vi.fn();
vi.mock("@/lib/api", () => ({
  api: {
    notifications: () => notifications(),
    markNotificationRead: (id: string) => markNotificationRead(id),
    markAllNotificationsRead: () => markAllNotificationsRead(),
  },
}));
vi.mock("@/lib/format", () => ({ formatDate: () => "2026-01-01" }));

import { NotificationBell } from "./NotificationBell";

function item(over: Partial<NotificationItem> = {}): NotificationItem {
  return {
    id: "n1",
    title: "تنبيه",
    body: "نص",
    severity: "high",
    is_read: false,
    created_at: "2026-01-01T00:00:00Z",
    link: {},
    ...over,
  } as NotificationItem;
}

describe("NotificationBell", () => {
  beforeEach(() => {
    navigateMock.mockReset();
    notifications.mockReset();
    markNotificationRead.mockReset();
    markAllNotificationsRead.mockReset();
    markNotificationRead.mockResolvedValue(undefined);
    markAllNotificationsRead.mockResolvedValue(undefined);
  });

  it("shows the unread badge count", async () => {
    notifications.mockResolvedValue({ items: [item()], unread_count: 3 });
    render(<NotificationBell />);
    await waitFor(() => expect(screen.getByText("3")).toBeInTheDocument());
  });

  it("caps the badge at 99+", async () => {
    notifications.mockResolvedValue({ items: [], unread_count: 250 });
    render(<NotificationBell />);
    await waitFor(() => expect(screen.getByText("99+")).toBeInTheDocument());
  });

  it("renders no badge when there are zero unread", async () => {
    notifications.mockResolvedValue({ items: [], unread_count: 0 });
    render(<NotificationBell />);
    await waitFor(() => expect(notifications).toHaveBeenCalled());
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("marks one as read and navigates on item click", async () => {
    notifications
      .mockResolvedValueOnce({ items: [item({ id: "n9" })], unread_count: 1 })
      .mockResolvedValue({ items: [item({ id: "n9", is_read: true })], unread_count: 0 });
    render(<NotificationBell />);
    await userEvent.click(await screen.findByLabelText("التنبيهات")); // open dropdown
    await userEvent.click(await screen.findByText("نص"));
    await waitFor(() => expect(markNotificationRead).toHaveBeenCalledWith("n9"));
    expect(navigateMock).toHaveBeenCalled();
  });

  it("marks all as read", async () => {
    notifications.mockResolvedValue({ items: [item()], unread_count: 2 });
    render(<NotificationBell />);
    await userEvent.click(await screen.findByLabelText("التنبيهات")); // open
    await userEvent.click(await screen.findByText("تعليم الكل كمقروء"));
    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalled());
  });
});
