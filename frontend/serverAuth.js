import crypto from "node:crypto";

const TOKEN_PAYLOAD = "loggedin";

/**
 * Constant-time string comparison that is safe against length leaks.
 * @param {string} a
 * @param {string} b
 * @returns {boolean}
 */
export function timingSafeEqual(a, b) {
  const bufferA = crypto.createHash("sha256").update(String(a)).digest();
  const bufferB = crypto.createHash("sha256").update(String(b)).digest();
  return crypto.timingSafeEqual(bufferA, bufferB);
}

function base64UrlEncode(value) {
  return Buffer.from(String(value), "utf8").toString("base64url");
}

function sign(secret, message) {
  return crypto.createHmac("sha256", secret).update(message).digest("base64url");
}

/**
 * Create a signed session token of the form `base64url(expiryMs).signature`.
 * @param {string} secret
 * @param {number} ttlMs
 * @param {number} [now]
 * @returns {string}
 */
export function createSessionToken(secret, ttlMs, now = Date.now()) {
  const expiry = now + ttlMs;
  const encodedExpiry = base64UrlEncode(String(expiry));
  const signature = sign(secret, `${TOKEN_PAYLOAD}|${encodedExpiry}`);
  return `${encodedExpiry}.${signature}`;
}

/**
 * Verify a session token's signature and expiry.
 * @param {string} secret
 * @param {string | undefined | null} token
 * @param {number} [now]
 * @returns {boolean}
 */
export function verifySessionToken(secret, token, now = Date.now()) {
  if (!secret || typeof token !== "string" || !token.includes(".")) {
    return false;
  }
  const separatorIndex = token.indexOf(".");
  const encodedExpiry = token.slice(0, separatorIndex);
  const providedSignature = token.slice(separatorIndex + 1);
  const expectedSignature = sign(secret, `${TOKEN_PAYLOAD}|${encodedExpiry}`);
  if (!timingSafeEqual(providedSignature, expectedSignature)) {
    return false;
  }
  const expiry = Number(Buffer.from(encodedExpiry, "base64url").toString("utf8"));
  if (!Number.isFinite(expiry)) {
    return false;
  }
  return expiry > now;
}

/**
 * Parse a Cookie header into a name/value map.
 * @param {string | undefined | null} header
 * @returns {Record<string, string>}
 */
export function parseCookies(header) {
  /** @type {Record<string, string>} */
  const result = {};
  if (typeof header !== "string" || header.length === 0) {
    return result;
  }
  for (const part of header.split(";")) {
    const separatorIndex = part.indexOf("=");
    if (separatorIndex < 0) {
      continue;
    }
    const name = part.slice(0, separatorIndex).trim();
    const value = part.slice(separatorIndex + 1).trim();
    if (name) {
      result[name] = decodeURIComponent(value);
    }
  }
  return result;
}

/**
 * Whether the process is running on an Azure App Service / Functions host.
 * @param {NodeJS.ProcessEnv} [env]
 * @returns {boolean}
 */
export function isAzureHost(env = process.env) {
  return Boolean(env.WEBSITE_SITE_NAME);
}
