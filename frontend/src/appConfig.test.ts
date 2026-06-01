import { describe, expect, it } from "vitest";

import { appTitle, heroCopy, heroHeadline } from "./appConfig";

describe("appConfig", () => {
  it("uses the Minutes Studio brand and polished Japanese hero copy", () => {
    expect(appTitle).toBe("Minutes Studio");
    expect(heroHeadline).toBe("録音を、読める議事録へ。");
    expect(heroCopy).toContain("アクションアイテム");
  });

  it("does not expose the old implementation-focused title", () => {
    const visibleCopy = [appTitle, heroHeadline, heroCopy].join(" ");

    expect(visibleCopy).not.toContain("話者分離付き議事録を生成");
  });
});
