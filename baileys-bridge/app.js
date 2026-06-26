// AuditCore — Baileys bridge HTTP app (testable, transport-only).
//
// Extracted from index.js so the routing + AUTH can be unit-tested without
// starting a real WhatsApp socket. index.js wires the real Baileys deps in.
//
// AUTH: /send-message and /qr require a shared secret in the `X-Bridge-Token`
// header matching WHATSAPP_BRIDGE_TOKEN. Without a configured token the bridge
// refuses those endpoints (503) so it can never run unauthenticated by mistake.
// /status is intentionally open (no sensitive data — just connection state).

import express from "express";

export function jidFor(to) {
  // Accept bare numbers or full JIDs.
  if (String(to).includes("@")) return String(to);
  const digits = String(to).replace(/\D/g, "");
  return `${digits}@s.whatsapp.net`;
}

/**
 * Build the Express app.
 *
 * deps:
 *   token       - required shared secret (string); falsy => protected routes 503
 *   getState()  - () => "disconnected" | "connecting" | "open"
 *   getQR()     - () => string | null   (raw QR payload, or null if linked)
 *   makeQrDataUrl(qr) - async (qr) => data URL string
 *   sendMessage(jid, text) - async; throws on failure
 *   logger      - optional pino-like logger
 */
export function createApp(deps) {
  const {
    token,
    getState,
    getQR,
    makeQrDataUrl,
    sendMessage,
    logger = console,
  } = deps;

  const app = express();
  app.use(express.json());

  // Constant-time-ish comparison to avoid trivial timing leaks.
  function tokenMatches(provided) {
    if (!token) return false; // no token configured => never authenticated
    if (typeof provided !== "string" || provided.length !== token.length) return false;
    let diff = 0;
    for (let i = 0; i < token.length; i++) {
      diff |= provided.charCodeAt(i) ^ token.charCodeAt(i);
    }
    return diff === 0;
  }

  // Auth gate for protected routes.
  function requireToken(req, res, next) {
    if (!token) {
      return res.status(503).json({
        ok: false,
        reason: "bridge_auth_not_configured",
        hint: "Set WHATSAPP_BRIDGE_TOKEN in .env (see SECURITY.md).",
      });
    }
    const provided = req.get("X-Bridge-Token");
    if (!tokenMatches(provided)) {
      return res.status(401).json({ ok: false, reason: "unauthorized" });
    }
    return next();
  }

  // Open diagnostics — no sensitive payload, just liveness/connection state.
  app.get("/status", (_req, res) => {
    res.json({ ok: true, state: getState(), hasQR: Boolean(getQR()) });
  });

  // QR is sensitive (scanning it links the account) => protected.
  app.get("/qr", requireToken, async (_req, res) => {
    const qr = getQR();
    if (!qr) {
      return res.status(404).json({ ok: false, reason: "no_pending_qr", state: getState() });
    }
    try {
      const dataUrl = await makeQrDataUrl(qr);
      res.json({ ok: true, qr: dataUrl });
    } catch (e) {
      res.status(500).json({ ok: false, error: String(e) });
    }
  });

  app.post("/send-message", requireToken, async (req, res) => {
    const { to, message } = req.body || {};
    if (!to || !message) {
      return res.status(400).json({ ok: false, reason: "missing_to_or_message" });
    }
    if (getState() !== "open") {
      // Tell the backend we're not ready so it queues for retry.
      return res.status(503).json({ ok: false, reason: "whatsapp_not_connected", state: getState() });
    }
    try {
      await sendMessage(jidFor(to), String(message));
      res.json({ ok: true });
    } catch (e) {
      logger.error?.(e, "send-message failed");
      res.status(502).json({ ok: false, error: String(e) });
    }
  });

  return app;
}
