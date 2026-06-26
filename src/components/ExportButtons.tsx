import { useState } from "react";
import { api } from "@/lib/api";

/** Reusable [تصدير Excel] [تصدير PDF] [تصدير صورة] buttons for owner reports. */
export function ExportButtons({ outputType }: { outputType: string }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(format: string) {
    setBusy(format);
    setError(null);
    try {
      const res = await api.createExport({ output_type: outputType, format });
      // Trigger the browser download via the signed URL.
      const url = api.downloadUrl(res.download_url);
      const a = document.createElement("a");
      a.href = url;
      a.download = res.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      setError(e instanceof Error ? e.message : "تعذّر التصدير");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <button
        onClick={() => void run("excel")}
        disabled={busy !== null}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
      >
        {busy === "excel" ? "..." : "تصدير Excel"}
      </button>
      <button
        onClick={() => void run("pdf")}
        disabled={busy !== null}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
      >
        {busy === "pdf" ? "..." : "تصدير PDF"}
      </button>
      <button
        onClick={() => void run("png")}
        disabled={busy !== null}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-xs hover:bg-accent disabled:opacity-50"
      >
        {busy === "png" ? "..." : "تصدير صورة"}
      </button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}
