import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("App", () => {
  it("renders the Minutes Studio brand and Japanese B2C hero copy", () => {
    const markup = renderToString(<App />);

    expect(markup).toContain("Minutes Studio");
    expect(markup).toContain("録音を、読める議事録へ。");
    expect(markup).toContain("アクションアイテムを自動整理");
    expect(markup).not.toContain("話者分離付き議事録を生成");
    expect(markup).not.toContain("Blob Storage");
  });
});
