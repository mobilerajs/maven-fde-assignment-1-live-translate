# Build context = repo root (see fly.gateway.toml) — bundles widget/ so the
# gateway's WIDGET_PATH (../../widget/translation-widget.js) resolves.
FROM node:22-slim
WORKDIR /app/backend/gateway-node
COPY backend/gateway-node/package*.json ./
RUN npm install --omit=dev
COPY backend/gateway-node/ ./
COPY widget/ /app/widget/
EXPOSE 8787
CMD ["node", "server.js"]
