FROM node:20-bookworm-slim

WORKDIR /app

# Baileys is pure JS/WebSocket (no puppeteer/Chromium needed). Keep image slim.
COPY package.json ./
RUN npm install --omit=dev

COPY . .

# Persistent auth dir on the shared /data volume.
RUN mkdir -p /data/whatsapp_auth

EXPOSE 3001
CMD ["node", "index.js"]
