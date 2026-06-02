import { supportedAudioExtensions } from "./appConfig";

export const hardMaxAudioFileSizeBytes = 500 * 1024 * 1024;
export const maxAudioDurationSeconds = 120 * 60;

export type FileValidationResult = {
  valid: boolean;
  message?: string;
};

export function validateAudioFile(file: File): FileValidationResult {
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
  if (file.size > hardMaxAudioFileSizeBytes) {
    return {
      valid: false,
      message: "音声ファイルが500MBを超えています。ファイルを圧縮してください。",
    };
  }
  return { valid: true };
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
