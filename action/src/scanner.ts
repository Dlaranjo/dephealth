import { resolve, relative, isAbsolute } from "node:path";
import { statSync, existsSync, realpathSync } from "node:fs";
import * as core from "@actions/core";
import {
  PkgWatchClient,
  ScanResult,
  PackageHealth,
  ApiClientError,
  readDependencies,
  readDependenciesFromFile,
  DependencyParseError,
  Ecosystem,
} from "./api";

const BATCH_SIZE = 25;

export interface ScanOptions {
  apiKey: string;
  basePath: string;
  includeDev: boolean;
  ecosystemOverride?: Ecosystem;
}

export interface ScanResultWithMeta extends ScanResult {
  /** The dependency file format that was scanned */
  format: string;
  /** The detected ecosystem */
  ecosystem: string;
}

export async function scanDependencies(
  apiKey: string,
  basePath: string,
  includeDev: boolean,
  ecosystemOverride?: Ecosystem
): Promise<ScanResultWithMeta> {
  // Determine if basePath is a file or directory and read dependencies
  let dependencies: Record<string, string>;
  let ecosystem: Ecosystem;
  let format: string;

  try {
    const resolvedPath = resolve(basePath);

    // Check if path exists
    if (!existsSync(resolvedPath)) {
      throw new DependencyParseError(`Path does not exist: ${resolvedPath}`);
    }

    // Resolve symlinks and validate the real path is within workspace
    let realPath: string;
    try {
      realPath = realpathSync(resolvedPath);
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      throw new DependencyParseError(`Cannot resolve path ${resolvedPath}: ${errMsg}`);
    }

    // Validate resolved path is still within workspace (prevent symlink escape)
    const workspace = process.env.GITHUB_WORKSPACE || process.cwd();
    const relativeToWorkspace = relative(workspace, realPath);
    if (relativeToWorkspace.startsWith("..") || isAbsolute(relativeToWorkspace)) {
      throw new DependencyParseError(
        `Path resolves outside workspace via symlink: ${resolvedPath} -> ${realPath}`
      );
    }

    // Use stat to properly determine if path is a file or directory
    const stats = statSync(realPath);
    if (stats.isFile()) {
      const result = readDependenciesFromFile(realPath, includeDev);
      dependencies = result.dependencies;
      ecosystem = result.ecosystem;
      format = result.format;
    } else if (stats.isDirectory()) {
      const result = readDependencies(realPath, includeDev);
      dependencies = result.dependencies;
      ecosystem = result.ecosystem;
      format = result.format;
    } else {
      throw new DependencyParseError(`Path is not a file or directory: ${realPath}`);
    }
  } catch (err) {
    if (err instanceof DependencyParseError) {
      throw new Error(
        `${err.message}\n\nEnsure the 'working-directory' input points to a directory containing a supported dependency file.`
      );
    }
    throw err;
  }

  // Allow ecosystem override
  if (ecosystemOverride) {
    ecosystem = ecosystemOverride;
    core.debug(`Ecosystem overridden to ${ecosystem}`);
  }

  const depCount = Object.keys(dependencies).length;

  if (depCount === 0) {
    core.info(`No dependencies found in ${format}`);
    return { total: 0, critical: 0, high: 0, medium: 0, low: 0, packages: [], format, ecosystem };
  }

  core.info(`Found ${depCount} ${ecosystem} dependencies in ${format}, analyzing health scores...`);

  const client = new PkgWatchClient(apiKey);

  // Batch processing for large dependency lists to avoid timeouts
  if (depCount <= BATCH_SIZE) {
    // Small enough to process in one request
    try {
      const result = await client.scan(dependencies, ecosystem);
      return { ...result, format, ecosystem };
    } catch (error) {
      // For single batch, we can't recover - rethrow with context
      if (error instanceof ApiClientError) {
        throw error;
      }
      throw new Error(`Failed to scan dependencies: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  // Process in batches
  const depEntries = Object.entries(dependencies);
  const allPackages: PackageHealth[] = [];
  let notFound: string[] = [];

  let failedBatches = 0;

  for (let i = 0; i < depEntries.length; i += BATCH_SIZE) {
    const batchNum = Math.floor(i / BATCH_SIZE) + 1;
    const totalBatches = Math.ceil(depEntries.length / BATCH_SIZE);
    core.info(`Processing batch ${batchNum}/${totalBatches}...`);

    const batchEntries = depEntries.slice(i, Math.min(i + BATCH_SIZE, depEntries.length));
    const batchDeps = Object.fromEntries(batchEntries);

    try {
      const batchResult = await client.scan(batchDeps, ecosystem);
      allPackages.push(...batchResult.packages);
      if (batchResult.not_found) {
        notFound.push(...batchResult.not_found);
      }
    } catch (error) {
      // Fail immediately on rate limit or auth errors - no point retrying more batches
      if (error instanceof ApiClientError) {
        if (error.code === "rate_limited" || error.code === "unauthorized" || error.code === "forbidden") {
          throw error;
        }
      }

      failedBatches++;
      const packageNames = batchEntries.map(([name]) => name);
      const errorMessage = error instanceof Error ? error.message : String(error);
      core.warning(`Batch ${batchNum} failed: ${errorMessage}. Packages: ${packageNames.slice(0, 5).join(", ")}${packageNames.length > 5 ? ` and ${packageNames.length - 5} more` : ""}`);
      // Continue with remaining batches instead of failing entirely
    }
  }

  if (failedBatches > 0) {
    core.warning(`${failedBatches} batch(es) failed. Results may be incomplete.`);
  }

  // Aggregate data quality counts
  let verifiedCount = 0;
  let partialCount = 0;
  let unverifiedCount = 0;
  let verifiedRiskCount = 0;
  let unverifiedRiskCount = 0;

  for (const pkg of allPackages) {
    const assessment = pkg.data_quality?.assessment || "UNVERIFIED";
    const isHighRisk = pkg.risk_level === "HIGH" || pkg.risk_level === "CRITICAL";

    if (assessment === "VERIFIED") {
      verifiedCount++;
      if (isHighRisk) verifiedRiskCount++;
    } else if (assessment === "PARTIAL") {
      partialCount++;
      if (isHighRisk) unverifiedRiskCount++;
    } else {
      unverifiedCount++;
      if (isHighRisk) unverifiedRiskCount++;
    }
  }

  // Aggregate results
  return {
    total: allPackages.length,
    critical: allPackages.filter((p: PackageHealth) => p.risk_level === "CRITICAL").length,
    high: allPackages.filter((p: PackageHealth) => p.risk_level === "HIGH").length,
    medium: allPackages.filter((p: PackageHealth) => p.risk_level === "MEDIUM").length,
    low: allPackages.filter((p: PackageHealth) => p.risk_level === "LOW").length,
    packages: allPackages,
    not_found: notFound.length > 0 ? notFound : undefined,
    data_quality: {
      verified_count: verifiedCount,
      partial_count: partialCount,
      unverified_count: unverifiedCount,
    },
    verified_risk_count: verifiedRiskCount,
    unverified_risk_count: unverifiedRiskCount,
    format,
    ecosystem,
  };
}
