// Tests for the Baileys bridge HTTP auth (no real WhatsApp socket).
// Run: node --test   (Node 20+; uses the built-in test runner + global fetch)

import { test } from "node:test";
import assert from "node:assert/strict";
import { createApp, jidFor } from "../app.js";

const TOKEN = "test-bridge-token-0123456789";

function fakeDeps(overrides = {}) {
  return {
    token: TOKEN,
    getState: () => "open",
    getQR: () => "QR-PAYLOAD",
    makeQrDataUrl: async () => "data:image/png;base64,AAAA",
    sendMessage: async () => {},
    logger: { error: () => {} },
    ...overrides,
  };
}

async function withServer(app, fn) {
  const server = app.listen(0);
  await new Promise((r) => server.once("listening", r));
  const { port } = server.address();
  try {
    return await fn(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((r) => server.close(r));
  }
}

test("jidFor normalizes bare numbers and passes JIDs through", () => {
  assert.equal(jidFor("9647701234567"), "9647701234567@s.whatsapp.net");
  assert.equal(jidFor("+964 770 123 4567"), "9647701234567@s.whatsapp.net");
  assert.equal(jidFor("123@g.us"), "123@g.us");
});

test("/status is open (no token required)", async () => {
  await withServer(createApp(fakeDeps()), async (base) => {
    const r = await fetch(`${base}/status`);
    assert.equal(r.status, 200);
    const body = await r.json();
    assert.equal(body.ok, true);
    assert.equal(body.state, "open");
  });
});

test("/send-message without token => 401", async () => {
  await withServer(createApp(fakeDeps()), async (base) => {
    const r = await fetch(`${base}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ to: "964770", message: "hi" }),
    });
    assert.equal(r.status, 401);
    assert.equal((await r.json()).reason, "unauthorized");
  });
});

test("/send-message with wrong token => 401", async () => {
  await withServer(createApp(fakeDeps()), async (base) => {
    const r = await fetch(`${base}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Bridge-Token": "nope" },
      body: JSON.stringify({ to: "964770", message: "hi" }),
    });
    assert.equal(r.status, 401);
  });
});

test("/send-message with correct token => 200 and calls sendMessage", async () => {
  let called = null;
  const deps = fakeDeps({ sendMessage: async (jid, text) => { called = { jid, text }; } });
  await withServer(createApp(deps), async (base) => {
    const r = await fetch(`${base}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Bridge-Token": TOKEN },
      body: JSON.stringify({ to: "9647701234567", message: "مرحبا" }),
    });
    assert.equal(r.status, 200);
    assert.equal((await r.json()).ok, true);
    assert.deepEqual(called, { jid: "9647701234567@s.whatsapp.net", text: "مرحبا" });
  });
});

test("/send-message returns 503 when not connected (even with valid token)", async () => {
  const deps = fakeDeps({ getState: () => "connecting" });
  await withServer(createApp(deps), async (base) => {
    const r = await fetch(`${base}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Bridge-Token": TOKEN },
      body: JSON.stringify({ to: "964770", message: "hi" }),
    });
    assert.equal(r.status, 503);
    assert.equal((await r.json()).reason, "whatsapp_not_connected");
  });
});

test("/qr requires the token", async () => {
  await withServer(createApp(fakeDeps()), async (base) => {
    const noAuth = await fetch(`${base}/qr`);
    assert.equal(noAuth.status, 401);
    const ok = await fetch(`${base}/qr`, { headers: { "X-Bridge-Token": TOKEN } });
    assert.equal(ok.status, 200);
    assert.equal((await ok.json()).ok, true);
  });
});

test("protected routes fail closed (503) when no token configured", async () => {
  const deps = fakeDeps({ token: "" });
  await withServer(createApp(deps), async (base) => {
    const send = await fetch(`${base}/send-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Bridge-Token": "anything" },
      body: JSON.stringify({ to: "964770", message: "hi" }),
    });
    assert.equal(send.status, 503);
    assert.equal((await send.json()).reason, "bridge_auth_not_configured");
    const qr = await fetch(`${base}/qr`, { headers: { "X-Bridge-Token": "anything" } });
    assert.equal(qr.status, 503);
  });
});
