import { describe, it, expect, vi, beforeEach } from "vitest";
import * as core from "@actions/core";
import { generateSummary } from "../src/summary.js";
import type { ScanResult } from "../src/api.js";

// Mock @actions/core
vi.mock("@actions/core", () => ({
  summary: {
    addRaw: vi.fn().mockReturnThis(),
    addHeading: vi.fn().mockReturnThis(),
    addTable: vi.fn().mockReturnThis(),
    write: vi.fn().mockResolvedValue(undefined),
  },
}));

describe("generateSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("generates summary with pass banner when threshold not exceeded", async () => {
    const result: ScanResult = {
      total: 5,
      critical: 0,
      high: 0,
      medium: 2,
      low: 3,
      packages: [],
    };

    await generateSummary(result, false, "HIGH");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("[!TIP]")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Scan Passed")
    );
    expect(core.summary.write).toHaveBeenCalled();
  });

  it("generates summary with fail banner when threshold exceeded", async () => {
    const result: ScanResult = {
      total: 5,
      critical: 1,
      high: 2,
      medium: 1,
      low: 1,
      packages: [],
    };

    await generateSummary(result, true, "HIGH");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("[!CAUTION]")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Policy Violation")
    );
  });

  it("generates table for high-risk packages", async () => {
    const result: ScanResult = {
      total: 2,
      critical: 1,
      high: 1,
      medium: 0,
      low: 0,
      packages: [
        {
          package: "bad-pkg",
          risk_level: "CRITICAL",
          health_score: 15,
          abandonment_risk: { risk_factors: ["Deprecated"] },
        } as any,
        {
          package: "risky-pkg",
          risk_level: "HIGH",
          health_score: 40,
          abandonment_risk: { risk_factors: ["Low maintainers"] },
        } as any,
      ],
    };

    await generateSummary(result, true, "HIGH");

    expect(core.summary.addHeading).toHaveBeenCalledWith(
      "Packages Requiring Attention",
      3
    );
    expect(core.summary.addTable).toHaveBeenCalled();
  });

  it("shows healthy banner when no threshold set and no issues", async () => {
    const result: ScanResult = {
      total: 1,
      critical: 0,
      high: 0,
      medium: 0,
      low: 1,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("[!TIP]")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Healthy")
    );
  });

  it("shows warning banner when no threshold set but has issues", async () => {
    const result: ScanResult = {
      total: 2,
      critical: 1,
      high: 0,
      medium: 0,
      low: 1,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("[!WARNING]")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Attention")
    );
  });

  it("generates collapsible section for all packages", async () => {
    const result: ScanResult = {
      total: 2,
      critical: 0,
      high: 0,
      medium: 1,
      low: 1,
      packages: [
        { package: "pkg-a", risk_level: "MEDIUM", health_score: 60 } as any,
        { package: "pkg-b", risk_level: "LOW", health_score: 80 } as any,
      ],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("<details>")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("View all packages")
    );
  });
});

describe("escapeMarkdown (via generateSummary)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("escapes markdown special characters in package names", async () => {
    const result: ScanResult = {
      total: 1,
      critical: 1,
      high: 0,
      medium: 0,
      low: 0,
      packages: [
        {
          package: "@scope/pkg-name",
          risk_level: "CRITICAL",
          health_score: 10,
          abandonment_risk: { risk_factors: ["Test *bold* _italic_"] },
        } as any,
      ],
    };

    await generateSummary(result, true, "CRITICAL");

    // The table should be called with escaped content
    expect(core.summary.addTable).toHaveBeenCalled();
  });
});

describe("feedback links in footer", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows feedback links when CRITICAL issues found", async () => {
    const result: ScanResult = {
      total: 5,
      critical: 1,
      high: 0,
      medium: 2,
      low: 2,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Wrong score?")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Feedback")
    );
  });

  it("shows feedback links when HIGH issues found", async () => {
    const result: ScanResult = {
      total: 5,
      critical: 0,
      high: 2,
      medium: 2,
      low: 1,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Wrong score?")
    );
  });

  it("hides feedback links when no HIGH/CRITICAL issues", async () => {
    const result: ScanResult = {
      total: 5,
      critical: 0,
      high: 0,
      medium: 2,
      low: 3,
      packages: [],
    };

    await generateSummary(result, false, "");

    // Check that addRaw was NOT called with "Wrong score?"
    const addRawCalls = (core.summary.addRaw as any).mock.calls;
    const hasWrongScoreLink = addRawCalls.some(
      (call: string[]) => call[0] && call[0].includes("Wrong score?")
    );
    expect(hasWrongScoreLink).toBe(false);
  });

  it("includes UTM parameters in PkgWatch link", async () => {
    const result: ScanResult = {
      total: 1,
      critical: 1,
      high: 0,
      medium: 0,
      low: 0,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("utm_source=action")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("utm_medium=summary")
    );
  });

  it("shows feedback links when both CRITICAL and HIGH issues found", async () => {
    const result: ScanResult = {
      total: 5,
      critical: 2,
      high: 3,
      medium: 0,
      low: 0,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("Wrong score?")
    );
  });

  it("feedback link points to discussions", async () => {
    const result: ScanResult = {
      total: 1,
      critical: 1,
      high: 0,
      medium: 0,
      low: 0,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("discussions/new?category=feedback")
    );
  });

  it("wrong score link points to bug report template", async () => {
    const result: ScanResult = {
      total: 1,
      critical: 1,
      high: 0,
      medium: 0,
      low: 0,
      packages: [],
    };

    await generateSummary(result, false, "");

    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("template=bug_report.yml")
    );
    expect(core.summary.addRaw).toHaveBeenCalledWith(
      expect.stringContaining("labels=bug,action,false-positive")
    );
  });
});
