import type { JobStatus } from "./apiClient";

export const healthyJobPollingIntervalMs = 4000;
export const hiddenJobPollingIntervalMs = 15000;
export const maxFailureJobPollingIntervalMs = 5000;

const failureBackoffBaseMs = 1000;
const transcriptFetchStatuses: ReadonlySet<JobStatus> = new Set([
  "TRANSCRIPT_READY",
  "GENERATING_CHUNK_SUMMARIES",
  "GENERATING_FINAL_MINUTES",
  "DONE",
]);

export function getJobPollingDelayMilliseconds(
  failureCount: number,
  visibilityState: DocumentVisibilityState = "visible",
): number {
  if (failureCount > 0) {
    return Math.min(failureBackoffBaseMs * 2 ** failureCount, maxFailureJobPollingIntervalMs);
  }
  return visibilityState === "hidden" ? hiddenJobPollingIntervalMs : healthyJobPollingIntervalMs;
}

export function shouldFetchTranscript(status: JobStatus, hasTranscript: boolean): boolean {
  return !hasTranscript && transcriptFetchStatuses.has(status);
}

export function shouldFetchMinutes(status: JobStatus, hasMinutes: boolean): boolean {
  return !hasMinutes && status === "DONE";
}
