import { describe, expect, it } from "vitest";

import {
  createSessionToken,
  isAzureHost,
  parseCookies,
  timingSafeEqual,
  verifySessionToken,
} from "./serverAuth.js";

describe("timingSafeEqual", () => {
  it("returns true for equal strings", () => {
    expect(timingSafeEqual("secret-key", "secret-key")).toBe(true);
  });

  it("returns false for different strings of different length", () => {
    expect(timingSafeEqual("secret-key", "secret-key-extra")).toBe(false);
  });

  it("returns false for different strings of same length", () => {
    expect(timingSafeEqual("secret-aaa", "secret-bbb")).toBe(false);
  });
});

describe("session token", () => {
  const secret = "signing-secret";

  it("creates a token that verifies before expiry", () => {
    const now = 1_000_000;
    const token = createSessionToken(secret, 60_000, now);
    expect(verifySessionToken(secret, token, now + 30_000)).toBe(true);
  });

  it("rejects an expired token", () => {
    const now = 1_000_000;
    const token = createSessionToken(secret, 60_000, now);
    expect(verifySessionToken(secret, token, now + 60_001)).toBe(false);
  });

  it("rejects a token signed with a different secret", () => {
    const now = 1_000_000;
    const token = createSessionToken("other-secret", 60_000, now);
    expect(verifySessionToken(secret, token, now)).toBe(false);
  });

  it("rejects a tampered token", () => {
    const now = 1_000_000;
    const token = createSessionToken(secret, 60_000, now);
    const tampered = `${token}x`;
    expect(verifySessionToken(secret, tampered, now)).toBe(false);
  });

  it("rejects malformed input", () => {
    expect(verifySessionToken(secret, undefined)).toBe(false);
    expect(verifySessionToken(secret, "")).toBe(false);
    expect(verifySessionToken(secret, "no-separator")).toBe(false);
    expect(verifySessionToken("", "anything.sig")).toBe(false);
  });
});

describe("parseCookies", () => {
  it("parses multiple cookies", () => {
    expect(parseCookies("a=1; b=two; c=three")).toEqual({ a: "1", b: "two", c: "three" });
  });

  it("decodes url-encoded values", () => {
    expect(parseCookies("session=a%2Eb")).toEqual({ session: "a.b" });
  });

  it("returns empty object for missing header", () => {
    expect(parseCookies(undefined)).toEqual({});
    expect(parseCookies("")).toEqual({});
  });
});

describe("isAzureHost", () => {
  it("detects an Azure host by WEBSITE_SITE_NAME", () => {
    expect(isAzureHost({ WEBSITE_SITE_NAME: "mm-demo-web" })).toBe(true);
    expect(isAzureHost({})).toBe(false);
  });
});
