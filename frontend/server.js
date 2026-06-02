import path from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";

import {
  createSessionToken,
  isAzureHost,
  parseCookies,
  timingSafeEqual,
  verifySessionToken,
} from "./serverAuth.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const port = Number(process.env.PORT || 8080);
const distPath = path.join(__dirname, "dist");

const accessKey = (process.env.DEMO_ACCESS_KEY || "").trim();
const proxySecret = (process.env.MEETING_MINUTES_PROXY_SECRET || "").trim();
const apiOrigin = (process.env.API_ORIGIN || "").replace(/\/+$/, "");
const sessionSecret = (process.env.SESSION_SIGNING_SECRET || proxySecret || accessKey).trim();
const parsedTtl = Number(process.env.SESSION_TTL_MS);
const sessionTtlMs =
  Number.isFinite(parsedTtl) && parsedTtl > 0 ? parsedTtl : 12 * 60 * 60 * 1000;

const COOKIE_NAME = "mm_session";
const gateEnabled = accessKey.length > 0;
// Fail closed on a real Azure host unless the full gate is configured.
const misconfiguredOnAzure = isAzureHost() && (!gateEnabled || !proxySecret || !apiOrigin);

const loginAttempts = new Map();
const LOGIN_WINDOW_MS = 10 * 60 * 1000;
const LOGIN_MAX_ATTEMPTS = 10;
const MAX_PROXY_BODY_BYTES = 2 * 1024 * 1024;
const PROXY_TIMEOUT_MS = 60_000;
const HOP_BY_HOP_HEADERS = new Set([
  "host",
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "cookie",
  "authorization",
  "content-length",
  "accept-encoding",
  "x-proxy-secret",
]);

const app = express();
app.disable("x-powered-by");
// App Service terminates TLS in front of the app; trust its forwarding headers
// so req.ip and req.protocol reflect the real client.
app.set("trust proxy", true);

function isSecureRequest(req) {
  return req.get("x-forwarded-proto") === "https" || isAzureHost();
}

function setSessionCookie(req, res) {
  const token = createSessionToken(sessionSecret, sessionTtlMs);
  const attributes = [
    `${COOKIE_NAME}=${encodeURIComponent(token)}`,
    "HttpOnly",
    "SameSite=Lax",
    "Path=/",
    `Max-Age=${Math.floor(sessionTtlMs / 1000)}`,
  ];
  if (isSecureRequest(req)) {
    attributes.push("Secure");
  }
  res.setHeader("Set-Cookie", attributes.join("; "));
}

function clearSessionCookie(res) {
  res.setHeader("Set-Cookie", `${COOKIE_NAME}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0`);
}

function isAuthenticated(req) {
  if (!gateEnabled) {
    return true;
  }
  const cookies = parseCookies(req.get("cookie"));
  return verifySessionToken(sessionSecret, cookies[COOKIE_NAME]);
}

function loginPage(error) {
  const banner = error
    ? '<p class="error" role="alert">アクセスキーが正しくありません。</p>'
    : "";
  return `<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="robots" content="noindex" />
<title>Minutes Studio</title>
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: radial-gradient(1200px 600px at 50% -10%, #e9efff, #f6f7fb); color: #1b2330; }
  .card { width: min(92vw, 380px); padding: 2.25rem 2rem; background: #fff;
    border-radius: 16px; box-shadow: 0 20px 60px rgba(30, 45, 90, 0.15); }
  h1 { margin: 0 0 .25rem; font-size: 1.35rem; }
  p.sub { margin: 0 0 1.5rem; color: #5b6577; font-size: .9rem; }
  label { display: block; font-size: .85rem; font-weight: 600; margin-bottom: .4rem; }
  input { width: 100%; padding: .7rem .85rem; font-size: 1rem; border: 1px solid #cfd6e4;
    border-radius: 10px; background: #fbfcfe; color: #1b2330; caret-color: #3b6ef0; }
  input::placeholder { color: #9aa4b5; }
  input:focus { outline: 2px solid #3b6ef0; border-color: #3b6ef0; }
  button { margin-top: 1.25rem; width: 100%; padding: .75rem; font-size: 1rem; font-weight: 600;
    color: #fff; background: #3b6ef0; border: 0; border-radius: 10px; cursor: pointer; }
  button:hover { background: #2f5ad6; }
  .error { color: #c0392b; font-size: .85rem; margin: 0 0 1rem; }
</style>
</head>
<body>
  <main class="card">
    <h1>Minutes Studio</h1>
    <p class="sub">続行するにはアクセスキーを入力してください。</p>
    ${banner}
    <form method="POST" action="/login" autocomplete="off">
      <label for="key">アクセスキー</label>
      <input id="key" name="key" type="password" required autofocus aria-label="アクセスキー" />
      <button type="submit">アクセス</button>
    </form>
  </main>
</body>
</html>`;
}

function clientIp(req) {
  return req.ip || "unknown";
}

// CSRF defense for state-changing requests: require a same-origin signal.
// Browsers send Sec-Fetch-Site and/or Origin on cross-site fetches; SameSite=Lax
// already blocks the session cookie cross-site, this is defense in depth.
function isSameOriginWrite(req) {
  const fetchSite = req.get("sec-fetch-site");
  if (fetchSite) {
    return fetchSite === "same-origin" || fetchSite === "none";
  }
  const origin = req.get("origin");
  if (!origin) {
    return true;
  }
  try {
    return new URL(origin).host === req.get("host");
  } catch {
    return false;
  }
}

function tooManyAttempts(ip) {
  const now = Date.now();
  const entry = loginAttempts.get(ip);
  if (!entry || now - entry.firstAt > LOGIN_WINDOW_MS) {
    return false;
  }
  return entry.count >= LOGIN_MAX_ATTEMPTS;
}

function recordFailedAttempt(ip) {
  const now = Date.now();
  const entry = loginAttempts.get(ip);
  if (!entry || now - entry.firstAt > LOGIN_WINDOW_MS) {
    loginAttempts.set(ip, { count: 1, firstAt: now });
    return;
  }
  entry.count += 1;
}

function readRawBody(req, maxBytes) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let total = 0;
    req.on("data", (chunk) => {
      total += chunk.length;
      if (total > maxBytes) {
        const error = new Error("request body too large");
        error.code = "BODY_TOO_LARGE";
        req.destroy();
        reject(error);
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

// --- Open endpoints ----------------------------------------------------------
app.get("/healthz", (_req, res) => {
  res.status(200).json({ status: "ok" });
});

// --- Fail closed if misconfigured on Azure -----------------------------------
app.use((req, res, next) => {
  if (misconfiguredOnAzure) {
    res.status(503).type("text/plain").send("Service is not configured for access.");
    return;
  }
  next();
});

app.get("/login", (req, res) => {
  if (!gateEnabled || isAuthenticated(req)) {
    res.redirect("/");
    return;
  }
  res.status(200).type("html").send(loginPage(false));
});

app.post("/login", express.urlencoded({ extended: false, limit: "1kb" }), async (req, res) => {
  if (!gateEnabled) {
    res.redirect("/");
    return;
  }
  const ip = clientIp(req);
  if (tooManyAttempts(ip)) {
    res.status(429).type("html").send(loginPage(true));
    return;
  }
  const provided = typeof req.body?.key === "string" ? req.body.key : "";
  if (provided && timingSafeEqual(provided, accessKey)) {
    loginAttempts.delete(ip);
    setSessionCookie(req, res);
    res.redirect("/");
    return;
  }
  recordFailedAttempt(ip);
  // Small fixed delay to slow online brute-force attempts.
  await new Promise((resolve) => setTimeout(resolve, 500));
  res.status(401).type("html").send(loginPage(true));
});

app.post("/logout", (req, res) => {
  if (!isSameOriginWrite(req)) {
    res.status(403).type("text/plain").send("Forbidden");
    return;
  }
  clearSessionCookie(res);
  res.redirect("/login");
});

// --- Authentication gate -----------------------------------------------------
app.use((req, res, next) => {
  if (isAuthenticated(req)) {
    next();
    return;
  }
  if (req.path === "/api" || req.path.startsWith("/api/")) {
    res.status(401).json({
      error: { code: "AUTH_REQUIRED", message: "アクセスキーでのサインインが必要です。" },
    });
    return;
  }
  res.redirect("/login");
});

// --- Reverse proxy to the Functions API --------------------------------------
app.use("/api", async (req, res) => {
  if (!apiOrigin) {
    res.status(502).json({
      error: { code: "PROXY_NOT_CONFIGURED", message: "APIの接続先が設定されていません。" },
    });
    return;
  }
  const method = req.method.toUpperCase();
  // Lightweight CSRF defense: reject cross-site state-changing requests.
  if (method !== "GET" && method !== "HEAD" && !isSameOriginWrite(req)) {
    res.status(403).json({
      error: { code: "FORBIDDEN", message: "リクエストの送信元を確認できませんでした。" },
    });
    return;
  }

  const targetUrl = `${apiOrigin}${req.originalUrl}`;
  const headers = {};
  for (const [name, value] of Object.entries(req.headers)) {
    if (!HOP_BY_HOP_HEADERS.has(name.toLowerCase()) && typeof value === "string") {
      headers[name] = value;
    }
  }
  headers["x-proxy-secret"] = proxySecret;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROXY_TIMEOUT_MS);
  try {
    let body;
    if (method !== "GET" && method !== "HEAD") {
      body = await readRawBody(req, MAX_PROXY_BODY_BYTES);
    }
    const upstream = await fetch(targetUrl, {
      method,
      headers,
      body,
      redirect: "manual",
      signal: controller.signal,
    });
    res.status(upstream.status);
    const contentType = upstream.headers.get("content-type");
    if (contentType) {
      res.setHeader("Content-Type", contentType);
    }
    const correlationId = upstream.headers.get("x-correlation-id");
    if (correlationId) {
      res.setHeader("x-correlation-id", correlationId);
    }
    const buffer = Buffer.from(await upstream.arrayBuffer());
    res.send(buffer);
  } catch (error) {
    if (error && error.code === "BODY_TOO_LARGE") {
      res.status(413).json({
        error: { code: "PAYLOAD_TOO_LARGE", message: "リクエストが大きすぎます。" },
      });
      return;
    }
    if (error && error.name === "AbortError") {
      res.status(504).json({
        error: { code: "UPSTREAM_TIMEOUT", message: "APIの応答がタイムアウトしました。" },
      });
      return;
    }
    res.status(502).json({
      error: { code: "UPSTREAM_UNAVAILABLE", message: "APIへの接続に失敗しました。" },
    });
  } finally {
    clearTimeout(timer);
  }
});

// --- Static assets and SPA fallback (authenticated) --------------------------
app.use(express.static(distPath));
app.use((_req, res) => {
  res.sendFile(path.join(distPath, "index.html"));
});

app.listen(port, "0.0.0.0", () => {
  const mode = gateEnabled ? "access-key gate enabled" : "open (no DEMO_ACCESS_KEY)";
  console.log(`Frontend server listening on ${port} (${mode})`);
});
