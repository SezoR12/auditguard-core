FROM node:26-alpine

WORKDIR /app
RUN npm install -g bun

COPY package.json bun.lock* bunfig.toml* ./
RUN bun install || npm install

COPY . .

EXPOSE 5173
CMD ["bun", "run", "dev", "--host", "0.0.0.0"]
