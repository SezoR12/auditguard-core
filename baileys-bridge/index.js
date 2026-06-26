// AuditCore — Baileys WhatsApp bridge.
//
// Responsibilities:
//   * Maintain a WhatsApp Web session (multi-file auth in /data/whatsapp_auth).
//   * Show a QR code on first run for the Owner to scan.
//   * Expose POST /send-message {to, message} for the backend to dispatch alerts.
//   * Expose GET /status and GET /qr for diagnostics.
//
// The session survives container restarts because the auth folder lives on a
// persistent volume.

import express from "express";
import pino from "pino";
import qrcodeTerminal from "qrcode-terminal";
import QRCode from "qrcode";
import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from "@whiskeysockets/baileys";

const PORT = process.env.PORT || 3001;
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || "/data/whatsapp_auth";
const logger = pino({ level: process.env.LOG_LEVEL || "info" });

let sock = null;
let connectionState = "disconnected"; // disconnected | connecting | open
let lastQR = null; // latest QR string (until scanned)

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version } = await fetchLatestBaileysVersion().catch(() => ({ version: undefined }));

  sock = makeWASocket({
    version,
    auth: state,
    logger,
    printQRInTerminal: false, // we handle QR ourselves
    markOnlineOnConnect: false,
  });

  connectionState = "connecting";

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;
    if (qr) {
      lastQR = qr;
      logger.info("Scan this QR with the Owner's WhatsApp (Linked Devices):");
      qrcodeTerminal.generate(qr, { small: true });
    }
    if (connection === "open") {
      connectionState = "open";
      lastQR = null;
      logger.info("WhatsApp connection OPEN");
    } else if (connection === "close") {
      connectionState = "disconnected";
      const code = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = code !== DisconnectReason.loggedOut;
      logger.warn({ code, shouldReconnect }, "WhatsApp connection closed");
      if (shouldReconnect) {
        setTimeout(() => startSock().catch((e) => logger.error(e)), 3000);
      }
    }
  });

  return sock;
}

function jidFor(to) {
  // Accept bare numbers or full JIDs.
  if (to.includes("@")) return to;
  const digits = String(to).replace(/\D/g, "");
  return `${digits}@s.whatsapp.net`;
}

const app = express();
app.use(express.json());

app.get("/status", (_req, res) => {
  res.json({ ok: true, state: connectionState, hasQR: Boolean(lastQR) });
});

// QR as a PNG data URL (for an admin UI to display) or 404 if already linked.
app.get("/qr", async (_req, res) => {
  if (!lastQR) {
    return res.status(404).json({ ok: false, reason: "no_pending_qr", state: connectionState });
  }
  try {
    const dataUrl = await QRCode.toDataURL(lastQR);
    res.json({ ok: true, qr: dataUrl });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e) });
  }
});

app.post("/send-message", async (req, res) => {
  const { to, message } = req.body || {};
  if (!to || !message) {
    return res.status(400).json({ ok: false, reason: "missing_to_or_message" });
  }
  if (connectionState !== "open" || !sock) {
    // Tell the backend we're not ready so it queues for retry.
    return res.status(503).json({ ok: false, reason: "whatsapp_not_connected", state: connectionState });
  }
  try {
    await sock.sendMessage(jidFor(to), { text: String(message) });
    res.json({ ok: true });
  } catch (e) {
    logger.error(e, "send-message failed");
    res.status(502).json({ ok: false, error: String(e) });
  }
});

app.listen(PORT, () => logger.info(`baileys-bridge listening on :${PORT}`));

startSock().catch((e) => {
  logger.error(e, "failed to start WhatsApp socket");
});
