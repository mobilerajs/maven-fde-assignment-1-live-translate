/*
 * FDE · Assignment 1 · Node Gateway  (the "software backend")
 * ==========================================================
 * This is the ONLY server the browser widget talks to. Its jobs:
 *   - serve the widget file at /widget.js
 *   - accept translation requests from the widget (CORS, validation)
 *   - forward them to the Python AI service
 *   - expose /health and /stats
 *   - log every request
 *
 * It is ~90% done. Find the two `TODO (YOU)` blocks and implement them.
 * Everything else works out of the box.
 *
 * Run:  npm install && npm start      (needs Node 18+ for global fetch)
 */
const express = require("express");
const cors = require("cors");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
require("dotenv").config();

const PORT = process.env.PORT || 8787;
const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";
const WIDGET_PATH = path.join(__dirname, "..", "..", "widget", "translation-widget.js");

const app = express();
const startedAt = Date.now();

// --- middleware ----------------------------------------------------------
app.use(cors()); // dev: allow every origin so the widget works on any page
app.use(express.json({ limit: "1mb" }));

// --- structured logging + request-id tracing ------------------------------
const GATEWAY_LOG = path.join(__dirname, "gateway.log");

function logLine(fields) {
  const line = JSON.stringify({ ts: new Date().toISOString(), ...fields });
  console.log(line);
  fs.appendFile(GATEWAY_LOG, line + "\n", () => {});
}

// request id: reuse inbound X-Request-Id if present, else generate one;
// echoed back to the client and forwarded to the AI service for tracing
app.use((req, res, next) => {
  req.id = req.get("x-request-id") || crypto.randomUUID();
  res.set("X-Request-Id", req.id);
  next();
});

// one structured line per request, AFTER it finishes (final status + elapsed)
app.use((req, res, next) => {
  const t0 = Date.now();
  res.on("finish", () => {
    logLine({
      level: res.statusCode >= 500 ? "ERROR" : res.statusCode >= 400 ? "WARN" : "INFO",
      event: "request",
      requestId: req.id,
      method: req.method,
      url: req.originalUrl,
      status: res.statusCode,
      ms: Date.now() - t0,
    });
  });
  next();
});

// --- serve the widget to the console loader ------------------------------
app.get("/widget.js", (req, res) => {
  res.type("application/javascript");
  res.sendFile(WIDGET_PATH);
});

// --- helper: forward a request to the Python AI service ------------------
async function callAiService(path, body, requestId) {
  const res = await fetch(AI_SERVICE_URL + path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-request-id": requestId || "",
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120000), // a hung AI service must not pin requests forever
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    const err = new Error("AI service " + res.status + (detail ? ": " + detail.slice(0, 300) : ""));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// Only an upstream 400/422 means the request itself was invalid (contract:
// 400). Any other upstream status — 401/403/404 (misconfig), 5xx, timeouts —
// is an upstream failure (contract: 502).
function proxyErrorStatus(err) {
  return err.status === 400 || err.status === 422 ? 400 : 502;
}

// --- routes the widget calls ---------------------------------------------
app.post("/translate", async (req, res) => {
  const { text, target } = req.body || {};
  if (typeof text !== "string") return res.status(400).json({ error: "`text` (string) is required" });
  if (target != null && typeof target !== "string") return res.status(400).json({ error: "`target` must be a string" });
  try {
    const data = await callAiService("/translate", { text, target: target || "es-MX" }, req.id);
    res.json(data);
  } catch (err) {
    res.status(proxyErrorStatus(err)).json({ error: "AI service error: " + err.message });
  }
});

app.post("/translate/batch", async (req, res) => {
  const { texts, target } = req.body || {};
  if (!Array.isArray(texts) || texts.some((t) => typeof t !== "string")) {
    return res.status(400).json({ error: "`texts` (array of strings) is required" });
  }
  if (target != null && typeof target !== "string") return res.status(400).json({ error: "`target` must be a string" });
  try {
    const data = await callAiService("/translate/batch", { texts, target: target || "es-MX" }, req.id);
    res.json(data);
  } catch (err) {
    res.status(proxyErrorStatus(err)).json({ error: "AI service error: " + err.message });
  }
});

app.get("/health", async (req, res) => {
  const uptimeSec = Math.round((Date.now() - startedAt) / 1000);
  let ai = "unreachable";
  try {
    const r = await fetch(AI_SERVICE_URL + "/health", { signal: AbortSignal.timeout(5000) });
    ai = r.ok ? await r.json() : "error";
  } catch (_) {}
  res.json({ status: "ok", gatewayUptimeSec: uptimeSec, aiService: ai });
});

app.get("/stats", async (req, res) => {
  try {
    const r = await fetch(AI_SERVICE_URL + "/stats", { signal: AbortSignal.timeout(10000) });
    res.json(await r.json());
  } catch (err) {
    res.status(502).json({ error: "AI service error: " + err.message });
  }
});

app.listen(PORT, () => {
  console.log(`FDE gateway on http://localhost:${PORT}  →  AI service ${AI_SERVICE_URL}`);
  console.log(`Widget served at http://localhost:${PORT}/widget.js`);
});
