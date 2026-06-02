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
  type MinutesModel,
  type MinutesResponse,
  type ProcessingRoute,
  type TranscriptResponse,
} from "./apiClient";
import { appTitle, heroCopy, heroHeadline, supportedAudioExtensions } from "./appConfig";
import {
  getAudioDurationSeconds,
  hardMaxAudioFileSizeBytes,
  maxAudioDurationSeconds,
  validateAudioFile,
} from "./fileValidation";
import { frontendFeatures } from "./frontendFeatures";
import {
  getJobPollingDelayMilliseconds,
  shouldFetchMinutes,
  shouldFetchTranscript,
} from "./jobPolling";
import { ResultsWorkspace, type ResultsTab } from "./Panels";

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
  { label: "アップロード", description: "音声を安全に転送" },
  { label: "文字起こし", description: "話者分離と整形" },
  { label: "議事録生成", description: "要約・アクション抽出" },
  { label: "完了", description: "レビュー可能" },
] as const;

const minutesModelOptions: Array<{
  id: MinutesModel;
  label: string;
  description: string;
}> = [
  {
    id: "fast",
    label: "高速",
    description: "GPT-5.4 miniで待ち時間を短縮。デモや通常会議向け。",
  },
  {
    id: "quality",
    label: "高品質",
    description: "GPT-5.4で精度を優先。重要会議のレビュー向け。",
  },
];

const processingRouteOptions: Array<{
  id: ProcessingRoute;
  label: string;
  description: string;
  badge?: string;
}> = [
  {
    id: "stable",
    label: "標準",
    description: "現行の安定経路。音声抽出、話者分離、議事録生成を既存方式で実行します。",
  },
  {
    id: "contentUnderstanding",
    label: "動画理解",
    description: "Content Understandingで映像補足も取得する実験経路です。標準より時間がかかる場合があります。",
    badge: "実験",
  },
];

const statusLabels: Record<JobStatus, StatusDescriptor> = {
  CREATED: { label: "準備中", tone: "info" },
  UPLOADING: { label: "アップロード中", tone: "accent" },
  UPLOADED: { label: "アップロード完了", tone: "info" },
  VALIDATING: { label: "検証中", tone: "accent" },
  PREPROCESSING: { label: "前処理中", tone: "accent" },
  TRANSCRIBING: { label: "文字起こし中", tone: "accent" },
  TRANSCRIPT_READY: { label: "文字起こし完了", tone: "success" },
  GENERATING_CHUNK_SUMMARIES: { label: "要点整理中", tone: "accent" },
  GENERATING_FINAL_MINUTES: { label: "議事録生成中", tone: "accent" },
  REVIEW_REQUIRED: { label: "確認が必要", tone: "warning" },
  DONE: { label: "完了", tone: "success" },
  FAILED: { label: "失敗", tone: "danger" },
  CANCELLED: { label: "キャンセル済み", tone: "neutral" },
};

export function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [createdJob, setCreatedJob] = useState<CreateJobResponse | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [minutes, setMinutes] = useState<MinutesResponse | null>(null);
  const [minutesModel, setMinutesModel] = useState<MinutesModel>("fast");
  const [processingRoute, setProcessingRoute] = useState<ProcessingRoute>("stable");
  const [activeResultsTab, setActiveResultsTab] = useState<ResultsTab>("minutes");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [runStartedAtMs, setRunStartedAtMs] = useState<number | null>(null);
  const [runFinishedAtMs, setRunFinishedAtMs] = useState<number | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isDragActive, setIsDragActive] = useState(false);
  const [message, setMessage] = useState("音声ファイルを選択してください。");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const abortPollingRef = useRef<AbortController | null>(null);
  const completedJobTabSelectionRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const fileMetadata = useMemo(() => (selectedFile ? buildFileMetadata(selectedFile) : null), [selectedFile]);
  const activeStatus = jobStatus?.status ?? createdJob?.status ?? null;
  const isTerminalStatus = activeStatus !== null && terminalStatuses.has(activeStatus);
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

  useEffect(() => {
    if (jobStatus?.status !== "DONE" || completedJobTabSelectionRef.current === jobStatus.jobId) {
      return;
    }
    // The completed workspace opens minutes-first so users land on the polished deliverable.
    setActiveResultsTab("minutes");
    completedJobTabSelectionRef.current = jobStatus.jobId;
  }, [jobStatus?.jobId, jobStatus?.status]);

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
    completedJobTabSelectionRef.current = null;
    setIsBusy(true);
    setErrorMessage(null);
    setUploadProgress(0);
    setRunStartedAtMs(Date.now());
    setRunFinishedAtMs(null);
    setJobStatus(null);
    setCreatedJob(null);
    setTranscript(null);
    setMinutes(null);
    setActiveResultsTab("minutes");

    try {
      setMessage("ジョブを作成しています。");
      const durationSeconds = await getAudioDurationSeconds(selectedFile);
      if (durationSeconds !== null && durationSeconds > maxAudioDurationSeconds) {
        setErrorMessage("120分を超える音声は対応範囲外です。音声を分割してからアップロードしてください。");
        setMessage("音声の長さを確認してください。");
        setRunStartedAtMs(null);
        setRunFinishedAtMs(null);
        return;
      }
      const job = await createJob(selectedFile, durationSeconds, minutesModel, processingRoute);
      activeJobIdRef.current = job.jobId;
      setCreatedJob(job);

      setMessage("音声ファイルをアップロードしています。");
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
      setRunFinishedAtMs(Date.now());
      setErrorMessage(toUserMessage(error));
      setMessage("処理を完了できませんでした。設定またはファイルを確認してください。");
    } finally {
      setIsBusy(false);
    }
  }

  async function pollJobUntilTerminal(jobId: string, signal: AbortSignal) {
    let failureCount = 0;
    let transcriptLoaded = transcript !== null;
    let minutesLoaded = minutes !== null;
    while (!signal.aborted && activeJobIdRef.current === jobId) {
      try {
        const status = await getJob(jobId);
        failureCount = 0;
        setJobStatus(status);
        setMessage(status.progress.message);
        await loadDerivedOutputsOnce(jobId, status);
        if (terminalStatuses.has(status.status)) {
          setRunFinishedAtMs(Date.now());
          if (status.status === "FAILED") {
            setErrorMessage(status.error?.message || "処理に失敗しました。");
          }
          if (status.status === "CANCELLED") {
            setErrorMessage("処理がキャンセルされました。");
          }
          return;
        }

        async function loadDerivedOutputsOnce(jobId: string, status: JobStatusResponse) {
          if (
            frontendFeatures.transcriptApi &&
            status.outputs.transcriptReady &&
            shouldFetchTranscript(status.status, transcriptLoaded)
          ) {
            setTranscript(await getTranscript(jobId));
            transcriptLoaded = true;
          }
          if (
            frontendFeatures.minutesApi &&
            status.outputs.minutesReady &&
            shouldFetchMinutes(status.status, minutesLoaded)
          ) {
            setMinutes(await getMinutes(jobId));
            minutesLoaded = true;
          }
        }
      } catch (error) {
        failureCount += 1;
        if (failureCount >= 3) {
          setRunFinishedAtMs(Date.now());
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
    completedJobTabSelectionRef.current = null;
    setSelectedFile(file);
    setCreatedJob(null);
    setJobStatus(null);
    setTranscript(null);
    setMinutes(null);
    setActiveResultsTab("minutes");
    setUploadProgress(0);
    setRunStartedAtMs(null);
    setRunFinishedAtMs(null);
    setErrorMessage(null);
    setMessage("準備完了。アップロードを開始できます。");
  }

  function clearSelectedFile(resetMessage = true) {
    abortPollingRef.current?.abort();
    activeJobIdRef.current = null;
    completedJobTabSelectionRef.current = null;
    setSelectedFile(null);
    setCreatedJob(null);
    setJobStatus(null);
    setTranscript(null);
    setMinutes(null);
    setActiveResultsTab("minutes");
    setUploadProgress(0);
    setRunStartedAtMs(null);
    setRunFinishedAtMs(null);
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
      <title>{appTitle}</title>
      <meta
        name="description"
        content="会議録音をアップロードするだけで、要点・決定事項・アクションアイテムを整理した議事録を生成します。"
      />

      <section className="dashboard-shell" aria-labelledby="app-title">
        <header className="hero">
          <div className="hero__content">
            <p className="eyebrow">{appTitle}</p>
            <h1 id="app-title">{heroHeadline}</h1>
            <p className="hero-copy">{heroCopy}</p>
            <div className="trust-row" aria-label="主な特徴">
              <span>日本語会議に最適化</span>
              <span>文字起こしと議事録を一体生成</span>
              <span>アクションアイテムを自動整理</span>
            </div>
          </div>

          <aside className="hero-card" aria-label="ワークフロー概要">
            <span className="hero-card__label">3ステップで完成</span>
            <strong>録音を選ぶ → 生成を待つ → 議事録を確認</strong>
            <p>議事録を先に読み、必要なときだけ発話ログで該当箇所を確認できます。</p>
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
              <p className="section-kicker">録音</p>
              <h2>音声アップロード</h2>
              <p>
                {supportedFormatsText} に対応。最大 {formatBytes(hardMaxAudioFileSizeBytes)} / 120分までの音声をドラッグ＆ドロップできます。
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

            <fieldset className="model-selector" disabled={isBusy}>
              <legend>処理方式</legend>
              <p>標準経路は既存の安定処理です。動画理解は比較デモ用の実験経路です。</p>
              <div className="model-selector__options">
                {processingRouteOptions.map((option) => {
                  const isDisabled =
                    option.id === "contentUnderstanding" &&
                    !frontendFeatures.contentUnderstandingRoute;
                  return (
                    <label
                      className={"model-option" + (isDisabled ? " model-option--disabled" : "")}
                      key={option.id}
                    >
                      <input
                        checked={processingRoute === option.id}
                        disabled={isDisabled}
                        name="processing-route"
                        onChange={() => setProcessingRoute(option.id)}
                        type="radio"
                        value={option.id}
                      />
                      <span>
                        <strong>
                          {option.label}
                          {option.badge ? <em>{option.badge}</em> : null}
                        </strong>
                        <small>{option.description}</small>
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>

            <fieldset className="model-selector" disabled={isBusy}>
              <legend>議事録生成モード</legend>
              <p>速度重視か品質重視かを選択できます。話者分離の文字起こしはどちらも同じ精度で処理します。</p>
              <div className="model-selector__options">
                {minutesModelOptions.map((option) => (
                  <label className="model-option" key={option.id}>
                    <input
                      checked={minutesModel === option.id}
                      name="minutes-model"
                      onChange={() => setMinutesModel(option.id)}
                      type="radio"
                      value={option.id}
                    />
                    <span>
                      <strong>{option.label}</strong>
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <button className="primary-action" type="submit" disabled={!selectedFile || isBusy}>
              <span>{isBusy ? "処理中..." : "アップロードして処理開始"}</span>
              <span aria-hidden="true">→</span>
            </button>
          </form>

          <aside className="status-card" aria-label="処理ステータス">
            <div className="status-card__top">
              <div>
                <p className="section-kicker">進行状況</p>
                <h2>処理ステータス</h2>
              </div>
              <span className={`status-badge status-badge--${statusDescriptor.tone}`}>
                {statusDescriptor.label}
              </span>
            </div>

            <p className="status-message" aria-live="polite">{message}</p>

            <div className="progress-meter" aria-hidden="true">
              <div className="progress-meter__header">
                <span>{jobStatus ? "生成進捗" : "アップロード準備"}</span>
                <strong>{currentProgress}%</strong>
              </div>
              <div className="progress-meter__track">
                <span className="progress-meter__bar" style={{ inlineSize: `${currentProgress}%` }} />
              </div>
            </div>
            <progress
              aria-label="処理進捗"
              aria-valuetext={`${currentProgress}% - ${statusDescriptor.label}`}
              className="sr-only"
              value={currentProgress}
              max={100}
            >
              {currentProgress}%
            </progress>

            <ol className="stepper" aria-label="処理ステップ">
              {processSteps.map((step, index) => {
                const stepState = getStepState(index, currentStepIndex, activeStatus, {
                  hasError: Boolean(errorMessage),
                  hasRunStarted: Boolean(selectedFile || createdJob || jobStatus),
                });
                return (
                  <li
                    aria-current={stepState === "active" ? "step" : undefined}
                    className={`stepper__item stepper__item--${stepState}`}
                    key={step.label}
                  >
                    <span className="stepper__dot" aria-hidden="true" />
                    <span>
                      <strong>{step.label}</strong>
                      <small>{step.description}</small>
                      <span className="sr-only">状態: {getStepStateLabel(stepState)}</span>
                    </span>
                  </li>
                );
              })}
            </ol>

            <dl className="status-details status-details--primary">
              <div>
                <dt>アップロード</dt>
                <dd>{uploadProgress}%</dd>
              </div>
              <div>
                <dt>経過時間</dt>
                <dd>
                  <ElapsedTime
                    finishedAtMs={runFinishedAtMs}
                    isRunning={Boolean(runStartedAtMs && isBusy && !isTerminalStatus)}
                    startedAtMs={runStartedAtMs}
                  />
                </dd>
              </div>
              <div>
                <dt>現在の処理</dt>
                <dd>{jobStatus?.progress.step ?? "待機中"}</dd>
              </div>
              <div>
                <dt>議事録モード</dt>
                <dd>{getMinutesModelLabel(jobStatus?.minutesModel ?? minutesModel)}</dd>
              </div>
              <div>
                <dt>処理方式</dt>
                <dd>{getProcessingRouteLabel(jobStatus?.processingRoute ?? processingRoute)}</dd>
              </div>
              <div>
                <dt>文字起こし</dt>
                <dd>{getTranscriptAvailabilityLabel(jobStatus, transcript)}</dd>
              </div>
            </dl>

            <details className="developer-details">
              <summary>開発者向け情報</summary>
              <dl className="status-details status-details--developer">
                <div>
                  <dt>ジョブID</dt>
                  <dd className="mono">{createdJob?.jobId ?? "未作成"}</dd>
                </div>
                <div>
                  <dt>アップロードURL期限</dt>
                  <dd>{createdJob ? formatDateTime(createdJob.uploadExpiresAt) : "未発行"}</dd>
                </div>
              </dl>
            </details>

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
              <p className="section-kicker">結果</p>
              <h2 id="results-title">生成結果プレビュー</h2>
            </div>
            <p>完了後は議事録を先頭に表示します。文字起こしは確認用タブとして必要な箇所だけ参照できます。</p>
          </div>
          <ResultsWorkspace
            activeTab={activeResultsTab}
            jobStatus={jobStatus}
            minutes={minutes}
            transcript={transcript}
            onTabChange={setActiveResultsTab}
          />
        </section>
      </section>
    </main>
  );
}

function getStepStateLabel(stepState: StepState): string {
  switch (stepState) {
    case "active":
      return "進行中";
    case "complete":
      return "完了";
    case "failed":
      return "失敗";
    case "idle":
      return "未開始";
  }
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
          <dt>種類</dt>
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

function ElapsedTime({
  finishedAtMs,
  isRunning,
  startedAtMs,
}: {
  finishedAtMs: number | null;
  isRunning: boolean;
  startedAtMs: number | null;
}) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!startedAtMs || !isRunning) {
      return;
    }
    setNowMs(Date.now());
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(intervalId);
  }, [isRunning, startedAtMs]);

  if (!startedAtMs) {
    return <span>未開始</span>;
  }

  const endMs = finishedAtMs ?? nowMs;
  return <span>{formatElapsedDuration(Math.max(0, endMs - startedAtMs))}</span>;
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

function getMinutesModelLabel(minutesModel: MinutesModel): string {
  switch (minutesModel) {
    case "fast":
      return "高速";
    case "quality":
      return "高品質";
  }
}

function getProcessingRouteLabel(processingRoute: ProcessingRoute): string {
  switch (processingRoute) {
    case "stable":
      return "標準";
    case "contentUnderstanding":
      return "動画理解（実験）";
  }
}

function getTranscriptAvailabilityLabel(
  jobStatus: JobStatusResponse | null,
  transcript: TranscriptResponse | null,
): string {
  if (transcript) {
    return "先に確認できます";
  }
  if (jobStatus?.outputs.transcriptReady) {
    return "取得中";
  }
  if (jobStatus?.status === "TRANSCRIBING" || jobStatus?.status === "PREPROCESSING") {
    return "処理中";
  }
  if (jobStatus) {
    return "準備中";
  }
  return "未開始";
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

function formatElapsedDuration(milliseconds: number): string {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
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
