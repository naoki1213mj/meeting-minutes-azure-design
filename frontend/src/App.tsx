import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type FormEvent,
} from "react";

import {
  ApiClientError,
  UploadError,
  completeUpload,
  createJob,
  getJob,
  getMinutes,
  getTranscript,
  terminalStatuses,
  uploadAudioFile,
  type CreateJobResponse,
  type JobStatus,
  type JobStatusResponse,
  type MinutesResponse,
  type TranscriptResponse,
} from "./apiClient";
import { appTitle, supportedAudioExtensions } from "./appConfig";
import { getAudioDurationSeconds, hardMaxAudioFileSizeBytes, validateAudioFile } from "./fileValidation";
import { frontendFeatures } from "./frontendFeatures";
import {
  getJobPollingDelayMilliseconds,
  shouldFetchMinutes,
  shouldFetchTranscript,
} from "./jobPolling";
import { MinutesPanel, TranscriptPanel } from "./Panels";

type FileMetadata = {
  name: string;
  extension: string;
  size: string;
  type: string;
  lastModified: string;
};

type StatusTone = "accent" | "danger" | "info" | "neutral" | "success" | "warning";

type StatusDescriptor = {
  label: string;
  tone: StatusTone;
};

type StepState = "active" | "complete" | "failed" | "idle";

const processSteps = [
  { label: "選択", description: "音声ファイルを確認" },
  { label: "アップロード", description: "Azure Blob へ転送" },
  { label: "文字起こし", description: "話者分離と整形" },
  { label: "議事録生成", description: "要約・ToDo抽出" },
  { label: "完了", description: "レビュー可能" },
] as const;

const statusLabels: Record<JobStatus, StatusDescriptor> = {
  CREATED: { label: "ジョブ作成済み", tone: "info" },
  UPLOADING: { label: "アップロード中", tone: "accent" },
  UPLOADED: { label: "アップロード完了", tone: "info" },
  VALIDATING: { label: "検証中", tone: "accent" },
  PREPROCESSING: { label: "前処理中", tone: "accent" },
  TRANSCRIBING: { label: "文字起こし中", tone: "accent" },
  TRANSCRIPT_READY: { label: "文字起こし完了", tone: "success" },
  GENERATING_CHUNK_SUMMARIES: { label: "チャンク要約中", tone: "accent" },
  GENERATING_FINAL_MINUTES: { label: "議事録生成中", tone: "accent" },
  REVIEW_REQUIRED: { label: "確認が必要", tone: "warning" },
  DONE: { label: "完了", tone: "success" },
  FAILED: { label: "失敗", tone: "danger" },
  CANCELLED: { label: "キャンセル", tone: "neutral" },
};

export function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [createdJob, setCreatedJob] = useState<CreateJobResponse | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [minutes, setMinutes] = useState<MinutesResponse | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isBusy, setIsBusy] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [message, setMessage] = useState("音声ファイルを選択してください。");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const abortPollingRef = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const fileMetadata = useMemo(() => (selectedFile ? buildFileMetadata(selectedFile) : null), [selectedFile]);
  const activeStatus = jobStatus?.status ?? createdJob?.status ?? null;
  const statusDescriptor = getStatusDescriptor(activeStatus, {
    hasError: Boolean(errorMessage),
    hasFile: Boolean(selectedFile),
    isBusy,
  });
  const currentProgress = getCurrentProgress(uploadProgress, jobStatus, Boolean(createdJob), Boolean(selectedFile));
  const currentStepIndex = getCurrentStepIndex({
    createdJob,
    jobStatus,
    selectedFile,
    uploadProgress,
  });
  const supportedFormatsText = supportedAudioExtensions
    .map((extension) => extension.replace(".", "").toUpperCase())
    .join(" / ");

  useEffect(() => {
    return () => {
      abortPollingRef.current?.abort();
    };
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedFile) {
      setErrorMessage("音声ファイルを選択してください。");
      return;
    }
    const validation = validateAudioFile(selectedFile);
    if (!validation.valid) {
      setErrorMessage(validation.message || "音声ファイルを確認してください。");
      return;
    }

    abortPollingRef.current?.abort();
    const abortController = new AbortController();
    abortPollingRef.current = abortController;
    activeJobIdRef.current = null;
    setIsBusy(true);
    setErrorMessage(null);
    setUploadProgress(0);
    setJobStatus(null);
    setCreatedJob(null);
    setTranscript(null);
    setMinutes(null);

    try {
      setMessage("ジョブを作成しています。");
      const durationSeconds = await getAudioDurationSeconds(selectedFile);
      const job = await createJob(selectedFile, durationSeconds);
      activeJobIdRef.current = job.jobId;
      setCreatedJob(job);

      setMessage("Blob Storageへアップロードしています。");
      await uploadAudioFile(job.uploadUrl, selectedFile, setUploadProgress);
      if (activeJobIdRef.current !== job.jobId) {
        return;
      }

      setMessage("アップロード完了を通知しています。");
      await completeUpload(job.jobId, selectedFile);
      if (activeJobIdRef.current !== job.jobId) {
        return;
      }

      setMessage("ジョブ状態を確認しています。");
      await pollJobUntilTerminal(job.jobId, abortController.signal);
    } catch (error) {
      setErrorMessage(toUserMessage(error));
      setMessage("処理を完了できませんでした。設定またはファイルを確認してください。");
    } finally {
      setIsBusy(false);
    }
  }

  async function pollJobUntilTerminal(jobId: string, signal: AbortSignal) {
    let failureCount = 0;
    while (!signal.aborted && activeJobIdRef.current === jobId) {
      try {
        const status = await getJob(jobId);
        failureCount = 0;
        setJobStatus(status);
        setMessage(status.progress.message);
        await loadDerivedOutputsOnce(jobId, status);
        if (terminalStatuses.has(status.status)) {
          return;
        }

        async function loadDerivedOutputsOnce(jobId: string, status: JobStatusResponse) {
          if (
            frontendFeatures.transcriptApi &&
            shouldFetchTranscript(status.status, transcript !== null)
          ) {
            setTranscript(await getTranscript(jobId));
          }
          if (frontendFeatures.minutesApi && shouldFetchMinutes(status.status, minutes !== null)) {
            setMinutes(await getMinutes(jobId));
          }
        }
      } catch (error) {
        failureCount += 1;
        if (failureCount >= 3) {
          throw error;
        }
      }
      await wait(getJobPollingDelayMilliseconds(failureCount, document.visibilityState), signal);
    }
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (!file) {
      clearSelectedFile();
      return;
    }
    acceptSelectedFile(file);
  }

  function handleDragEnter(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (!isBusy) {
      setIsDragActive(true);
    }
  }

  function handleDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = isBusy ? "none" : "copy";
    if (!isBusy) {
      setIsDragActive(true);
    }
  }

  function handleDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (isNode(event.relatedTarget) && event.currentTarget.contains(event.relatedTarget)) {
      return;
    }
    setIsDragActive(false);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    setIsDragActive(false);
    if (isBusy) {
      return;
    }
    const file = event.dataTransfer.files.item(0);
    if (file) {
      acceptSelectedFile(file);
    }
  }

  function acceptSelectedFile(file: File) {
    const validation = validateAudioFile(file);
    if (!validation.valid) {
      clearSelectedFile(false);
      setErrorMessage(validation.message || "音声ファイルを確認してください。");
      setMessage("ファイル形式またはサイズを確認してください。");
      return;
    }

    abortPollingRef.current?.abort();
    activeJobIdRef.current = null;
    setSelectedFile(file);
    setCreatedJob(null);
    setJobStatus(null);
    setTranscript(null);
    setMinutes(null);
    setUploadProgress(0);
    setErrorMessage(null);
    setMessage("準備完了。アップロードを開始できます。");
  }

  function clearSelectedFile(resetMessage = true) {
    abortPollingRef.current?.abort();
    activeJobIdRef.current = null;
    setSelectedFile(null);
    setCreatedJob(null);
    setJobStatus(null);
    setTranscript(null);
    setMinutes(null);
    setUploadProgress(0);
    setErrorMessage(null);
    setIsDragActive(false);
    if (resetMessage) {
      setMessage("音声ファイルを選択してください。");
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  return (
    <main className="app-shell">
      <title>Azure 議事録 Studio</title>
      <meta
        name="description"
        content="Azureで音声ファイルから話者分離付き文字起こしと議事録を生成するMVPダッシュボード"
      />

      <section className="dashboard-shell" aria-labelledby="app-title">
        <header className="hero">
          <div className="hero__content">
            <p className="eyebrow">Azure Meeting Intelligence</p>
            <h1 id="app-title">{appTitle}</h1>
            <p className="hero-copy">
              録音済み音声をアップロードするだけで、話者分離付きの文字起こしから構造化された議事録までを一気通貫で生成します。
            </p>
            <div className="trust-row" aria-label="主な特徴">
              <span>日本語会議に最適化</span>
              <span>Blob Storage 直接アップロード</span>
              <span>要約・ToDo抽出</span>
            </div>
          </div>

          <aside className="hero-card" aria-label="ワークフロー概要">
            <span className="hero-card__label">MVP Workflow</span>
            <strong>Upload → Transcribe → Minutes</strong>
            <p>署名付きURLは画面に表示せず、ブラウザから安全に音声を転送します。</p>
            <div className="hero-card__bars" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </aside>
        </header>

        <section className="workspace-grid" aria-label="アップロードと処理状況">
          <form id="upload-panel" className="upload-card" onSubmit={(event) => void handleSubmit(event)}>
            <div className="section-heading">
              <p className="section-kicker">Input</p>
              <h2>音声アップロード</h2>
              <p>
                {supportedFormatsText} に対応。最大 {formatBytes(hardMaxAudioFileSizeBytes)} までの音声をドラッグ＆ドロップできます。
              </p>
            </div>

            <label
              className={`dropzone${isDragActive ? " dropzone--active" : ""}${isBusy ? " dropzone--disabled" : ""}`}
              htmlFor="audio-file-input"
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
              aria-disabled={isBusy}
            >
              <input
                ref={fileInputRef}
                id="audio-file-input"
                className="sr-only"
                type="file"
                accept={supportedAudioExtensions.join(",")}
                disabled={isBusy}
                onChange={handleFileInputChange}
                aria-describedby="upload-helper upload-error"
              />
              <span className="dropzone__glow" aria-hidden="true" />
              <span className="dropzone__icon" aria-hidden="true">↥</span>
              <span className="dropzone__title">
                {isDragActive ? "ここにドロップして追加" : selectedFile ? "別の音声に差し替える" : "音声ファイルをドラッグ＆ドロップ"}
              </span>
              <span id="upload-helper" className="dropzone__hint">
                クリックしてファイル選択もできます。会議名が分かるファイル名がおすすめです。
              </span>
            </label>

            {fileMetadata ? (
              <FileMetadataCard metadata={fileMetadata} isBusy={isBusy} onClear={() => clearSelectedFile()} />
            ) : (
              <div className="file-empty" aria-live="polite">
                <span aria-hidden="true">✦</span>
                <p>ファイルを選ぶと、サイズ・形式・更新日時をここで確認できます。</p>
              </div>
            )}

            <button className="primary-action" type="submit" disabled={!selectedFile || isBusy}>
              <span>{isBusy ? "処理中..." : "アップロードして処理開始"}</span>
              <span aria-hidden="true">→</span>
            </button>
          </form>

          <aside className="status-card" aria-live="polite" aria-label="処理ステータス">
            <div className="status-card__top">
              <div>
                <p className="section-kicker">Pipeline</p>
                <h2>処理ステータス</h2>
              </div>
              <span className={`status-badge status-badge--${statusDescriptor.tone}`}>
                {statusDescriptor.label}
              </span>
            </div>

            <p className="status-message">{message}</p>

            <div className="progress-meter" aria-hidden="true">
              <div className="progress-meter__header">
                <span>{jobStatus ? "バックエンド進捗" : "アップロード準備"}</span>
                <strong>{currentProgress}%</strong>
              </div>
              <div className="progress-meter__track">
                <span className="progress-meter__bar" style={{ inlineSize: `${currentProgress}%` }} />
              </div>
            </div>
            <progress className="sr-only" value={currentProgress} max={100}>
              {currentProgress}%
            </progress>

            <ol className="stepper" aria-label="処理ステップ">
              {processSteps.map((step, index) => {
                const stepState = getStepState(index, currentStepIndex, activeStatus, {
                  hasError: Boolean(errorMessage),
                  hasRunStarted: Boolean(selectedFile || createdJob || jobStatus),
                });
                return (
                  <li className={`stepper__item stepper__item--${stepState}`} key={step.label}>
                    <span className="stepper__dot" aria-hidden="true" />
                    <span>
                      <strong>{step.label}</strong>
                      <small>{step.description}</small>
                    </span>
                  </li>
                );
              })}
            </ol>

            <dl className="status-details">
              <div>
                <dt>アップロード</dt>
                <dd>{uploadProgress}%</dd>
              </div>
              <div>
                <dt>Job ID</dt>
                <dd className="mono">{createdJob?.jobId ?? "未作成"}</dd>
              </div>
              <div>
                <dt>処理ステップ</dt>
                <dd>{jobStatus?.progress.step ?? "待機中"}</dd>
              </div>
              <div>
                <dt>SAS有効期限</dt>
                <dd>{createdJob ? formatDateTime(createdJob.uploadExpiresAt) : "未発行"}</dd>
              </div>
            </dl>

            {errorMessage ? (
              <p id="upload-error" className="error" role="alert">
                {errorMessage}
              </p>
            ) : null}
          </aside>
        </section>

        <section className="results-section" aria-labelledby="results-title">
          <div className="section-heading section-heading--inline">
            <div>
              <p className="section-kicker">Outputs</p>
              <h2 id="results-title">生成結果プレビュー</h2>
            </div>
            <p>文字起こしと議事録の取得APIが有効化されると、ここに結果が展開されます。</p>
          </div>
          <div className="placeholder-grid">
            <TranscriptPanel jobStatus={jobStatus} transcript={transcript} />
            <MinutesPanel jobStatus={jobStatus} minutes={minutes} />
          </div>
        </section>
      </section>
    </main>
  );
}

function FileMetadataCard({
  metadata,
  isBusy,
  onClear,
}: {
  metadata: FileMetadata;
  isBusy: boolean;
  onClear: () => void;
}) {
  return (
    <section className="file-card" aria-label="選択中の音声ファイル">
      <div className="file-card__summary">
        <span className="file-avatar" aria-hidden="true">
          {metadata.extension.replace(".", "") || "AUD"}
        </span>
        <div>
          <h3>{metadata.name}</h3>
          <p>{metadata.size}・{metadata.type}</p>
        </div>
        <button className="ghost-button" type="button" onClick={onClear} disabled={isBusy}>
          解除
        </button>
      </div>
      <dl className="file-meta-grid">
        <div>
          <dt>形式</dt>
          <dd>{metadata.extension}</dd>
        </div>
        <div>
          <dt>サイズ</dt>
          <dd>{metadata.size}</dd>
        </div>
        <div>
          <dt>MIME</dt>
          <dd>{metadata.type}</dd>
        </div>
        <div>
          <dt>更新日時</dt>
          <dd>{metadata.lastModified}</dd>
        </div>
      </dl>
    </section>
  );
}

function wait(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timeout = window.setTimeout(resolve, milliseconds);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        resolve();
      },
      { once: true },
    );
  });
}

function toUserMessage(error: unknown): string {
  if (error instanceof ApiClientError || error instanceof UploadError) {
    return error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "処理中にエラーが発生しました。";
}

function buildFileMetadata(file: File): FileMetadata {
  const extension = getFileExtension(file.name);
  return {
    name: file.name,
    extension,
    size: formatBytes(file.size),
    type: file.type || "audio/*",
    lastModified: formatDateTime(file.lastModified),
  };
}

function getFileExtension(fileName: string): string {
  const dotIndex = fileName.lastIndexOf(".");
  return dotIndex >= 0 ? fileName.slice(dotIndex).toUpperCase() : "不明";
}

function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"] as const;
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const fractionDigits = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(fractionDigits)} ${units[unitIndex]}`;
}

function formatDateTime(value: number | string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("ja-JP", {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function getStatusDescriptor(
  status: JobStatus | null,
  options: { hasError: boolean; hasFile: boolean; isBusy: boolean },
): StatusDescriptor {
  if (options.hasError || status === "FAILED") {
    return { label: "エラー", tone: "danger" };
  }
  if (status) {
    return statusLabels[status];
  }
  if (options.isBusy) {
    return { label: "処理中", tone: "accent" };
  }
  if (options.hasFile) {
    return { label: "準備完了", tone: "info" };
  }
  return { label: "待機中", tone: "neutral" };
}

function getCurrentProgress(
  uploadProgress: number,
  jobStatus: JobStatusResponse | null,
  hasCreatedJob: boolean,
  hasSelectedFile: boolean,
): number {
  if (jobStatus) {
    return clampPercent(jobStatus.progress.percent);
  }
  if (hasCreatedJob) {
    return clampPercent(uploadProgress);
  }
  return hasSelectedFile ? 5 : 0;
}

function getCurrentStepIndex({
  createdJob,
  jobStatus,
  selectedFile,
  uploadProgress,
}: {
  createdJob: CreateJobResponse | null;
  jobStatus: JobStatusResponse | null;
  selectedFile: File | null;
  uploadProgress: number;
}): number {
  if (jobStatus) {
    switch (jobStatus.status) {
      case "CREATED":
      case "UPLOADING":
      case "UPLOADED":
        return 1;
      case "VALIDATING":
      case "PREPROCESSING":
      case "TRANSCRIBING":
      case "TRANSCRIPT_READY":
        return 2;
      case "GENERATING_CHUNK_SUMMARIES":
      case "GENERATING_FINAL_MINUTES":
        return 3;
      case "REVIEW_REQUIRED":
      case "DONE":
        return 4;
      case "FAILED":
      case "CANCELLED":
        return Math.min(4, Math.max(1, Math.ceil(jobStatus.progress.percent / 25)));
    }
  }
  if (createdJob) {
    return uploadProgress >= 100 ? 2 : 1;
  }
  return selectedFile ? 0 : 0;
}

function getStepState(
  index: number,
  currentIndex: number,
  status: JobStatus | null,
  options: { hasError: boolean; hasRunStarted: boolean },
): StepState {
  if (!options.hasRunStarted) {
    return "idle";
  }
  if ((options.hasError || status === "FAILED" || status === "CANCELLED") && index === currentIndex) {
    return "failed";
  }
  if (status === "DONE") {
    return "complete";
  }
  if (index < currentIndex) {
    return "complete";
  }
  if (index === currentIndex) {
    return "active";
  }
  return "idle";
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function isNode(value: EventTarget | null): value is Node {
  return value instanceof Node;
}
