import { describe, expect, it } from "vitest";

import {
  getJobPollingDelayMilliseconds,
  healthyJobPollingIntervalMs,
  hiddenJobPollingIntervalMs,
  maxFailureJobPollingIntervalMs,
  shouldFetchMinutes,
  shouldFetchTranscript,
} from "./jobPolling";

describe("jobPolling", () => {
  it("uses a slower healthy polling interval for visible tabs", () => {
    expect(getJobPollingDelayMilliseconds(0, "visible")).toBe(healthyJobPollingIntervalMs);
  });

  it("slows healthy polling while the tab is hidden", () => {
    expect(getJobPollingDelayMilliseconds(0, "hidden")).toBe(hiddenJobPollingIntervalMs);
  });

  it("retains capped failure backoff", () => {
    expect(getJobPollingDelayMilliseconds(1, "visible")).toBe(2000);
    expect(getJobPollingDelayMilliseconds(2, "visible")).toBe(4000);
    expect(getJobPollingDelayMilliseconds(3, "visible")).toBe(maxFailureJobPollingIntervalMs);
  });

  it("prioritizes failure backoff over hidden-tab slowing", () => {
    expect(getJobPollingDelayMilliseconds(1, "hidden")).toBe(2000);
  });

  it("fetches transcript once after transcript artifacts can be ready", () => {
    expect(shouldFetchTranscript("TRANSCRIBING", false)).toBe(false);
    expect(shouldFetchTranscript("TRANSCRIPT_READY", false)).toBe(true);
    expect(shouldFetchTranscript("GENERATING_CHUNK_SUMMARIES", false)).toBe(true);
    expect(shouldFetchTranscript("GENERATING_FINAL_MINUTES", false)).toBe(true);
    expect(shouldFetchTranscript("DONE", false)).toBe(true);
    expect(shouldFetchTranscript("DONE", true)).toBe(false);
  });

  it("fetches minutes only once after the job is done", () => {
    expect(shouldFetchMinutes("GENERATING_FINAL_MINUTES", false)).toBe(false);
    expect(shouldFetchMinutes("DONE", false)).toBe(true);
    expect(shouldFetchMinutes("DONE", true)).toBe(false);
  });
});
