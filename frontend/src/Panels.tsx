import { Activity, useRef, type KeyboardEvent, type ReactNode } from "react";

import type {
  JobStatusResponse,
  MinutesResponse,
  TranscriptResponse,
  VisualContextResponse,
} from "./apiClient";
import { frontendFeatures } from "./frontendFeatures";

export type ResultsTab = "minutes" | "transcript" | "visual";

type ResultsWorkspaceProps = {
  activeTab: ResultsTab;
  jobStatus: JobStatusResponse | null;
  minutes: MinutesResponse | null;
  transcript: TranscriptResponse | null;
  visualContext: VisualContextResponse | null;
  onTabChange: (tab: ResultsTab) => void;
};

type TranscriptPanelProps = {
  jobStatus: JobStatusResponse | null;
  transcript: TranscriptResponse | null;
};

type MinutesPanelProps = {
  jobStatus: JobStatusResponse | null;
  minutes: MinutesResponse | null;
};

type VisualContextPanelProps = {
  jobStatus: JobStatusResponse | null;
  visualContext: VisualContextResponse | null;
};

type PanelStatusTone = "muted" | "pending" | "ready" | "warning";

const resultsTabs: Array<{ id: ResultsTab; label: string; description: string }> = [
  { id: "minutes", label: "議事録", description: "要点を先に確認" },
  { id: "transcript", label: "文字起こし", description: "発言の確認に使う" },
  { id: "visual", label: "映像メモ", description: "動画理解の補足" },
];

export function getNextResultsTab(currentTab: ResultsTab, key: string): ResultsTab | null {
  const currentIndex = resultsTabs.findIndex((tab) => tab.id === currentTab);
  if (currentIndex < 0) {
    return null;
  }
  if (key === "Home") {
    return resultsTabs[0].id;
  }
  if (key === "End") {
    return resultsTabs[resultsTabs.length - 1].id;
  }
  if (key === "ArrowRight") {
    return resultsTabs[(currentIndex + 1) % resultsTabs.length].id;
  }
  if (key === "ArrowLeft") {
    return resultsTabs[(currentIndex - 1 + resultsTabs.length) % resultsTabs.length].id;
  }
  return null;
}

export function ResultsWorkspace({
  activeTab,
  jobStatus,
  minutes,
  transcript,
  visualContext,
  onTabChange,
}: ResultsWorkspaceProps) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function handleTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, currentTab: ResultsTab) {
    const nextTab = getNextResultsTab(currentTab, event.key);
    if (!nextTab) {
      return;
    }
    event.preventDefault();
    onTabChange(nextTab);
    const nextIndex = resultsTabs.findIndex((tab) => tab.id === nextTab);
    tabRefs.current[nextIndex]?.focus();
  }

  return (
    <div className="results-workspace">
      <div className="results-tabs" role="tablist" aria-label="生成結果の切り替え">
        {resultsTabs.map((tab, index) => {
          const isSelected = activeTab === tab.id;
          return (
            <button
              aria-controls={"results-panel-" + tab.id}
              aria-selected={isSelected}
              className={"results-tab" + (isSelected ? " results-tab--active" : "")}
              id={"results-tab-" + tab.id}
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, tab.id)}
              ref={(element) => {
                tabRefs.current[index] = element;
              }}
              role="tab"
              tabIndex={isSelected ? 0 : -1}
              type="button"
            >
              <span>{tab.label}</span>
              <small>{tab.description}</small>
            </button>
          );
        })}
      </div>

      <div className="results-workspace__panels">
        {/* React 19.2 Activity preserves panel state after a tab has been opened. */}
        <Activity mode={activeTab === "minutes" ? "visible" : "hidden"}>
          <div
            aria-labelledby="results-tab-minutes"
            className="results-tab-panel"
            hidden={activeTab !== "minutes"}
            id="results-panel-minutes"
            role="tabpanel"
          >
            <MinutesPanel jobStatus={jobStatus} minutes={minutes} />
          </div>
        </Activity>

        <Activity mode={activeTab === "transcript" ? "visible" : "hidden"}>
          <div
            aria-labelledby="results-tab-transcript"
            className="results-tab-panel results-tab-panel--supplementary"
            hidden={activeTab !== "transcript"}
            id="results-panel-transcript"
            role="tabpanel"
          >
            <TranscriptPanel jobStatus={jobStatus} transcript={transcript} />
          </div>
        </Activity>

        <Activity mode={activeTab === "visual" ? "visible" : "hidden"}>
          <div
            aria-labelledby="results-tab-visual"
            className="results-tab-panel results-tab-panel--supplementary"
            hidden={activeTab !== "visual"}
            id="results-panel-visual"
            role="tabpanel"
          >
            <VisualContextPanel jobStatus={jobStatus} visualContext={visualContext} />
          </div>
        </Activity>
      </div>
    </div>
  );
}

export function TranscriptPanel({ jobStatus, transcript }: TranscriptPanelProps) {
  const isReady = jobStatus
    ? ["TRANSCRIPT_READY", "GENERATING_CHUNK_SUMMARIES", "GENERATING_FINAL_MINUTES", "DONE"].includes(
        jobStatus.status,
      )
    : false;
  const hasTranscript = Boolean(isReady && transcript);

  return (
    <section className="panel result-card result-card--transcript" aria-labelledby="transcript-title">
      <PanelHeader
        eyebrow="補助資料"
        title="文字起こし"
        titleId="transcript-title"
        statusLabel={getTranscriptStatusLabel(isReady, hasTranscript)}
        statusTone={hasTranscript ? "ready" : frontendFeatures.transcriptApi ? "pending" : "muted"}
      />

      {!frontendFeatures.transcriptApi ? (
        <ResultPlaceholder
          variant="transcript"
          title="文字起こし表示の準備中"
          description="表示機能が有効になると、話者ごとの発話とタイムスタンプを確認できます。"
          bullets={["会議の流れを時系列で確認", "話者ラベルで発言を整理", "議事録の該当箇所を確認"]}
        />
      ) : !hasTranscript || !transcript ? (
        <ResultPlaceholder
          variant="transcript"
          title="文字起こし完了後に表示"
          description="発話ログは議事録レビューを補助する情報として、必要なときだけ参照できます。"
          bullets={["概要", "話者チップ", "発話一覧"]}
        />
      ) : (
        <div className="transcript-workspace">
          <TranscriptOverview transcript={transcript} />
          <SpeakerChips speakers={transcript.speakers} />
          <PhraseList phrases={transcript.phrases} />
        </div>
      )}
    </section>
  );
}

export function MinutesPanel({ jobStatus, minutes }: MinutesPanelProps) {
  const hasMinutes = Boolean(jobStatus?.status === "DONE" && minutes);

  return (
    <section className="panel result-card result-card--minutes" aria-labelledby="minutes-title">
      <PanelHeader
        eyebrow="メイン結果"
        title="議事録"
        titleId="minutes-title"
        statusLabel={getMinutesStatusLabel(jobStatus, hasMinutes)}
        statusTone={hasMinutes ? "ready" : frontendFeatures.minutesApi ? "pending" : "muted"}
      />

      {!frontendFeatures.minutesApi ? (
        <ResultPlaceholder
          variant="minutes"
          title="議事録表示の準備中"
          description="生成結果の取得機能が有効になると、サマリー・決定事項・アクションアイテムをカードで確認できます。"
          bullets={["要点を先に表示", "決定事項と担当者", "アクションアイテムを整理"]}
        />
      ) : !hasMinutes || !minutes ? (
        <ResultPlaceholder
          variant="minutes"
          title="議事録生成完了後に表示"
          description="会議の要点、決定事項、次のアクションを読みやすい順番で整理します。"
          bullets={["サマリー", "決定事項", "アクションアイテム"]}
        />
      ) : (
        <article className="minutes-document">
          <header className="minutes-brief">
            <p className="minutes-brief__eyebrow">会議ブリーフ</p>
            <h3>{minutes.title}</h3>
            <p>まずサマリー、次に決定事項とアクションアイテムを確認できます。</p>
          </header>

          <MinutesKpiGrid minutes={minutes} />

          <section className="minutes-summary-card" aria-labelledby="minutes-summary-title">
            <span>サマリー</span>
            <h3 id="minutes-summary-title">会議の要点</h3>
            <p>{minutes.summary || "サマリーはありません。"}</p>
          </section>

          <MinutesSection title="決定事項" emptyMessage="決定事項はありません。">
            {minutes.decisions.map((decision, index) => (
              <li key={decision.text + "-" + index}>
                <strong>{decision.text}</strong>
                <span className="meta-line">担当者: {decision.owner || "未設定"}</span>
                <Evidence timestamps={decision.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="アクションアイテム" emptyMessage="アクションアイテムはありません。">
            {minutes.actionItems.map((item, index) => (
              <li key={item.task + "-" + index}>
                <strong>{item.task}</strong>
                <span className="meta-line">
                  担当者: {item.owner || "未設定"} / 期限: {item.dueDate || "未設定"}
                </span>
                <Evidence timestamps={item.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="主要トピック" emptyMessage="トピックはありません。">
            {minutes.topics.map((topic, index) => (
              <li key={topic.title + "-" + index}>
                <strong>{topic.title}</strong>
                <p>{topic.discussion}</p>
                <Evidence timestamps={topic.evidenceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="未解決の論点" emptyMessage="未解決の論点はありません。">
            {minutes.openQuestions.map((question, index) => (
              <li key={question.text + "-" + index}>
                <strong>{question.text}</strong>
                <span className="meta-line">担当者: {question.owner || "未設定"}</span>
                <Evidence timestamps={question.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="リスク" emptyMessage="リスクはありません。">
            {minutes.risks.map((risk, index) => (
              <li key={risk.text + "-" + index}>
                <strong>{risk.text}</strong>
                <span className="meta-line">重要度: {risk.severity}</span>
                <Evidence timestamps={risk.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>
        </article>
      )}
    </section>
  );
}

function PanelHeader({
  eyebrow,
  statusLabel,
  statusTone,
  title,
  titleId,
}: {
  eyebrow: string;
  statusLabel: string;
  statusTone: PanelStatusTone;
  title: string;
  titleId: string;
}) {
  return (
    <div className="panel-header">
      <div>
        <p className="panel-kicker">{eyebrow}</p>
        <h2 id={titleId}>{title}</h2>
      </div>
      <span className={"panel-status panel-status--" + statusTone}>{statusLabel}</span>
    </div>
  );
}

export function VisualContextPanel({ jobStatus, visualContext }: VisualContextPanelProps) {
  const isCuRoute = jobStatus?.processingRoute === "contentUnderstanding";
  const hasVisualContext = Boolean(isCuRoute && visualContext);
  const summary = visualContext ? extractFieldString(visualContext.fields, "Summary") : null;

  return (
    <section className="panel result-card result-card--visual" aria-labelledby="visual-title">
      <PanelHeader
        eyebrow="実験機能"
        title="映像メモ"
        titleId="visual-title"
        statusLabel={getVisualStatusLabel(jobStatus, hasVisualContext)}
        statusTone={hasVisualContext ? "ready" : isCuRoute ? "pending" : "muted"}
      />

      {!isCuRoute ? (
        <ResultPlaceholder
          variant="visual"
          title="動画理解モードで表示"
          description="標準経路では映像を議事録の根拠に使いません。動画理解（実験）経路を選ぶと、映像補足を確認できます。"
          bullets={["key frameの時刻", "カメラショット", "映像由来の補足メモ"]}
        />
      ) : !hasVisualContext || !visualContext ? (
        <ResultPlaceholder
          variant="visual"
          title="映像メモを生成中"
          description="Content Understanding の解析結果が保存されると、映像由来の補足情報を表示します。"
          bullets={["議事録本文とは分離", "人物識別はしない", "映像由来として確認"]}
        />
      ) : (
        <div className="visual-workspace">
          <section className="transcript-card" aria-labelledby="visual-summary-title">
            <div className="panel-subheader">
              <div>
                <h3 id="visual-summary-title">映像補足サマリー</h3>
                <p>議事録本文とは別の参考情報です。決定事項やToDoの根拠には自動採用しません。</p>
              </div>
            </div>
            <p className="visual-summary">{summary || "映像補足サマリーはありません。"}</p>
          </section>
          <div className="transcript-summary" aria-label="映像メモKPI">
            <MetricTile label="key frames" value={formatCount(visualContext.keyFrameTimesMs?.length || 0)} />
            <MetricTile label="camera shots" value={formatCount(visualContext.cameraShotTimesMs?.length || 0)} />
            <MetricTile label="duration" value={formatMilliseconds(visualContext.endTimeMs || 0)} />
          </div>
          <TimeList title="Key frame timestamps" values={visualContext.keyFrameTimesMs || []} />
          <TimeList title="Camera shot timestamps" values={visualContext.cameraShotTimesMs || []} />
        </div>
      )}
    </section>
  );
}

function ResultPlaceholder({
  bullets,
  description,
  title,
  variant,
}: {
  bullets: string[];
  description: string;
  title: string;
  variant: "minutes" | "transcript" | "visual";
}) {
  return (
    <div className={"result-placeholder result-placeholder--" + variant}>
      <div className="placeholder-visual" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <div>
        <h3>{title}</h3>
        <p>{description}</p>
        <ul className="feature-list">
          {bullets.map((bullet) => (
            <li key={bullet}>{bullet}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function TranscriptOverview({ transcript }: { transcript: TranscriptResponse }) {
  return (
    <section className="transcript-card transcript-overview" aria-labelledby="transcript-overview-title">
      <div className="panel-subheader">
        <div>
          <h3 id="transcript-overview-title">文字起こし概要</h3>
          <p>議事録の確認に必要な全体量を把握できます。</p>
        </div>
      </div>
      <div className="transcript-summary" aria-label="文字起こし概要KPI">
        <MetricTile label="音声長" value={formatMilliseconds(transcript.durationMilliseconds)} />
        <MetricTile label="話者" value={transcript.speakers.length + "名"} />
        <MetricTile label="発話" value={transcript.phrases.length + "件"} />
      </div>
    </section>
  );
}

function SpeakerChips({ speakers }: { speakers: TranscriptResponse["speakers"] }) {
  return (
    <section className="transcript-card speaker-mapping" aria-labelledby="speaker-list-title">
      <div className="panel-subheader">
        <div>
          <h3 id="speaker-list-title">話者</h3>
          {!frontendFeatures.speakerMappingSave ? <p>現在は自動ラベルで表示します。話者名の編集は今後対応予定です。</p> : null}
        </div>
      </div>
      {speakers.length > 0 ? (
        <div className="speaker-grid" role="list">
          {speakers.map((speaker) => {
            const primaryName = speaker.displayName || speaker.speakerLabel;
            return (
              <div className="speaker-chip" key={speaker.speakerLabel} role="listitem">
                <span className="speaker-chip__avatar" aria-hidden="true">
                  {formatSpeakerBadge(speaker.speakerLabel)}
                </span>
                <span className="speaker-chip__content">
                  <strong>{primaryName}</strong>
                  <small>
                    {speaker.displayName ? speaker.speakerLabel + "・" : "表示名未設定・"}
                    {speaker.phraseCount}件の発話
                  </small>
                </span>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="empty-state">話者情報はまだありません。</p>
      )}
    </section>
  );
}

function PhraseList({ phrases }: { phrases: TranscriptResponse["phrases"] }) {
  return (
    <section className="transcript-card transcript-phrase-card" aria-labelledby="phrase-list-title">
      <div className="panel-subheader">
        <div>
          <h3 id="phrase-list-title">発話一覧</h3>
          <p>長い文字起こしはスクロール領域内で確認できます。</p>
        </div>
      </div>
      {phrases.length > 0 ? (
        <ol className="phrase-list" aria-label="発話一覧">
          {phrases.map((phrase) => {
            const confidence = formatConfidence(phrase.confidence);
            return (
              <li key={phrase.phraseId}>
                <time dateTime={"PT" + Math.round(phrase.offsetMilliseconds / 1000) + "S"}>
                  {phrase.startTimeText}
                </time>
                <div>
                  <strong>{phrase.displayName || phrase.speakerLabel}</strong>
                  {confidence ? <small>信頼度 {confidence}</small> : null}
                  <span>{phrase.text}</span>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="empty-state">発話データはまだありません。</p>
      )}
    </section>
  );
}

function TimeList({ title, values }: { title: string; values: number[] }) {
  return (
    <section className="transcript-card" aria-labelledby={title.replace(/\s+/g, "-").toLowerCase()}>
      <div className="panel-subheader">
        <div>
          <h3 id={title.replace(/\s+/g, "-").toLowerCase()}>{title}</h3>
          <p>動画の時刻に基づく補足情報です。</p>
        </div>
      </div>
      {values.length > 0 ? (
        <div className="time-chip-list">
          {values.slice(0, 20).map((value) => (
            <span key={value}>{formatMilliseconds(value)}</span>
          ))}
        </div>
      ) : (
        <p className="empty-state">時刻情報はありません。</p>
      )}
    </section>
  );
}

function MinutesKpiGrid({ minutes }: { minutes: MinutesResponse }) {
  const kpis = [
    { label: "決定事項", value: formatCount(minutes.decisions.length), helper: "合意したこと" },
    { label: "アクションアイテム", value: formatCount(minutes.actionItems.length), helper: "次にやること" },
    { label: "未解決の論点", value: formatCount(minutes.openQuestions.length), helper: "確認が必要" },
    { label: "リスク", value: formatCount(minutes.risks.length), helper: "注意点" },
  ];

  return (
    <div className="minutes-kpi-grid" aria-label="議事録KPI">
      {kpis.map((kpi) => (
        <div className="minutes-kpi-card" key={kpi.label}>
          <strong>{kpi.value}</strong>
          <span>{kpi.label}</span>
          <small>{kpi.helper}</small>
        </div>
      ))}
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-tile">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function MinutesSection({
  children,
  emptyMessage,
  title,
}: {
  children: ReactNode;
  emptyMessage: string;
  title: string;
}) {
  const childArray = Array.isArray(children) ? children : [children];
  const hasItems = childArray.some(Boolean);

  return (
    <section className="minutes-block">
      <h3>{title}</h3>
      {hasItems ? <ul className="minutes-list">{children}</ul> : <p className="empty-state">{emptyMessage}</p>}
    </section>
  );
}

function Evidence({ timestamps }: { timestamps: string[] }) {
  return <small className="evidence">該当箇所: {formatTimestampList(timestamps)}</small>;
}

function getTranscriptStatusLabel(isReady: boolean, hasTranscript: boolean): string {
  if (!frontendFeatures.transcriptApi) {
    return "準備中";
  }
  if (hasTranscript) {
    return "表示可能";
  }
  return isReady ? "取得中" : "待機中";
}

function getMinutesStatusLabel(jobStatus: JobStatusResponse | null, hasMinutes: boolean): string {
  if (!frontendFeatures.minutesApi) {
    return "準備中";
  }
  if (hasMinutes) {
    return "表示可能";
  }
  return jobStatus?.status === "DONE" ? "取得中" : "待機中";
}

function getVisualStatusLabel(
  jobStatus: JobStatusResponse | null,
  hasVisualContext: boolean,
): string {
  if (hasVisualContext) {
    return "表示可能";
  }
  if (jobStatus?.processingRoute === "contentUnderstanding") {
    return jobStatus.status === "FAILED" ? "未生成" : "生成中";
  }
  return "対象外";
}

function extractFieldString(fields: VisualContextResponse["fields"], fieldName: string): string | null {
  const field = fields?.[fieldName];
  if (typeof field !== "object" || field === null || !("valueString" in field)) {
    return null;
  }
  const value = (field as { valueString?: unknown }).valueString;
  return typeof value === "string" ? value : null;
}

function formatMilliseconds(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.round(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return hours + "時間" + minutes + "分";
  }
  return minutes + "分" + seconds + "秒";
}

function formatConfidence(confidence: number | null): string | null {
  if (confidence === null) {
    return null;
  }
  const percentage = confidence <= 1 ? confidence * 100 : confidence;
  return Math.round(percentage) + "%";
}

function formatCount(count: number): string {
  return count + "件";
}

function formatSpeakerBadge(label: string): string {
  const numericPart = label.match(/\d+/)?.[0];
  if (numericPart) {
    return "S" + numericPart;
  }
  return label.slice(0, 2).toUpperCase();
}

function formatTimestampList(timestamps: string[]): string {
  return timestamps.length > 0 ? timestamps.join(" / ") : "該当箇所未設定";
}
