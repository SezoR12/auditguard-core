// Placeholder. Phase 2 wires up Baileys (WhatsApp Web).
const http = require("http");
const PORT = 3001;
http
  .createServer((_, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "baileys-bridge placeholder" }));
  })
  .listen(PORT, () => console.log(`baileys-bridge listening on :${PORT}`));
