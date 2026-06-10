import { supportedAudioExtensions } from "./appConfig";
import type { ProcessingRoute } from "./apiClient";

export const hardMaxAudioFileSizeBytes = 500 * 1024 * 1024;
export const batchMaxAudioFileSizeBytes = 1024 * 1024 * 1024;
export const stablePreprocessedSourceMaxFileSizeBytes = 4 * 1024 * 1024 * 1024;
export const contentUnderstandingMaxFileSizeBytes = 4 * 1024 * 1024 * 1024;
export const maxAudioDurationSeconds = 120 * 60;
export const batchMaxAudioDurationSeconds = 240 * 60;
const preprocessedExtensions = new Set([".m4a", ".mp4"]);
const preprocessedContentTypes = new Set([
  "application/mp4",
  "audio/aac",
  "audio/m4a",
  "audio/mp4",
  "audio/x-m4a",
  "video/mp4",
]);

export type FileValidationResult = {
  valid: boolean;
  message?: string;
};

export function validateAudioFile(
  file: File,
  processingRoute: ProcessingRoute = "stable",
): FileValidationResult {
  const lowerName = file.name.toLowerCase();
  const hasSupportedExtension = supportedAudioExtensions.some((extension) =>
    lowerName.endsWith(extension),
  );
  if (!hasSupportedExtension) {
    return {
      valid: false,
      message: `対応形式は ${supportedAudioExtensions.join(", ")} です。`,
    };
  }
  const maxFileSizeBytes = getMaxFileSizeBytes(processingRoute, file);
  if (file.size >= maxFileSizeBytes) {
    if (processingRoute === "stable" && shouldPreprocessMedia(file)) {
      return {
        valid: false,
        message:
          "標準経路で前処理できる元ファイルサイズの上限4GBを超えています。動画を圧縮または分割してください。",
      };
    }
    return {
      valid: false,
      message:
        processingRoute === "contentUnderstanding"
          ? "動画理解経路の上限4GBを超えています。動画を圧縮してください。"
        : "標準経路のBatch fallback上限1GBを超えています。音声を圧縮または分割してください。",
    };
  }
  return { valid: true };
}

export function getMaxFileSizeBytes(
  processingRoute: ProcessingRoute,
  file?: Pick<File, "name" | "type"> | null,
): number {
  if (processingRoute === "contentUnderstanding") {
    return contentUnderstandingMaxFileSizeBytes;
  }
  if (file && shouldPreprocessMedia(file)) {
    return stablePreprocessedSourceMaxFileSizeBytes;
  }
  return batchMaxAudioFileSizeBytes;
}

export function shouldPreprocessMedia(file: Pick<File, "name" | "type">): boolean {
  const lowerName = file.name.toLowerCase();
  const extension = lowerName.includes(".")
    ? lowerName.slice(lowerName.lastIndexOf("."))
    : "";
  const normalizedType = file.type.trim().toLowerCase();
  return preprocessedExtensions.has(extension) || preprocessedContentTypes.has(normalizedType);
}

export function getMaxDurationSeconds(processingRoute: ProcessingRoute): number {
  return processingRoute === "contentUnderstanding"
    ? maxAudioDurationSeconds
    : batchMaxAudioDurationSeconds;
}

export function getAudioDurationSeconds(file: File, timeoutMilliseconds = 5000): Promise<number | null> {
  return new Promise((resolve) => {
    const audio = document.createElement("audio");
    const objectUrl = URL.createObjectURL(file);
    const timeout = window.setTimeout(() => cleanup(null), timeoutMilliseconds);

    function cleanup(value: number | null) {
      window.clearTimeout(timeout);
      URL.revokeObjectURL(objectUrl);
      audio.removeAttribute("src");
      audio.load();
      resolve(value);
    }

    audio.onloadedmetadata = () => {
      cleanup(Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : null);
    };
    audio.onerror = () => cleanup(null);
    audio.src = objectUrl;
  });
}
