export type JobStatus =
  | "CREATED"
  | "UPLOADING"
  | "UPLOADED"
  | "VALIDATING"
  | "PREPROCESSING"
  | "TRANSCRIBING"
  | "TRANSCRIPT_READY"
  | "GENERATING_CHUNK_SUMMARIES"
  | "GENERATING_FINAL_MINUTES"
  | "REVIEW_REQUIRED"
  | "DONE"
  | "FAILED"
  | "CANCELLED";

export type MinutesModel = "fast" | "quality";
export type ProcessingRoute = "stable" | "contentUnderstanding";

export type CreateJobResponse = {
  jobId: string;
  status: JobStatus;
  blobName: string;
  uploadUrl: string;
  uploadExpiresAt: string;
  constraints: {
    normalMaxFileSizeBytes: number;
    hardMaxFileSizeBytes: number;
    maxDurationSecondsWithDiarization: number;
  };
};

export type UploadCompleteResponse = {
  jobId: string;
  status: JobStatus;
  orchestrationInstanceId: string;
  statusUrl: string;
};

export type JobStatusResponse = {
  jobId: string;
  tenantId: string;
  userId: string;
  minutesModel: MinutesModel;
  processingRoute: ProcessingRoute;
  status: JobStatus;
  progress: {
    step: string;
    percent: number;
    message: string;
    updatedAt: string;
  };
  outputs: {
    transcriptReady: boolean;
    minutesReady: boolean;
    rawTranscriptBlobUri?: string | null;
    normalizedTranscriptBlobUri?: string | null;
    visualContextBlobUri?: string | null;
    minutesJsonBlobUri?: string | null;
    minutesMarkdownBlobUri?: string | null;
  };
  error?: {
    code: string;
    message: string;
    correlationId: string;
  } | null;
  createdAt: string;
  updatedAt: string;
};

export type TranscriptResponse = {
  jobId: string;
  tenantId: string;
  locale: string;
  durationMilliseconds: number;
  speakers: Array<{
    speakerLabel: string;
    displayName: string | null;
    phraseCount: number;
    representativePhrases: Array<{
      offsetMilliseconds: number;
      startTimeText: string;
      text: string;
    }>;
  }>;
  phrases: Array<{
    phraseId: string;
    speakerLabel: string;
    displayName: string | null;
    offsetMilliseconds: number;
    durationMilliseconds: number;
    startTimeText: string;
    endTimeText?: string;
    text: string;
    confidence: number | null;
  }>;
};

export type MinutesResponse = {
  jobId: string;
  tenantId: string;
  title: string;
  summary: string;
  topics: Array<{ title: string; discussion: string; evidenceTimestamps: string[] }>;
  decisions: Array<{ text: string; owner: string | null; sourceTimestamps: string[] }>;
  actionItems: Array<{
    task: string;
    owner: string | null;
    dueDate: string | null;
    sourceTimestamps: string[];
  }>;
  openQuestions: Array<{ text: string; owner: string | null; sourceTimestamps: string[] }>;
  risks: Array<{ text: string; severity: string; sourceTimestamps: string[] }>;
};

export type DevAuthEnv = {
  VITE_DEV_TENANT_ID?: string;
  VITE_DEV_USER_ID?: string;
};

export type UploadErrorKind = "network" | "cors-suspected" | "http-status" | "aborted";

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export class UploadError extends Error {
  constructor(
    readonly kind: UploadErrorKind,
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "UploadError";
  }
}

export const terminalStatuses: ReadonlySet<JobStatus> = new Set(["DONE", "FAILED", "CANCELLED"]);

const defaultApiBaseUrl = "http://localhost:7071/api";
const fallbackContentType = "application/octet-stream";
const canonicalAudioContentTypeByExtension: Record<string, string> = {
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".m4a": "audio/mp4",
  ".mp4": "video/mp4",
  ".ogg": "audio/ogg",
  ".webm": "audio/webm",
  ".flac": "audio/flac",
};
const allowedAudioContentTypesByExtension: Record<string, ReadonlySet<string>> = {
  ".mp3": new Set(["audio/mpeg", "audio/mp3"]),
  ".wav": new Set(["audio/wav", "audio/x-wav"]),
  ".m4a": new Set(["audio/mp4", "audio/m4a", "audio/x-m4a", "audio/aac"]),
  ".mp4": new Set(["video/mp4", "audio/mp4", "application/mp4"]),
  ".ogg": new Set(["audio/ogg"]),
  ".webm": new Set(["audio/webm"]),
  ".flac": new Set(["audio/flac"]),
};

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/+$/, "");
}

export function resolveAudioContentType(file: Pick<File, "name" | "type">): string {
  const extension = getLowerExtension(file.name);
  const inferredContentType = extension
    ? canonicalAudioContentTypeByExtension[extension]
    : undefined;
  const normalizedFileType = file.type.trim().toLowerCase();
  if (!extension || !inferredContentType) {
    return normalizedFileType || fallbackContentType;
  }
  if (!normalizedFileType || normalizedFileType === fallbackContentType) {
    return inferredContentType;
  }
  if (!allowedAudioContentTypesByExtension[extension]?.has(normalizedFileType)) {
    return inferredContentType;
  }
  return normalizedFileType;
}

export function buildDevAuthHeaders(isDev: boolean, env: DevAuthEnv): Record<string, string> {
  if (!isDev) {
    return {};
  }
  return {
    "x-dev-tenant-id": env.VITE_DEV_TENANT_ID || "local-tenant",
    "x-dev-user-id": env.VITE_DEV_USER_ID || "local-user",
  };
}

export function shouldSendDevAuthHeaders(isDev: boolean, apiBaseUrl: string): boolean {
  return isDev && isLocalApiBaseUrl(apiBaseUrl);
}

export function isLocalApiBaseUrl(apiBaseUrl: string): boolean {
  try {
    const hostname = new URL(apiBaseUrl, "http://localhost").hostname.toLowerCase();
    return (
      hostname === "localhost" ||
      hostname === "127.0.0.1" ||
      hostname === "[::1]" ||
      hostname === "::1"
    );
  } catch {
    return false;
  }
}

export function isLocalPlaceholderUploadUrl(uploadUrl: string): boolean {
  try {
    return new URL(uploadUrl).hostname === "local.blob.invalid";
  } catch {
    return false;
  }
}

export async function createJob(
  file: File,
  clientEstimatedDurationSeconds?: number | null,
  minutesModel: MinutesModel = "fast",
  processingRoute: ProcessingRoute = "stable",
): Promise<CreateJobResponse> {
  return apiFetch<CreateJobResponse>("/jobs", {
    method: "POST",
    body: JSON.stringify({
      fileName: file.name,
      contentType: resolveAudioContentType(file),
      fileSizeBytes: file.size,
      ...(clientEstimatedDurationSeconds
        ? { clientEstimatedDurationSeconds: Math.round(clientEstimatedDurationSeconds) }
        : {}),
      locale: "ja-JP",
      maxSpeakers: 8,
      minutesModel,
      processingRoute,
    }),
  });
}

export async function completeUpload(
  jobId: string,
  file: File,
): Promise<UploadCompleteResponse> {
  return apiFetch<UploadCompleteResponse>(`/jobs/${encodeURIComponent(jobId)}/upload-complete`, {
    method: "POST",
    body: JSON.stringify({
      uploadedSizeBytes: file.size,
    }),
  });
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  return apiFetch<JobStatusResponse>(`/jobs/${encodeURIComponent(jobId)}`, {
    method: "GET",
  });
}

export async function getTranscript(jobId: string): Promise<TranscriptResponse> {
  return apiFetch<TranscriptResponse>(`/jobs/${encodeURIComponent(jobId)}/transcript`, {
    method: "GET",
  });
}

export async function getMinutes(jobId: string): Promise<MinutesResponse> {
  return apiFetch<MinutesResponse>(`/jobs/${encodeURIComponent(jobId)}/minutes`, {
    method: "GET",
  });
}

export async function updateSpeakerMapping(
  jobId: string,
  speakers: Array<{ speakerLabel: string; displayName: string | null }>,
): Promise<void> {
  await apiFetch<unknown>(`/jobs/${encodeURIComponent(jobId)}/speaker-mapping`, {
    method: "PUT",
    body: JSON.stringify({ speakers }),
  });
}

export async function uploadAudioFile(
  uploadUrl: string,
  file: File,
  onProgress: (percent: number) => void,
): Promise<void> {
  if (import.meta.env.DEV && isLocalPlaceholderUploadUrl(uploadUrl)) {
    onProgress(100);
    return;
  }

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", uploadUrl);
    request.setRequestHeader("x-ms-blob-type", "BlockBlob");
    request.setRequestHeader("Content-Type", resolveAudioContentType(file));

    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(100);
        resolve();
        return;
      }
      reject(new UploadError("http-status", "アップロードに失敗しました。", request.status));
    };
    request.onerror = () => {
      reject(
        new UploadError(
          "cors-suspected",
          "アップロードに失敗しました。Storage CORS設定またはネットワークを確認してください。",
        ),
      );
    };
    request.onabort = () => {
      reject(new UploadError("aborted", "アップロードが中断されました。"));
    };
    request.send(file);
  });
}

function getLowerExtension(fileName: string): string | undefined {
  const lowerName = fileName.toLowerCase();
  const dotIndex = lowerName.lastIndexOf(".");
  if (dotIndex < 0) {
    return undefined;
  }
  return lowerName.slice(dotIndex);
}

async function apiFetch<T>(path: string, init: RequestInit): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("Content-Type", "application/json");

  const apiBaseUrl = getApiBaseUrl();
  const devHeaders = buildDevAuthHeaders(
    shouldSendDevAuthHeaders(import.meta.env.DEV, apiBaseUrl),
    import.meta.env,
  );
  for (const [key, value] of Object.entries(devHeaders)) {
    headers.set(key, value);
  }

  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  });
  const body = await parseResponseBody(response);

  if (!response.ok) {
    const error = extractError(body);
    throw new ApiClientError(error.message, response.status, error.code);
  }

  return body as T;
}

async function parseResponseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return {};
  }
  return JSON.parse(text);
}

function extractError(body: unknown): { code?: string; message: string } {
  if (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    typeof body.error === "object" &&
    body.error !== null &&
    "message" in body.error
  ) {
    const error = body.error as { code?: unknown; message: unknown };
    return {
      code: typeof error.code === "string" ? error.code : undefined,
      message: typeof error.message === "string" ? error.message : "APIエラーが発生しました。",
    };
  }
  return { message: "APIエラーが発生しました。" };
}
