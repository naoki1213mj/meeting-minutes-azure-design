import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { JobStatusResponse, MinutesResponse, TranscriptResponse } from "./apiClient";
import { getNextResultsTab, ResultsWorkspace } from "./Panels";

const doneJob: JobStatusResponse = {
  jobId: "job-1",
  tenantId: "tenant-1",
  userId: "user-1",
  minutesModel: "fast",
  processingRoute: "stable",
  status: "DONE",
  progress: {
    step: "完了",
    percent: 100,
    message: "議事録が完成しました。",
    updatedAt: "2026-06-02T00:00:00.000Z",
  },
  outputs: {
    transcriptReady: true,
    minutesReady: true,
  },
  error: null,
  createdAt: "2026-06-02T00:00:00.000Z",
  updatedAt: "2026-06-02T00:05:00.000Z",
};

const transcript: TranscriptResponse = {
  jobId: "job-1",
  tenantId: "tenant-1",
  locale: "ja-JP",
  durationMilliseconds: 125000,
  speakers: [
    {
      speakerLabel: "Speaker 1",
      displayName: null,
      phraseCount: 1,
      representativePhrases: [
        {
          offsetMilliseconds: 1000,
          startTimeText: "00:00:01",
          text: "本日の目的を確認します。",
        },
      ],
    },
  ],
  phrases: [
    {
      phraseId: "phrase-1",
      speakerLabel: "Speaker 1",
      displayName: null,
      offsetMilliseconds: 1000,
      durationMilliseconds: 3000,
      startTimeText: "00:00:01",
      text: "本日の目的を確認します。",
      confidence: 0.98,
    },
  ],
};

const minutes: MinutesResponse = {
  jobId: "job-1",
  tenantId: "tenant-1",
  title: "定例会議",
  summary: "次回リリースに向けた優先事項を確認しました。",
  topics: [
    {
      title: "リリース計画",
      discussion: "公開日と確認手順を整理しました。",
      evidenceTimestamps: ["00:03:00"],
    },
  ],
  decisions: [
    {
      text: "予算を承認する",
      owner: "田中",
      sourceTimestamps: ["00:01:00"],
    },
  ],
  actionItems: [
    {
      task: "レビュー観点を共有する",
      owner: "佐藤",
      dueDate: "2026-06-10",
      sourceTimestamps: ["00:02:00"],
    },
  ],
  openQuestions: [
    {
      text: "追加検証の担当範囲を確認する",
      owner: null,
      sourceTimestamps: ["00:04:00"],
    },
  ],
  risks: [
    {
      text: "外部レビューが遅れる可能性",
      severity: "medium",
      sourceTimestamps: ["00:05:00"],
    },
  ],
};

describe("ResultsWorkspace", () => {
  it("supports roving keyboard tab navigation semantics", () => {
    expect(getNextResultsTab("minutes", "ArrowRight")).toBe("transcript");
    expect(getNextResultsTab("transcript", "ArrowRight")).toBe("visual");
    expect(getNextResultsTab("visual", "ArrowRight")).toBe("minutes");
    expect(getNextResultsTab("transcript", "ArrowLeft")).toBe("minutes");
    expect(getNextResultsTab("minutes", "End")).toBe("visual");
    expect(getNextResultsTab("visual", "Home")).toBe("minutes");
    expect(getNextResultsTab("minutes", "Enter")).toBeNull();
  });

  it("renders a minutes-first tab workspace for completed jobs", () => {
    const markup = renderToString(
      <ResultsWorkspace
        activeTab="minutes"
        jobStatus={doneJob}
        minutes={minutes}
        transcript={transcript}
        visualContext={null}
        onTabChange={() => undefined}
      />,
    );

    const minutesTabIndex = markup.indexOf("<span>議事録</span>");
    const transcriptTabIndex = markup.indexOf("<span>文字起こし</span>");
    expect(minutesTabIndex).toBeGreaterThan(-1);
    expect(transcriptTabIndex).toBeGreaterThan(minutesTabIndex);
    expect(markup).toContain('aria-selected=\"true\"');
    expect(markup).toContain("会議ブリーフ");
    expect(markup).toContain("アクションアイテム");
    expect(markup).toContain("該当箇所:");
    expect(markup).toContain("00:01:00");
    expect(markup).not.toContain("ToDo");

    const summaryIndex = markup.indexOf("次回リリースに向けた優先事項");
    const decisionIndex = markup.indexOf("予算を承認する");
    const actionIndex = markup.indexOf("レビュー観点を共有する");
    const topicIndex = markup.indexOf("リリース計画");
    const questionIndex = markup.indexOf("追加検証の担当範囲");
    const riskIndex = markup.indexOf("外部レビューが遅れる可能性");
    expect(summaryIndex).toBeLessThan(decisionIndex);
    expect(decisionIndex).toBeLessThan(actionIndex);
    expect(actionIndex).toBeLessThan(topicIndex);
    expect(topicIndex).toBeLessThan(questionIndex);
    expect(questionIndex).toBeLessThan(riskIndex);
  });

  it("renders transcript as a supplementary tab without disabled speaker inputs", () => {
    const markup = renderToString(
      <ResultsWorkspace
        activeTab="transcript"
        jobStatus={doneJob}
        minutes={minutes}
        transcript={transcript}
        visualContext={null}
        onTabChange={() => undefined}
      />,
    );

    expect(markup).toContain("文字起こし概要");
    expect(markup).toContain("話者");
    expect(markup).toContain("発話一覧");
    expect(markup).toContain("表示名未設定");
    expect(markup).not.toContain("<input");
    expect(markup).not.toContain("disabled");
  });
});
