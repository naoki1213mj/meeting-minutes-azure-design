import type { JobStatusResponse, MinutesResponse, TranscriptResponse } from "./apiClient";
import { frontendFeatures } from "./frontendFeatures";

type TranscriptPanelProps = {
  jobStatus: JobStatusResponse | null;
  transcript: TranscriptResponse | null;
};

type MinutesPanelProps = {
  jobStatus: JobStatusResponse | null;
  minutes: MinutesResponse | null;
};

type PanelStatusTone = "muted" | "pending" | "ready" | "warning";

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
        eyebrow="Output 01"
        title="話者分離文字起こし"
        titleId="transcript-title"
        statusLabel={getTranscriptStatusLabel(isReady, hasTranscript)}
        statusTone={hasTranscript ? "ready" : frontendFeatures.transcriptApi ? "pending" : "muted"}
      />

      {!frontendFeatures.transcriptApi ? (
        <ResultPlaceholder
          variant="transcript"
          title="文字起こし取得APIの接続待ち"
          description="バックエンドの取得APIが有効になると、話者ごとの発話ログとタイムスタンプがここに表示されます。"
          bullets={["話者ラベルと表示名", "タイムスタンプ付き発話", "信頼度プレビュー"]}
        />
      ) : !hasTranscript || !transcript ? (
        <ResultPlaceholder
          variant="transcript"
          title="文字起こし完了後に自動表示"
          description="アップロード後、話者分離と正規化が完了すると発話単位で確認できます。"
          bullets={["処理状況に合わせて更新", "会議の流れを時系列で確認", "後続フェーズで話者名編集に対応"]}
        />
      ) : (
        <>
          <div className="transcript-summary" aria-label="文字起こし概要">
            <MetricTile label="音声長" value={formatMilliseconds(transcript.durationMilliseconds)} />
            <MetricTile label="話者" value={`${transcript.speakers.length}名`} />
            <MetricTile label="発話" value={`${transcript.phrases.length}件`} />
          </div>

          <SpeakerMappingPreview speakers={transcript.speakers} />

          {transcript.phrases.length > 0 ? (
            <ol className="phrase-list">
              {transcript.phrases.map((phrase) => {
                const confidence = formatConfidence(phrase.confidence);
                return (
                  <li key={phrase.phraseId}>
                    <time dateTime={`PT${Math.round(phrase.offsetMilliseconds / 1000)}S`}>
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
        </>
      )}
    </section>
  );
}

export function MinutesPanel({ jobStatus, minutes }: MinutesPanelProps) {
  const hasMinutes = Boolean(jobStatus?.status === "DONE" && minutes);

  return (
    <section className="panel result-card result-card--minutes" aria-labelledby="minutes-title">
      <PanelHeader
        eyebrow="Output 02"
        title="AI議事録"
        titleId="minutes-title"
        statusLabel={getMinutesStatusLabel(jobStatus, hasMinutes)}
        statusTone={hasMinutes ? "ready" : frontendFeatures.minutesApi ? "pending" : "muted"}
      />

      {!frontendFeatures.minutesApi ? (
        <ResultPlaceholder
          variant="minutes"
          title="議事録取得APIの接続待ち"
          description="DONE後に議事録JSONを取得できるようになると、サマリー・決定事項・ToDoをカードで確認できます。"
          bullets={["要約とトピック整理", "決定事項と担当者", "アクションアイテム抽出"]}
        />
      ) : !hasMinutes || !minutes ? (
        <ResultPlaceholder
          variant="minutes"
          title="議事録生成完了後に表示"
          description="文字起こしをもとに、会議の要点と次のアクションを構造化します。"
          bullets={["生成状況をステータスで追跡", "根拠タイムスタンプを表示", "レビューしやすいカードUI"]}
        />
      ) : (
        <article className="minutes-document">
          <div className="minutes-summary-card">
            <span>Meeting brief</span>
            <h3>{minutes.title}</h3>
            <p>{minutes.summary}</p>
          </div>

          <MinutesSection title="主要トピック" emptyMessage="トピックはありません。">
            {minutes.topics.map((topic, index) => (
              <li key={`${topic.title}-${index}`}>
                <strong>{topic.title}</strong>
                <p>{topic.discussion}</p>
                <Evidence timestamps={topic.evidenceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="決定事項" emptyMessage="決定事項はありません。">
            {minutes.decisions.map((decision, index) => (
              <li key={`${decision.text}-${index}`}>
                <strong>{decision.text}</strong>
                <span className="meta-line">オーナー: {decision.owner || "未設定"}</span>
                <Evidence timestamps={decision.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="ToDo" emptyMessage="ToDoはありません。">
            {minutes.actionItems.map((item, index) => (
              <li key={`${item.task}-${index}`}>
                <strong>{item.task}</strong>
                <span className="meta-line">
                  担当: {item.owner || "未設定"} / 期限: {item.dueDate || "未設定"}
                </span>
                <Evidence timestamps={item.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="未解決の論点" emptyMessage="未解決の論点はありません。">
            {minutes.openQuestions.map((question, index) => (
              <li key={`${question.text}-${index}`}>
                <strong>{question.text}</strong>
                <span className="meta-line">オーナー: {question.owner || "未設定"}</span>
                <Evidence timestamps={question.sourceTimestamps} />
              </li>
            ))}
          </MinutesSection>

          <MinutesSection title="リスク" emptyMessage="リスクはありません。">
            {minutes.risks.map((risk, index) => (
              <li key={`${risk.text}-${index}`}>
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
      <span className={`panel-status panel-status--${statusTone}`}>{statusLabel}</span>
    </div>
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
  variant: "minutes" | "transcript";
}) {
  return (
    <div className={`result-placeholder result-placeholder--${variant}`}>
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

function SpeakerMappingPreview({ speakers }: { speakers: TranscriptResponse["speakers"] }) {
  return (
    <div className="speaker-mapping">
      <div className="panel-subheader">
        <div>
          <h3>話者マッピング</h3>
          {!frontendFeatures.speakerMappingSave ? <p>表示名の編集は後続フェーズで有効化します。</p> : null}
        </div>
      </div>
      {speakers.length > 0 ? (
        <div className="speaker-grid">
          {speakers.map((speaker) => (
            <label className="speaker-chip" key={speaker.speakerLabel}>
              <span>
                <strong>{speaker.speakerLabel}</strong>
                <small>{speaker.phraseCount}件の発話</small>
              </span>
              <input
                aria-label={`${speaker.speakerLabel}の表示名`}
                value={speaker.displayName || ""}
                placeholder="表示名未設定"
                disabled
                readOnly
              />
            </label>
          ))}
        </div>
      ) : (
        <p className="empty-state">話者情報はまだありません。</p>
      )}
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
  children: React.ReactNode;
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
  return <small className="evidence">根拠: {formatTimestampList(timestamps)}</small>;
}

function getTranscriptStatusLabel(isReady: boolean, hasTranscript: boolean): string {
  if (!frontendFeatures.transcriptApi) {
    return "API待ち";
  }
  if (hasTranscript) {
    return "表示可能";
  }
  return isReady ? "取得中" : "待機中";
}

function getMinutesStatusLabel(jobStatus: JobStatusResponse | null, hasMinutes: boolean): string {
  if (!frontendFeatures.minutesApi) {
    return "API待ち";
  }
  if (hasMinutes) {
    return "表示可能";
  }
  return jobStatus?.status === "DONE" ? "取得中" : "待機中";
}

function formatMilliseconds(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.round(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}時間${minutes}分`;
  }
  return `${minutes}分${seconds}秒`;
}

function formatConfidence(confidence: number | null): string | null {
  if (confidence === null) {
    return null;
  }
  const percentage = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(percentage)}%`;
}

function formatTimestampList(timestamps: string[]): string {
  return timestamps.length > 0 ? timestamps.join(" / ") : "タイムスタンプ未設定";
}
