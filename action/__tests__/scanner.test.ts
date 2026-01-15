import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { scanDependencies } from "../src/scanner.js";
import { PkgWatchClient } from "../src/api.js";

// Use vi.hoisted to ensure these are available when vi.mock is executed
const { mockScan, mockReadDependencies, mockReadDependenciesFromFile, MockDependencyParseError, mockExistsSync, mockStatSync, mockRealpathSync } = vi.hoisted(() => {
  class MockDependencyParseError extends Error {
    constructor(message: string) {
      super(message);
      this.name = "DependencyParseError";
    }
  }

  return {
    mockScan: vi.fn(),
    mockReadDependencies: vi.fn(),
    mockReadDependenciesFromFile: vi.fn(),
    MockDependencyParseError,
    mockExistsSync: vi.fn(),
    mockStatSync: vi.fn(),
    mockRealpathSync: vi.fn(),
  };
});

// Mock API client and dependency parsing
vi.mock("../src/api.js", () => ({
  PkgWatchClient: vi.fn().mockImplementation(() => ({
    scan: mockScan,
  })),
  DependencyParseError: MockDependencyParseError,
  readDependencies: (...args: unknown[]) => mockReadDependencies(...args),
  readDependenciesFromFile: (...args: unknown[]) => mockReadDependenciesFromFile(...args),
}));

// Mock node:fs for existsSync, statSync, and realpathSync
vi.mock("node:fs", () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
  statSync: (...args: unknown[]) => mockStatSync(...args),
  realpathSync: (...args: unknown[]) => mockRealpathSync(...args),
}));

describe("scanDependencies", () => {
  const originalGitHubWorkspace = process.env.GITHUB_WORKSPACE;

  beforeEach(() => {
    vi.clearAllMocks();
    // Set GITHUB_WORKSPACE to /repo for tests using /repo paths
    process.env.GITHUB_WORKSPACE = "/repo";
    // Default: path exists and is a directory
    mockExistsSync.mockReturnValue(true);
    mockStatSync.mockReturnValue({ isFile: () => false, isDirectory: () => true });
    // Default: realpathSync returns input unchanged (no symlink)
    mockRealpathSync.mockImplementation((p: string) => p);
    // Default mock response
    mockScan.mockResolvedValue({
      total: 2,
      critical: 0,
      high: 1,
      medium: 1,
      low: 0,
      packages: [
        { package: "risky-pkg", risk_level: "HIGH", health_score: 45 },
        { package: "ok-pkg", risk_level: "MEDIUM", health_score: 65 },
      ],
    });
  });

  afterEach(() => {
    // Restore original GITHUB_WORKSPACE
    if (originalGitHubWorkspace === undefined) {
      delete process.env.GITHUB_WORKSPACE;
    } else {
      process.env.GITHUB_WORKSPACE = originalGitHubWorkspace;
    }
  });

  it("reads package.json and returns scan results", async () => {
    mockReadDependencies.mockReturnValue({
      dependencies: { lodash: "^4.17.21", vitest: "^2.0.0" },
      ecosystem: "npm",
      format: "package.json",
      count: 2,
    });

    const result = await scanDependencies("test-key", "/repo", true);

    expect(mockReadDependencies).toHaveBeenCalledWith("/repo", true);
    expect(result.total).toBe(2);
    expect(result.high).toBe(1);
    // Verify scan was called with npm ecosystem
    expect(mockScan).toHaveBeenCalledWith(expect.any(Object), "npm");
  });

  it("handles direct package.json path", async () => {
    // Mock as a file instead of directory
    mockStatSync.mockReturnValue({ isFile: () => true, isDirectory: () => false });
    mockReadDependenciesFromFile.mockReturnValue({
      dependencies: { express: "^4.0.0" },
      ecosystem: "npm",
      format: "package.json",
      count: 1,
    });

    await scanDependencies("test-key", "/repo/package.json", true);

    expect(mockReadDependenciesFromFile).toHaveBeenCalledWith("/repo/package.json", true);
  });

  it("throws error when no dependency file found", async () => {
    mockReadDependencies.mockImplementation(() => {
      throw new MockDependencyParseError("No dependency file found in /repo/missing");
    });

    await expect(scanDependencies("test-key", "/repo/missing", true)).rejects.toThrow(
      "No dependency file found"
    );
  });

  it("throws error for invalid JSON", async () => {
    mockReadDependencies.mockImplementation(() => {
      throw new MockDependencyParseError("Invalid JSON in package.json");
    });

    await expect(scanDependencies("test-key", "/repo", true)).rejects.toThrow(
      "Invalid JSON"
    );
  });

  it("excludes devDependencies when includeDev is false", async () => {
    mockReadDependencies.mockReturnValue({
      dependencies: { lodash: "^4.17.21" },
      ecosystem: "npm",
      format: "package.json",
      count: 1,
    });

    mockScan.mockResolvedValue({
      total: 1, critical: 0, high: 0, medium: 0, low: 1,
      packages: [{ package: "lodash", risk_level: "LOW", health_score: 90 }],
    });

    await scanDependencies("test-key", "/repo", false);

    // Verify includeDev=false was passed
    expect(mockReadDependencies).toHaveBeenCalledWith("/repo", false);
    // Verify scan was called with npm ecosystem
    expect(mockScan).toHaveBeenCalledWith({ lodash: "^4.17.21" }, "npm");
  });

  it("returns empty result for no dependencies", async () => {
    mockReadDependencies.mockReturnValue({
      dependencies: {},
      ecosystem: "npm",
      format: "package.json",
      count: 0,
    });

    const result = await scanDependencies("test-key", "/repo", true);

    expect(result.total).toBe(0);
    expect(result.packages).toEqual([]);
  });
});

describe("scanDependencies - Batch Processing", () => {
  const originalGitHubWorkspace = process.env.GITHUB_WORKSPACE;

  beforeEach(() => {
    vi.clearAllMocks();
    // Set GITHUB_WORKSPACE to /repo for tests using /repo paths
    process.env.GITHUB_WORKSPACE = "/repo";
    // Default: path exists and is a directory
    mockExistsSync.mockReturnValue(true);
    mockStatSync.mockReturnValue({ isFile: () => false, isDirectory: () => true });
    // Default: realpathSync returns input unchanged (no symlink)
    mockRealpathSync.mockImplementation((p: string) => p);
  });

  afterEach(() => {
    // Restore original GITHUB_WORKSPACE
    if (originalGitHubWorkspace === undefined) {
      delete process.env.GITHUB_WORKSPACE;
    } else {
      process.env.GITHUB_WORKSPACE = originalGitHubWorkspace;
    }
  });

  it("processes dependencies in batches when > 25 packages", async () => {
    // Create 30 dependencies
    const dependencies: Record<string, string> = {};
    for (let i = 0; i < 30; i++) {
      dependencies[`pkg-${i}`] = "^1.0.0";
    }

    mockReadDependencies.mockReturnValue({
      dependencies,
      ecosystem: "npm",
      format: "package.json",
      count: 30,
    });

    // Mock responses for two batches
    mockScan
      .mockResolvedValueOnce({
        total: 25,
        critical: 1,
        high: 2,
        medium: 10,
        low: 12,
        packages: Array.from({ length: 25 }, (_, i) => ({
          package: `pkg-${i}`,
          risk_level: i === 0 ? "CRITICAL" : i < 3 ? "HIGH" : i < 13 ? "MEDIUM" : "LOW",
          health_score: 50 + i,
        })),
      })
      .mockResolvedValueOnce({
        total: 5,
        critical: 0,
        high: 1,
        medium: 2,
        low: 2,
        packages: Array.from({ length: 5 }, (_, i) => ({
          package: `pkg-${25 + i}`,
          risk_level: i === 0 ? "HIGH" : i < 3 ? "MEDIUM" : "LOW",
          health_score: 60 + i,
        })),
      });

    const result = await scanDependencies("test-key", "/repo", true);

    // Should have called scan twice (25 + 5)
    expect(mockScan).toHaveBeenCalledTimes(2);

    // Should aggregate results correctly
    expect(result.total).toBe(30);
    expect(result.critical).toBe(1); // 1 from first batch
    expect(result.high).toBe(3); // 2 from first + 1 from second
    expect(result.packages.length).toBe(30);
  });

  it("aggregates not_found across batches", async () => {
    // Create 30 dependencies
    const dependencies: Record<string, string> = {};
    for (let i = 0; i < 30; i++) {
      dependencies[`pkg-${i}`] = "^1.0.0";
    }

    mockReadDependencies.mockReturnValue({
      dependencies,
      ecosystem: "npm",
      format: "package.json",
      count: 30,
    });

    // Mock responses with not_found packages in both batches
    mockScan
      .mockResolvedValueOnce({
        total: 23,
        critical: 0, high: 0, medium: 0, low: 23,
        packages: Array.from({ length: 23 }, (_, i) => ({
          package: `pkg-${i}`,
          risk_level: "LOW",
          health_score: 85,
        })),
        not_found: ["pkg-23", "pkg-24"],
      })
      .mockResolvedValueOnce({
        total: 4,
        critical: 0, high: 0, medium: 0, low: 4,
        packages: Array.from({ length: 4 }, (_, i) => ({
          package: `pkg-${25 + i}`,
          risk_level: "LOW",
          health_score: 85,
        })),
        not_found: ["pkg-29"],
      });

    const result = await scanDependencies("test-key", "/repo", true);

    // Should aggregate not_found from both batches
    expect(result.not_found).toEqual(["pkg-23", "pkg-24", "pkg-29"]);
    expect(result.total).toBe(27); // 23 + 4 found packages
  });

  it("does not batch when <= 25 packages", async () => {
    const dependencies: Record<string, string> = {};
    for (let i = 0; i < 20; i++) {
      dependencies[`pkg-${i}`] = "^1.0.0";
    }

    mockReadDependencies.mockReturnValue({
      dependencies,
      ecosystem: "npm",
      format: "package.json",
      count: 20,
    });

    mockScan.mockResolvedValue({
      total: 20,
      critical: 0, high: 0, medium: 0, low: 20,
      packages: [],
    });

    await scanDependencies("test-key", "/repo", true);

    // Should only call scan once
    expect(mockScan).toHaveBeenCalledTimes(1);
  });
});

describe("scanDependencies - Symlink Security", () => {
  const originalGitHubWorkspace = process.env.GITHUB_WORKSPACE;

  beforeEach(() => {
    vi.clearAllMocks();
    // Clear GITHUB_WORKSPACE so tests use process.cwd()
    delete process.env.GITHUB_WORKSPACE;
    mockExistsSync.mockReturnValue(true);
    mockStatSync.mockReturnValue({ isFile: () => false, isDirectory: () => true });
    // Default: realpathSync returns input unchanged
    mockRealpathSync.mockImplementation((p: string) => p);
    // Reset scan mock to avoid leaking from previous tests
    mockScan.mockReset();
  });

  afterEach(() => {
    // Restore original GITHUB_WORKSPACE
    if (originalGitHubWorkspace === undefined) {
      delete process.env.GITHUB_WORKSPACE;
    } else {
      process.env.GITHUB_WORKSPACE = originalGitHubWorkspace;
    }
  });

  it("rejects symlinks pointing outside workspace", async () => {
    // Symlink resolves to path outside workspace
    mockRealpathSync.mockReturnValue("/etc/passwd");

    await expect(
      scanDependencies("test-key", "./symlink-to-etc", false)
    ).rejects.toThrow("resolves outside workspace via symlink");
  });

  it("rejects symlinks using parent directory traversal", async () => {
    // Symlink resolves to path that escapes via ..
    const workspace = process.cwd();
    mockRealpathSync.mockReturnValue(`${workspace}/../secrets/config`);

    await expect(
      scanDependencies("test-key", "./malicious-link", false)
    ).rejects.toThrow("resolves outside workspace via symlink");
  });

  it("allows symlinks within workspace", async () => {
    const workspace = process.cwd();
    // Symlink resolves to valid path within workspace
    mockRealpathSync.mockReturnValue(`${workspace}/actual/nested/package.json`);
    mockStatSync.mockReturnValue({ isFile: () => true, isDirectory: () => false });
    mockReadDependenciesFromFile.mockReturnValue({
      dependencies: { lodash: "^4.0.0" },
      ecosystem: "npm",
      format: "package.json",
      count: 1,
    });
    mockScan.mockResolvedValue({
      total: 1, critical: 0, high: 0, medium: 0, low: 1,
      packages: [{ package: "lodash", risk_level: "LOW", health_score: 90 }],
    });

    // Should not throw - symlink is within workspace
    const result = await scanDependencies("test-key", "./symlink-to-nested", false);
    expect(result.total).toBe(1);
  });

  it("handles broken symlinks gracefully", async () => {
    mockRealpathSync.mockImplementation(() => {
      throw new Error("ENOENT: no such file or directory");
    });

    await expect(
      scanDependencies("test-key", "./broken-link", false)
    ).rejects.toThrow("Cannot resolve path");
  });

  it("handles permission denied on symlink resolution", async () => {
    mockRealpathSync.mockImplementation(() => {
      throw new Error("EACCES: permission denied");
    });

    await expect(
      scanDependencies("test-key", "./protected-link", false)
    ).rejects.toThrow("Cannot resolve path");
  });
});
