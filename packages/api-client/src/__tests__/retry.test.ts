import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DepHealthClient, ApiClientError } from "../index.js";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("DepHealthClient retry behavior", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  const createClient = () =>
    new DepHealthClient("dh_test123", {
      baseUrl: "https://api.test.com",
      timeout: 5000,
      maxRetries: 3,
    });

  // ===========================================
  // Success Cases
  // ===========================================

  it("returns data on successful response", async () => {
    const mockData = { package: "lodash", health_score: 85 };
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockData),
    });

    const client = createClient();
    const result = await client.getPackage("lodash");

    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  // ===========================================
  // Retry on 5xx Errors
  // ===========================================

  it("retries on 500 error and succeeds on second attempt", async () => {
    const mockData = { package: "lodash", health_score: 85 };

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.reject(new Error("No body")),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    // Advance past the first retry delay (1-2 seconds with jitter)
    await vi.advanceTimersByTimeAsync(2500);

    const result = await resultPromise;
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("retries on 502 error", async () => {
    const mockData = { package: "lodash", health_score: 85 };

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        statusText: "Bad Gateway",
        json: () => Promise.reject(new Error("No body")),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    await vi.advanceTimersByTimeAsync(2500);

    const result = await resultPromise;
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("retries on 503 error", async () => {
    const mockData = { package: "lodash", health_score: 85 };

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        statusText: "Service Unavailable",
        json: () => Promise.reject(new Error("No body")),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    await vi.advanceTimersByTimeAsync(2500);

    const result = await resultPromise;
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  // ===========================================
  // Retry on 429 Rate Limit
  // ===========================================

  it("retries on 429 rate limit", async () => {
    const mockData = { package: "lodash", health_score: 85 };

    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 429,
        statusText: "Too Many Requests",
        json: () => Promise.resolve({ error: { message: "Rate limited" } }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    await vi.advanceTimersByTimeAsync(2500);

    const result = await resultPromise;
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  // ===========================================
  // No Retry on 4xx Errors (except 429)
  // ===========================================

  it("does NOT retry on 400 error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ message: "Invalid request" }),
    });

    const client = createClient();

    await expect(client.getPackage("lodash")).rejects.toThrow(ApiClientError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("does NOT retry on 401 error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({ error: { message: "Invalid API key" } }),
    });

    const client = createClient();

    await expect(client.getPackage("lodash")).rejects.toThrow(ApiClientError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("does NOT retry on 403 error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: () => Promise.resolve({ message: "Access denied" }),
    });

    const client = createClient();

    await expect(client.getPackage("lodash")).rejects.toThrow(ApiClientError);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it("does NOT retry on 404 error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ message: "Package not found" }),
    });

    const client = createClient();

    await expect(client.getPackage("nonexistent")).rejects.toThrow(
      ApiClientError
    );
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  // ===========================================
  // Max Retries Exceeded
  // ===========================================

  it("fails after max retries exceeded", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("No body")),
    });

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    // Advance through all retry delays (1s + 2s + 4s + margin for jitter)
    await vi.advanceTimersByTimeAsync(10000);

    await expect(resultPromise).rejects.toThrow(ApiClientError);
    // Initial attempt + 3 retries = 4 total calls
    expect(mockFetch).toHaveBeenCalledTimes(4);
  });

  // ===========================================
  // Network Errors
  // ===========================================

  it("retries on network error", async () => {
    const mockData = { package: "lodash", health_score: 85 };

    mockFetch
      .mockRejectedValueOnce(new Error("Network failure"))
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    await vi.advanceTimersByTimeAsync(2500);

    const result = await resultPromise;
    expect(result).toEqual(mockData);
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it("throws network_error after all retries fail", async () => {
    mockFetch.mockRejectedValue(new Error("Network failure"));

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    await vi.advanceTimersByTimeAsync(10000);

    await expect(resultPromise).rejects.toMatchObject({
      code: "network_error",
    });
  });

  // ===========================================
  // Timeout Handling
  // ===========================================

  it("throws timeout error when request exceeds timeout", async () => {
    // Create an abort error
    const abortError = new Error("Aborted");
    abortError.name = "AbortError";
    mockFetch.mockRejectedValue(abortError);

    const client = createClient();
    const resultPromise = client.getPackage("lodash");

    await vi.advanceTimersByTimeAsync(10000);

    await expect(resultPromise).rejects.toMatchObject({
      code: "timeout",
    });
  });

  // ===========================================
  // Error Code Mapping
  // ===========================================

  it("maps 400 to invalid_request", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toMatchObject({
      code: "invalid_request",
    });
  });

  it("maps 401 to unauthorized", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      statusText: "Unauthorized",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toMatchObject({
      code: "unauthorized",
    });
  });

  it("maps 403 to forbidden", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toMatchObject({
      code: "forbidden",
    });
  });

  it("maps 404 to not_found", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toMatchObject({
      code: "not_found",
    });
  });

  it("maps 429 to rate_limited", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 429,
      statusText: "Too Many Requests",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    const resultPromise = client.getPackage("test");

    await vi.advanceTimersByTimeAsync(10000);

    await expect(resultPromise).rejects.toMatchObject({
      code: "rate_limited",
    });
  });

  it("maps 500 to server_error", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    const resultPromise = client.getPackage("test");

    await vi.advanceTimersByTimeAsync(10000);

    await expect(resultPromise).rejects.toMatchObject({
      code: "server_error",
    });
  });

  it("maps unknown 4xx to unknown_error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 418,
      statusText: "I'm a teapot",
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toMatchObject({
      code: "unknown_error",
    });
  });

  // ===========================================
  // Error Message Parsing
  // ===========================================

  it("extracts message from error.message field", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ error: { message: "Custom error message" } }),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toThrow(
      "Custom error message"
    );
  });

  it("extracts message from flat message field", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ message: "Flat message" }),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toThrow("Flat message");
  });

  it("falls back to statusText when body parsing fails", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.reject(new Error("Invalid JSON")),
    });

    const client = createClient();
    await expect(client.getPackage("test")).rejects.toThrow("Bad Request");
  });

  // ===========================================
  // Request Format Tests
  // ===========================================

  it("encodes scoped package names correctly", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ package: "@types/node" }),
    });

    const client = createClient();
    await client.getPackage("@types/node");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("%40types%2Fnode"),
      expect.any(Object)
    );
  });

  it("includes X-API-Key header", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({}),
    });

    const client = createClient();
    await client.getPackage("lodash");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-API-Key": "dh_test123",
        }),
      })
    );
  });

  it("sends POST request for scan", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: () =>
        Promise.resolve({ total: 1, critical: 0, high: 0, medium: 0, low: 1, packages: [] }),
    });

    const client = createClient();
    await client.scan({ lodash: "^4.0.0" });

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/scan"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ dependencies: { lodash: "^4.0.0" } }),
      })
    );
  });
});
