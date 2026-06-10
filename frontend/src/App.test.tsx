import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the Minutes Studio brand and Japanese B2C hero copy", () => {
    const markup = renderToString(<App />);

    expect(markup).toContain("Minutes Studio");
    expect(markup).toContain("録音を、");
    expect(markup).toContain("読める議事録へ。");
    expect(markup).toContain("アクションアイテムを自動整理");
    expect(markup).toContain("経過時間");
    expect(markup).toContain("議事録生成モード");
    expect(markup).toContain("処理方式");
    expect(markup).toContain("動画理解");
    expect(markup).toContain("仕組みガイド");
    expect(markup).toContain("処理の仕組みとAzure構成");
    expect(markup).toContain("Public Ingest Storage");
    expect(markup).toContain("高速");
    expect(markup).not.toContain("話者分離付き議事録を生成");
  });
});
