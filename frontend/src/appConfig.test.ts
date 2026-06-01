import { describe, expect, it } from "vitest";

import { appTitle } from "./appConfig";

describe("appConfig", () => {
  it("uses a Japanese app title", () => {
    expect(appTitle).toContain("議事録");
  });
});
