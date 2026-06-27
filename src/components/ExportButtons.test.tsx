import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// --- Mocks ---------------------------------------------------------------
const createExport = vi.fn();
const downloadUrl = vi.fn((p: string) => `http://api${p}`);
vi.mock("@/lib/api", () => ({
  api: {
    createExport: (...args: unknown[]) => createExport(...args),
    downloadUrl: (p: string) => downloadUrl(p),
  },
}));

import { ExportButtons } from "./ExportButtons";

describe("ExportButtons", () => {
  beforeEach(() => {
    createExport.mockReset();
    downloadUrl.mockClear();
    createExport.mockResolvedValue({ download_url: "/exports/abc", filename: "report.xlsx" });
  });

  it("renders the three format buttons", () => {
    render(<ExportButtons outputType="dashboard" />);
    expect(screen.getByText("تصدير Excel")).toBeInTheDocument();
    expect(screen.getByText("تصدير PDF")).toBeInTheDocument();
    expect(screen.getByText("تصدير صورة")).toBeInTheDocument();
  });

  it.each([
    ["تصدير Excel", "excel"],
    ["تصدير PDF", "pdf"],
    ["تصدير صورة", "png"],
  ])("calls createExport with the right format for %s", async (label, format) => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<ExportButtons outputType="dashboard" />);
    await userEvent.click(screen.getByText(label));
    await waitFor(() =>
      expect(createExport).toHaveBeenCalledWith({ output_type: "dashboard", format }),
    );
    // Builds the signed URL and triggers a browser download.
    expect(downloadUrl).toHaveBeenCalledWith("/exports/abc");
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();
  });

  it("shows an error message when the export fails", async () => {
    createExport.mockRejectedValueOnce(new Error("بوم"));
    render(<ExportButtons outputType="dashboard" />);
    await userEvent.click(screen.getByText("تصدير PDF"));
    await waitFor(() => expect(screen.getByText("بوم")).toBeInTheDocument());
  });
});
