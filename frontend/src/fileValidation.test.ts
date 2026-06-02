import { describe, expect, it } from "vitest";

import {
  hardMaxAudioFileSizeBytes,
  maxAudioDurationSeconds,
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
  });

  it("rejects unsupported extensions", () => {
    expect(validateAudioFile(file("meeting.txt", 1024)).valid).toBe(false);
  });

  it("rejects files over the hard limit", () => {
    expect(validateAudioFile(file("meeting.mp3", hardMaxAudioFileSizeBytes + 1)).valid).toBe(false);
  });

  it("sets the UI duration limit to 120 minutes", () => {
    expect(maxAudioDurationSeconds).toBe(120 * 60);
  });
});
