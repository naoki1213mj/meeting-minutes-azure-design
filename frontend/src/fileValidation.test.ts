import { describe, expect, it } from "vitest";

import {
  batchMaxAudioFileSizeBytes,
  contentUnderstandingMaxFileSizeBytes,
  getMaxDurationSeconds,
  hardMaxAudioFileSizeBytes,
  maxAudioDurationSeconds,
  stablePreprocessedSourceMaxFileSizeBytes,
  validateAudioFile,
} from "./fileValidation";

function file(name: string, size: number, type = "audio/mpeg"): File {
  const result = new File(["x"], name, { type, lastModified: 0 });
  Object.defineProperty(result, "size", { value: size });
  return result;
}

describe("fileValidation", () => {
  it("accepts supported audio extensions", () => {
    expect(validateAudioFile(file("meeting.mp3", 1024)).valid).toBe(true);
    expect(validateAudioFile(file("meeting.mp4", 1024, "video/mp4")).valid).toBe(true);
  });

  it("rejects unsupported extensions", () => {
    expect(validateAudioFile(file("meeting.txt", 1024)).valid).toBe(false);
  });

  it("rejects stable-route direct audio files over the batch fallback limit", () => {
    expect(validateAudioFile(file("meeting.mp3", batchMaxAudioFileSizeBytes - 1)).valid).toBe(true);
    expect(validateAudioFile(file("meeting.mp3", batchMaxAudioFileSizeBytes)).valid).toBe(false);
  });

  it("allows larger stable-route mp4 files that are preprocessed before Speech", () => {
    expect(
      validateAudioFile(file("meeting.mp4", batchMaxAudioFileSizeBytes + 1, "video/mp4")).valid,
    ).toBe(true);
    expect(
      validateAudioFile(
        file("meeting.mp4", stablePreprocessedSourceMaxFileSizeBytes + 1, "video/mp4"),
      ).valid,
    ).toBe(false);
  });

  it("allows larger videos for the Content Understanding route", () => {
    expect(
      validateAudioFile(file("meeting.mp4", hardMaxAudioFileSizeBytes + 1, "video/mp4"), "contentUnderstanding").valid,
    ).toBe(true);
    expect(
      validateAudioFile(
        file("meeting.mp4", contentUnderstandingMaxFileSizeBytes + 1, "video/mp4"),
        "contentUnderstanding",
      ).valid,
    ).toBe(false);
  });

  it("sets the UI duration limit to 120 minutes", () => {
    expect(maxAudioDurationSeconds).toBe(120 * 60);
    expect(getMaxDurationSeconds("stable")).toBe(240 * 60);
    expect(getMaxDurationSeconds("contentUnderstanding")).toBe(120 * 60);
  });
});
