// AuditCore — Baileys WhatsApp bridge.
//
// Responsibilities:
//   * Maintain a WhatsApp Web session (multi-file auth in /data/whatsapp_auth).
//   * Show a QR code on first run for the Owner to scan.
//   * Expose POST /send-message {to, message} for the backend to dispatch alerts.
//   * Expose GET /status and GET /qr for diagnostics.
//
// AUTH: /send-message and /qr require the X-Bridge-Token header to match
// WHATSAPP_BRIDGE_TOKEN. If that env var is unset the bridge logs a CRITICAL
// warning and those endpoints return 503 (fail-closed) so it can never run
// unauthenticated by accident. Generate the token in install.sh/setup.sh.
//
// The session survives container restarts because the auth folder lives on a
// persistent volume.

import pino from "pino";
import qrcodeTerminal from "qrcode-terminal";
import QRCode from "qrcode";
import {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
} from "@whiskeysockets/baileys";

import { createApp } from "./app.js";

const PORT = process.env.PORT || 3001;
const AUTH_DIR = process.env.WHATSAPP_AUTH_DIR || "/data/whatsapp_auth";
const BRIDGE_TOKEN = process.env.WHATSAPP_BRIDGE_TOKEN || "";
const logger = pino({ level: process.env.LOG_LEVEL || "info" });

if (!BRIDGE_TOKEN) {
  logger.error(
    "CRITICAL: WHATSAPP_BRIDGE_TOKEN is not set — /send-message and /qr will " +
      "reject all requests (503) until it is configured. See SECURITY.md.",
  );
}

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

const app = createApp({
  token: BRIDGE_TOKEN,
  getState: () => connectionState,
  getQR: () => lastQR,
  makeQrDataUrl: (qr) => QRCode.toDataURL(qr),
  sendMessage: (jid, text) => sock.sendMessage(jid, { text }),
  logger,
});

app.listen(PORT, () => logger.info(`baileys-bridge listening on :${PORT}`));

startSock().catch((e) => {
  logger.error(e, "failed to start WhatsApp socket");
});
