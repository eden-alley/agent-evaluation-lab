import test from "node:test";
import assert from "node:assert/strict";
import { ApiError, request } from "../lib/api";

test("comparison routes get 90 seconds and unrelated routes retain 12 seconds", async () => {
  const originalFetch = globalThis.fetch;
  const originalTimeout = AbortSignal.timeout;
  const deadlines: number[] = [];
  AbortSignal.timeout = (ms) => { deadlines.push(ms); return new AbortController().signal; };
  globalThis.fetch = async () => new Response('{"ok":true}', { status: 200 });
  try {
    for (const path of ["/comparisons", "/comparisons?id=1", "/comparisons/abc", "/health", "/comparisons-other"]) {
      assert.deepEqual(await request(path), { ok: true });
    }
    assert.deepEqual(deadlines, [90000, 90000, 90000, 12000, 12000]);
  } finally {
    globalThis.fetch = originalFetch;
    AbortSignal.timeout = originalTimeout;
  }
});

test("comparison timeout warns that creation may still be running without retrying", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; throw new DOMException("Timed out", "TimeoutError"); };
  try {
    await assert.rejects(request("/comparisons", { method: "POST" }), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.code, "API_TIMEOUT");
      assert.match(error.message, /仍在处理/);
      assert.match(error.message, /刷新/);
      assert.match(error.message, /重复创建/);
      return true;
    });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = originalFetch; }
});

test("network failures and non-comparison timeouts keep existing unavailable behavior without retrying", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  try {
    for (const [path, error] of [["/comparisons/abc", new TypeError("network")], ["/health", new DOMException("Timed out", "TimeoutError")]] as const) {
      globalThis.fetch = async () => { calls++; throw error; };
      await assert.rejects(request(path), (caught: unknown) => {
        assert.ok(caught instanceof ApiError);
        assert.equal(caught.code, "API_UNAVAILABLE");
        return true;
      });
    }
    assert.equal(calls, 2);
  } finally { globalThis.fetch = originalFetch; }
});

test("comparison HTTP errors preserve backend status and details without retrying", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async () => { calls++; return new Response(JSON.stringify({ error: { code: "BAD_INPUT", message: "bad input" } }), { status: 400 }); };
  try {
    await assert.rejects(request("/comparisons"), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 400);
      assert.equal(error.code, "BAD_INPUT");
      assert.equal(error.message, "bad input");
      return true;
    });
    assert.equal(calls, 1);
  } finally { globalThis.fetch = originalFetch; }
});
