import { afterEach, describe, expect, it, vi } from "vitest";

import {
  appendBlobQueryParameters,
  buildDevAuthHeaders,
  createJob,
  isLocalApiBaseUrl,
  isLocalPlaceholderUploadUrl,
  resolveAudioContentType,
  shouldSendDevAuthHeaders,
} from "./apiClient";

describe("apiClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("detects only the exact local placeholder upload host", () => {
    expect(isLocalPlaceholderUploadUrl("https://local.blob.invalid/container/file?sig=dev")).toBe(
      true,
    );
    expect(isLocalPlaceholderUploadUrl("https://local.blob.invalid.evil.test/file")).toBe(false);
  });

  it("appends block upload query parameters after the SAS query", () => {
    expect(
      appendBlobQueryParameters("https://storage.example/video.mp4?sv=2026&sig=redacted", {
        comp: "block",
        blockid: "abc==",
      }),
    ).toBe("https://storage.example/video.mp4?sv=2026&sig=redacted&comp=block&blockid=abc%3D%3D");
  });

  it("adds development auth headers only when dev mode is enabled", () => {
    expect(
      buildDevAuthHeaders(true, {
        VITE_DEV_TENANT_ID: "tenant-a",
        VITE_DEV_USER_ID: "user-a",
      }),
    ).toEqual({
      "x-dev-tenant-id": "tenant-a",
      "x-dev-user-id": "user-a",
    });
    expect(buildDevAuthHeaders(false, {})).toEqual({});
  });

  it("allows dev auth headers only for local API origins", () => {
    expect(shouldSendDevAuthHeaders(true, "http://localhost:7071/api")).toBe(true);
    expect(shouldSendDevAuthHeaders(true, "http://127.0.0.1:7071/api")).toBe(true);
    expect(shouldSendDevAuthHeaders(true, "http://[::1]:7071/api")).toBe(true);
    expect(shouldSendDevAuthHeaders(false, "http://localhost:7071/api")).toBe(false);
    expect(shouldSendDevAuthHeaders(true, "https://func.azurewebsites.net/api")).toBe(false);
  });

  it("does not treat localhost-looking remote hosts as local", () => {
    expect(isLocalApiBaseUrl("https://localhost.evil.test/api")).toBe(false);
  });

  it("infers a stable m4a content type when the browser omits one", () => {
    expect(resolveAudioContentType({ name: "meeting.m4a", type: "" })).toBe("audio/mp4");
  });

  it("normalizes mismatched known extension content types before sending to the backend", () => {
    expect(resolveAudioContentType({ name: "meeting.m4a", type: "audio/mpeg" })).toBe(
      "audio/mp4",
    );
  });

  it("infers a stable mp4 content type when the browser omits one", () => {
    expect(resolveAudioContentType({ name: "meeting.mp4", type: "" })).toBe("video/mp4");
  });

  it("preserves compatible browser mp4 content types", () => {
    expect(resolveAudioContentType({ name: "meeting.mp4", type: "video/mp4" })).toBe(
      "video/mp4",
    );
  });

  it("normalizes mismatched mp4 content types before sending to the backend", () => {
    expect(resolveAudioContentType({ name: "meeting.mp4", type: "audio/mpeg" })).toBe(
      "video/mp4",
    );
  });

  it("preserves compatible browser m4a content types", () => {
    expect(resolveAudioContentType({ name: "meeting.m4a", type: "audio/x-m4a" })).toBe(
      "audio/x-m4a",
    );
  });

  it("never returns an empty content type", () => {
    expect(resolveAudioContentType({ name: "meeting.unknown", type: "" })).toBe(
      "application/octet-stream",
    );
  });

  it("sends the selected minutes model and processing route when creating a job", async () => {
    const requests: RequestInit[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, init: RequestInit) => {
        requests.push(init);
        return new Response(
          JSON.stringify({
            jobId: "job-a",
            status: "CREATED",
            blobName: "raw-audio/demo/job-a/meeting.mp3",
            uploadUrl: "https://storage.example/upload",
            uploadExpiresAt: "2026-06-02T00:00:00.000Z",
            constraints: {
              normalMaxFileSizeBytes: 314572800,
              hardMaxFileSizeBytes: 524288000,
              contentUnderstandingMaxFileSizeBytes: 4294967296,
              maxDurationSecondsWithDiarization: 7200,
              stableUploadSasTtlMinutes: 30,
              contentUnderstandingUploadSasTtlMinutes: 120,
            },
          }),
          { status: 201, headers: { "Content-Type": "application/json" } },
        );
      }),
    );

    await createJob(
      new File(["audio"], "meeting.mp3", { type: "audio/mpeg" }),
      60,
      "quality",
      "contentUnderstanding",
    );

    const body = JSON.parse(String(requests[0].body)) as {
      minutesModel: string;
      processingRoute: string;
    };
    expect(body.minutesModel).toBe("quality");
    expect(body.processingRoute).toBe("contentUnderstanding");
  });
});
