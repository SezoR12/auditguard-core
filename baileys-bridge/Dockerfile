FROM node:20-alpine

WORKDIR /app

# Placeholder for Phase 2 WhatsApp Web (Baileys) integration.
COPY package.json ./
RUN npm install --omit=dev || true

COPY . .

EXPOSE 3001
CMD ["node", "index.js"]
